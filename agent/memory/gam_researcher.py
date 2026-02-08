# -*- coding: utf-8 -*-
"""
GAM Researcher - LLM 驱动的深度研究组件

基于 GAM 论文 (arxiv:2511.18423) 实现的在线阶段组件。
负责在 Phase 开始前，通过 Deep-Research 循环检索历史记忆。

Deep-Research 循环:
1. Planning: LLM 分析查询，规划搜索策略
2. Searching: 向量搜索 + BM25 + Page-ID 多工具检索
3. Reflection: LLM 评估结果，决定是否继续迭代

运行时机: Phase 开始前，为 Worker 准备上下文
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from inspect import isasyncgen
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import PageStoreBase, RetrieverBase
from .models import Page, PreconstructedMemory, SessionMemo
from .utils import extract_keywords

logger = logging.getLogger(__name__)


class GAMResearcher:
    """
    GAM 在线阶段 - LLM 驱动的深度研究

    主入口方法: deep_research()
    """

    def __init__(
        self,
        page_store: PageStoreBase,
        memo_store: Dict[str, SessionMemo],
        model: Any,  # ChatModelBase 或类似接口
        retrievers: Optional[List[RetrieverBase]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化 GAMResearcher

        Args:
            page_store: Page 存储实例
            memo_store: SessionMemo 存储 (来自 GAMMemorizer)
            model: LLM 模型实例
            retrievers: 检索器列表 (可选，会自动创建默认检索器)
            config: 配置选项
        """
        self.page_store = page_store
        self.memo_store = memo_store
        self.model = model
        self.config = config or {}

        # 配置
        self.max_iterations = self.config.get("max_iterations", 3)
        self.min_confidence = self.config.get("min_confidence", 0.7)
        self.top_k_memos = self.config.get("top_k_memos", 10)
        self.top_k_pages = self.config.get("top_k_pages", 20)

        # 初始化检索器
        self.retrievers = {}
        if retrievers:
            for r in retrievers:
                self.retrievers[r.get_name()] = r
        else:
            self._init_default_retrievers()

        # Prompt 模板路径
        self.prompts_dir = Path(self.config.get("prompts_dir", "prompts/memory"))

        # 统计
        self._researches_completed = 0
        self._total_iterations = 0

    def _init_default_retrievers(self) -> None:
        """初始化默认检索器（独立初始化，一个失败不影响其他）"""
        # BM25 (有纯 Python fallback)
        try:
            from .retrieval import BM25Retriever
            self.retrievers["bm25_search"] = BM25Retriever(self.config)
        except ImportError as e:
            logger.warning(f"BM25Retriever not available: {e}")

        # Vector Search (依赖 sentence_transformers)
        try:
            from .retrieval import VectorSearchRetriever
            self.retrievers["vector_search"] = VectorSearchRetriever(self.config)
        except ImportError as e:
            logger.info(f"VectorSearchRetriever not available: {e}")

        # Page ID Search
        try:
            from .retrieval import PageIDRetriever
            self.retrievers["page_id_search"] = PageIDRetriever(self.page_store, self.config)
        except ImportError as e:
            logger.warning(f"PageIDRetriever not available: {e}")

        if not self.retrievers:
            logger.info("No retrievers available, will use page_store fallback")

    async def deep_research(
        self,
        query: str,
        plan_id: Optional[str] = None,
        pre_memory: Optional[PreconstructedMemory] = None
    ) -> PreconstructedMemory:
        """
        执行 Deep-Research 循环 - 主入口

        Args:
            query: 查询/目标
            plan_id: 可选的 Plan ID 过滤
            pre_memory: 可选的预存在记忆（用于增量研究）

        Returns:
            PreconstructedMemory 实例
        """
        logger.info(f"GAMResearcher: Starting deep research for: {query[:50]}...")

        # 初始化记忆
        memory = pre_memory or PreconstructedMemory(query=query)

        for iteration in range(self.max_iterations):
            logger.debug(f"GAMResearcher: Iteration {iteration + 1}/{self.max_iterations}")

            # 1. Planning - LLM 规划搜索策略
            strategy = await self._plan_search(query, memory, iteration)
            memory.search_strategy = strategy

            # 2. Searching - 执行多工具检索
            new_memos, new_pages = await self._execute_search(query, strategy, plan_id)

            # 合并结果（去重）
            existing_memo_ids = {m.memo_id for m in memory.retrieved_memos}
            for memo in new_memos:
                if memo.memo_id not in existing_memo_ids:
                    memory.retrieved_memos.append(memo)
                    existing_memo_ids.add(memo.memo_id)

            existing_page_ids = {p.page_id for p in memory.retrieved_pages}
            for page in new_pages:
                if page.page_id not in existing_page_ids:
                    memory.retrieved_pages.append(page)
                    existing_page_ids.add(page.page_id)

            memory.iterations = iteration + 1

            # 3. Reflection - LLM 评估结果充分性
            is_sufficient, confidence, feedback = await self._reflect(query, memory)
            memory.is_sufficient = is_sufficient
            memory.confidence_score = confidence

            logger.debug(
                f"GAMResearcher: Iteration {iteration + 1} - "
                f"sufficient={is_sufficient}, confidence={confidence:.2f}, "
                f"memos={len(memory.retrieved_memos)}, pages={len(memory.retrieved_pages)}"
            )

            if is_sufficient:
                break

        # 生成最终上下文
        memory.context_summary = await self._generate_context(query, memory)

        # 更新统计
        self._researches_completed += 1
        self._total_iterations += memory.iterations

        logger.info(
            f"GAMResearcher: Deep research completed - "
            f"iterations={memory.iterations}, confidence={memory.confidence_score:.2f}"
        )

        return memory

    async def _plan_search(
        self,
        query: str,
        memory: PreconstructedMemory,
        iteration: int
    ) -> Dict[str, Any]:
        """
        LLM 规划搜索策略

        Args:
            query: 查询文本
            memory: 当前记忆状态
            iteration: 当前迭代次数

        Returns:
            搜索策略字典
        """
        # 默认策略
        default_strategy = {
            "search_memos_first": True,
            "use_vector_search": True,
            "use_bm25_search": True,
            "vector_weight": 0.6,
            "bm25_weight": 0.4,
            "search_queries": [query],
            "top_k": 10,
            "reasoning": "默认策略"
        }

        # 第一次迭代或没有模型时使用默认策略
        if iteration == 0 and self.model is None:
            return default_strategy

        # 构建 prompt
        prompt = self._build_planning_prompt(query, memory, iteration)

        try:
            response = await self._call_model(prompt)
            strategy = self._parse_planning_response(response)

            # 确保必要字段存在
            strategy.setdefault("search_memos_first", True)
            strategy.setdefault("use_vector_search", True)
            strategy.setdefault("use_bm25_search", True)
            strategy.setdefault("vector_weight", 0.6)
            strategy.setdefault("bm25_weight", 0.4)
            strategy.setdefault("search_queries", [query])
            strategy.setdefault("top_k", 10)

            return strategy

        except Exception as e:
            logger.warning(f"GAMResearcher: Planning failed: {e}, using default strategy")
            return default_strategy

    def _build_planning_prompt(
        self,
        query: str,
        memory: PreconstructedMemory,
        iteration: int
    ) -> str:
        """构建搜索规划 prompt"""
        return f"""你是研究规划助手。分析查询并规划最优搜索策略。

## 查询
{query}

## 当前状态
- 迭代次数: {iteration + 1}
- 已检索 Memos: {len(memory.retrieved_memos)}
- 已检索 Pages: {len(memory.retrieved_pages)}

## 可用搜索工具
1. 向量搜索: 语义相似度，适合概念性查询
2. BM25 搜索: 关键词匹配，适合精确术语
3. Page-ID 查找: 直接访问已知页面

## 任务
规划搜索策略。考虑：
- 查询是概念性的还是精确的？
- 需要哪种搜索方法组合？
- 是否需要扩展或修改搜索查询？

输出 JSON:
```json
{{
  "search_memos_first": true,
  "use_vector_search": true,
  "use_bm25_search": true,
  "vector_weight": 0.6,
  "bm25_weight": 0.4,
  "search_queries": ["主查询", "扩展查询1"],
  "top_k": 10,
  "reasoning": "选择该策略的原因"
}}
```"""

    def _parse_planning_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的规划策略"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return {}

    async def _execute_search(
        self,
        query: str,
        strategy: Dict[str, Any],
        plan_id: Optional[str] = None
    ) -> Tuple[List[SessionMemo], List[Page]]:
        """
        执行多工具检索

        Args:
            query: 查询文本
            strategy: 搜索策略
            plan_id: 可选的 Plan ID 过滤

        Returns:
            (memos, pages) 元组
        """
        memos = []
        pages = []

        search_queries = strategy.get("search_queries", [query])
        top_k = strategy.get("top_k", 10)

        # 1. 搜索 Memos（如果策略指定）
        if strategy.get("search_memos_first", True):
            for sq in search_queries:
                memo_results = self._search_memos(sq, plan_id, top_k)
                memos.extend([m for m, _ in memo_results])

        # 2. 搜索 Pages
        all_page_scores: Dict[str, float] = {}

        # 检查 retrievers 可用性
        has_retrievers = bool(self.retrievers)
        use_vector = strategy.get("use_vector_search") and "vector_search" in self.retrievers
        use_bm25 = strategy.get("use_bm25_search") and "bm25_search" in self.retrievers

        # Fallback: 当没有可用 retriever 时，使用 page_store.search_pages()
        if not has_retrievers or (not use_vector and not use_bm25):
            logger.debug("GAMResearcher: Using page_store.search_pages() as fallback")
            filters = {"plan_id": plan_id} if plan_id else None

            for sq in search_queries:
                page_results = self.page_store.search_pages(sq, top_k=top_k, filters=filters)
                for page, score in page_results:
                    if page.page_id not in all_page_scores:
                        all_page_scores[page.page_id] = score
                    else:
                        all_page_scores[page.page_id] = max(all_page_scores[page.page_id], score)

            # 按得分排序返回
            sorted_pages = sorted(all_page_scores.items(), key=lambda x: x[1], reverse=True)
            for page_id, _ in sorted_pages[:top_k]:
                page = self.page_store.get_page(page_id)
                if page:
                    pages.append(page)

            return memos, pages

        # 使用 retrievers 进行搜索
        pages_list = list(self.page_store.iter_pages())

        if not pages_list:
            return memos, pages

        # 应用 plan_id 过滤
        if plan_id:
            pages_list = [p for p in pages_list if p.plan_id == plan_id]

        documents = [p.content for p in pages_list]

        for sq in search_queries:
            # 向量搜索
            if use_vector:
                vector_retriever = self.retrievers["vector_search"]
                vector_retriever.index_documents(documents)
                vector_results = vector_retriever.search(sq, top_k=top_k)

                vector_weight = strategy.get("vector_weight", 0.6)
                for idx, score in vector_results:
                    if 0 <= idx < len(pages_list):
                        page_id = pages_list[idx].page_id
                        all_page_scores[page_id] = all_page_scores.get(page_id, 0) + score * vector_weight

            # BM25 搜索
            if use_bm25:
                bm25_retriever = self.retrievers["bm25_search"]
                bm25_retriever.index_documents(documents)
                bm25_results = bm25_retriever.search(sq, top_k=top_k)

                bm25_weight = strategy.get("bm25_weight", 0.4)
                for idx, score in bm25_results:
                    if 0 <= idx < len(pages_list):
                        page_id = pages_list[idx].page_id
                        normalized_score = min(score / 10.0, 1.0)
                        all_page_scores[page_id] = all_page_scores.get(page_id, 0) + normalized_score * bm25_weight

        # 按得分排序
        sorted_pages = sorted(all_page_scores.items(), key=lambda x: x[1], reverse=True)

        for page_id, score in sorted_pages[:top_k]:
            page = self.page_store.get_page(page_id)
            if page:
                pages.append(page)

        return memos, pages

    def _search_memos(
        self,
        query: str,
        plan_id: Optional[str],
        top_k: int
    ) -> List[Tuple[SessionMemo, float]]:
        """
        搜索 Memos

        Args:
            query: 查询文本
            plan_id: Plan ID 过滤
            top_k: 返回数量

        Returns:
            (SessionMemo, score) 列表
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        results = []
        for memo in self.memo_store.values():
            # 过滤 Plan
            if plan_id and memo.plan_id != plan_id:
                continue

            # 计算得分
            score = 0.0
            search_text = memo.to_search_text().lower()

            # 完整查询匹配
            if query_lower in search_text:
                score += 0.5

            # 词项匹配
            for term in query_terms:
                if term in search_text:
                    score += 0.1

            # 实体匹配
            for entity in memo.key_entities:
                if query_lower in entity.lower() or entity.lower() in query_lower:
                    score += 0.2

            if score > 0:
                results.append((memo, min(score, 1.0)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def _reflect(
        self,
        query: str,
        memory: PreconstructedMemory
    ) -> Tuple[bool, float, str]:
        """
        LLM 评估结果充分性

        Args:
            query: 原始查询
            memory: 当前记忆状态

        Returns:
            (is_sufficient, confidence, feedback) 元组
        """
        # 基本检查
        if not memory.retrieved_memos and not memory.retrieved_pages:
            return False, 0.0, "未检索到任何结果"

        # 简单启发式：如果有一定数量的结果，认为可能充分
        if len(memory.retrieved_memos) >= 3 or len(memory.retrieved_pages) >= 5:
            base_confidence = 0.6
        else:
            base_confidence = 0.4

        # 如果没有模型，使用简单启发式
        if self.model is None:
            is_sufficient = base_confidence >= self.min_confidence
            return is_sufficient, base_confidence, "使用启发式评估"

        # 构建 prompt
        prompt = self._build_reflection_prompt(query, memory)

        try:
            response = await self._call_model(prompt)
            result = self._parse_reflection_response(response)

            is_sufficient = result.get("is_sufficient", base_confidence >= self.min_confidence)
            confidence = result.get("confidence", base_confidence)
            feedback = result.get("feedback", "")

            return is_sufficient, confidence, feedback

        except Exception as e:
            logger.warning(f"GAMResearcher: Reflection failed: {e}")
            is_sufficient = base_confidence >= self.min_confidence
            return is_sufficient, base_confidence, f"反思失败: {e}"

    def _build_reflection_prompt(self, query: str, memory: PreconstructedMemory) -> str:
        """构建反思 prompt"""
        # 构建 memo 摘要
        memo_summaries = []
        for i, memo in enumerate(memory.retrieved_memos[:5]):
            memo_summaries.append(f"{i+1}. [{memo.worker}] {memo.session_memo}")

        # 构建 page 摘要
        page_summaries = []
        for i, page in enumerate(memory.retrieved_pages[:5]):
            preview = page.content[:200] + "..." if len(page.content) > 200 else page.content
            page_summaries.append(f"{i+1}. [Phase {page.phase}] {preview}")

        return f"""你是研究评估助手。评估检索信息是否充分回答查询。

## 原始查询
{query}

## 检索到的 Memos ({len(memory.retrieved_memos)} 个)
{chr(10).join(memo_summaries) if memo_summaries else "无"}

## 检索到的 Pages ({len(memory.retrieved_pages)} 个)
{chr(10).join(page_summaries) if page_summaries else "无"}

## 任务
评估:
1. 信息是否足以回答查询?
2. 置信度 (0.0-1.0)?
3. 如果不足，缺少什么?

输出 JSON:
```json
{{
  "is_sufficient": true,
  "confidence": 0.85,
  "feedback": "需要更多关于 X 的信息",
  "reasoning": "..."
}}
```"""

    def _parse_reflection_response(self, response: str) -> Dict[str, Any]:
        """解析反思响应"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return {}

    async def _generate_context(
        self,
        query: str,
        memory: PreconstructedMemory
    ) -> str:
        """
        LLM 整合检索结果为连贯上下文

        Args:
            query: 原始查询
            memory: 当前记忆状态

        Returns:
            整合后的上下文文本
        """
        if not memory.retrieved_memos and not memory.retrieved_pages:
            return "未找到相关历史记忆。"

        # 如果没有模型，使用简单拼接
        if self.model is None:
            return self._simple_context_generation(query, memory)

        prompt = self._build_context_prompt(query, memory)

        try:
            response = await self._call_model(prompt)
            return response.strip() if response else self._simple_context_generation(query, memory)
        except Exception as e:
            logger.warning(f"GAMResearcher: Context generation failed: {e}")
            return self._simple_context_generation(query, memory)

    def _build_context_prompt(self, query: str, memory: PreconstructedMemory) -> str:
        """构建上下文生成 prompt"""
        # 收集内容
        contents = []

        for memo in memory.retrieved_memos[:10]:
            contents.append(f"[Session {memo.session_id}]\n{memo.session_memo}\nEntities: {', '.join(memo.key_entities)}")

        for page in memory.retrieved_pages[:10]:
            preview = page.content[:500] if len(page.content) > 500 else page.content
            contents.append(f"[Page {page.page_id} - Phase {page.phase}]\n{preview}")

        return f"""你是上下文整合助手。将检索到的历史记忆整合为连贯的上下文摘要。

## 当前目标
{query}

## 检索到的历史记忆
{chr(10).join(contents)}

## 任务
整合以上信息，生成一个连贯的上下文摘要，供后续任务使用。
摘要应该:
1. 突出与当前目标相关的信息
2. 总结之前已经完成的工作
3. 列出已处理过的文件/资源（避免重复操作）
4. 简洁明了，不超过 500 字

直接输出整合后的上下文，不要其他格式:"""

    def _simple_context_generation(self, query: str, memory: PreconstructedMemory) -> str:
        """简单的上下文拼接"""
        parts = [f"## 相关历史记忆 (查询: {query})\n"]

        if memory.retrieved_memos:
            parts.append("### 会话摘要")
            for memo in memory.retrieved_memos[:5]:
                parts.append(f"- [{memo.worker}] {memo.session_memo}")
                if memo.key_entities:
                    parts.append(f"  相关实体: {', '.join(memo.key_entities[:5])}")

        if memory.retrieved_pages:
            parts.append("\n### 详细记录")
            for page in memory.retrieved_pages[:5]:
                preview = page.content[:300] + "..." if len(page.content) > 300 else page.content
                parts.append(f"- [Phase {page.phase}] {preview}")

        return "\n".join(parts)

    async def _call_model(self, prompt: str) -> str:
        """调用 LLM 模型"""
        from agentscope.message import Msg

        messages = [Msg(name="user", content=prompt, role="user")]
        result = self.model(messages)

        if asyncio.iscoroutine(result):
            result = await result

        if isasyncgen(result):
            collected = None
            async for chunk in result:
                collected = chunk
            result = collected

        if result is None:
            return ""

        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                texts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        texts.append(block)
                return " ".join(texts)

        return str(result) if result else ""

    def quick_search(
        self,
        query: str,
        plan_id: Optional[str] = None,
        top_k: int = 10
    ) -> PreconstructedMemory:
        """
        快速搜索（不进行深度研究）

        Args:
            query: 查询文本
            plan_id: Plan ID 过滤
            top_k: 返回数量

        Returns:
            PreconstructedMemory 实例
        """
        memory = PreconstructedMemory(query=query)

        # 搜索 memos
        memo_results = self._search_memos(query, plan_id, top_k)
        memory.retrieved_memos = [m for m, _ in memo_results]

        # 搜索 pages
        pages_results = self.page_store.search_pages(query, top_k=top_k)
        memory.retrieved_pages = [p for p, _ in pages_results]

        memory.iterations = 1
        memory.is_sufficient = bool(memory.retrieved_memos or memory.retrieved_pages)
        memory.confidence_score = 0.5 if memory.is_sufficient else 0.0
        memory.context_summary = self._simple_context_generation(query, memory)

        return memory

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "researches_completed": self._researches_completed,
            "total_iterations": self._total_iterations,
            "avg_iterations": (
                self._total_iterations / self._researches_completed
                if self._researches_completed > 0 else 0
            ),
            "memo_store_size": len(self.memo_store),
            "retrievers": list(self.retrievers.keys())
        }
