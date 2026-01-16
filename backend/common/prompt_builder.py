"""
Prompt 构建器

用于组装 System Prompt、User Query 和 JSON Schema
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from backend.common.logger import get_logger


class PromptBuilder:
    """Prompt 构建器"""
    
    def __init__(self, prompts_dir: Optional[str] = None):
        """
        初始化 Prompt 构建器
        
        Args:
            prompts_dir: Prompts 目录路径，默认为 backend/prompts
        """
        self.logger = get_logger()
        
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            # 默认路径：backend/prompts
            backend_dir = Path(__file__).parent.parent
            self.prompts_dir = backend_dir / "prompts"
        
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts 目录不存在: {self.prompts_dir}")
        
        self.logger.debug(f"PromptBuilder 初始化 | prompts_dir: {self.prompts_dir}")
    
    def load_prompt_template(self, template_name: str) -> str:
        """
        加载 prompt 模板文件
        
        Args:
            template_name: 模板名称（不含扩展名）
            
        Returns:
            模板内容
        """
        template_path = self.prompts_dir / f"{template_name}.txt"
        
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt 模板不存在: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.logger.debug(f"加载 Prompt 模板 | 模板: {template_name} | 长度: {len(content)}")
        return content
    
    def load_json_schema(self, schema_name: str) -> Dict[str, Any]:
        """
        加载 JSON Schema 文件
        
        Args:
            schema_name: Schema 名称（不含扩展名）
            
        Returns:
            Schema 字典
        """
        schema_path = self.prompts_dir / f"{schema_name}.json"
        
        if not schema_path.exists():
            raise FileNotFoundError(f"JSON Schema 不存在: {schema_path}")
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        self.logger.debug(f"加载 JSON Schema | schema: {schema_name}")
        return schema
    
    def build_word_to_interfaces_prompt(
        self,
        word_content: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> Dict[str, str]:
        """
        构建 Word 文档转接口规范的 Prompt
        
        Args:
            word_content: Word 文档内容（结构化）
            business_context: 业务上下文（可选）
            
        Returns:
            包含 system_prompt 和 user_query 的字典
        """
        # 加载 System Prompt 模板
        system_prompt = self.load_prompt_template("word_to_interfaces")
        
        # 加载接口 Schema
        interface_schema = self.load_json_schema("interface_schema")
        
        # 添加 Schema 到 System Prompt
        system_prompt += "\n\n# 输出格式 (JSON Schema)\n```json\n"
        system_prompt += json.dumps(interface_schema, ensure_ascii=False, indent=2)
        system_prompt += "\n```"
        
        # 构建 User Query
        user_query = "# 业务需求文档\n\n"
        
        # 添加业务上下文
        if business_context:
            user_query += f"## 业务背景\n{business_context}\n\n"
        
        # 添加文档标题
        if word_content.get("headings"):
            user_query += "## 文档结构\n"
            for heading in word_content["headings"][:10]:  # 最多10个标题
                level = heading.get("heading_level", "1")
                text = heading.get("text", "")
                user_query += f"{'#' * int(level)} {text}\n"
            user_query += "\n"
        
        # 添加段落内容
        if word_content.get("paragraphs"):
            user_query += "## 文档内容\n"
            for para in word_content["paragraphs"]:
                text = para.get("text", "").strip()
                if text:
                    user_query += f"{text}\n\n"
        
        # 添加表格内容
        if word_content.get("tables"):
            user_query += "## 数据表格\n"
            for idx, table in enumerate(word_content["tables"], 1):
                user_query += f"\n### 表格 {idx}\n"
                table_data = table.get("data", [])
                if table_data:
                    # 渲染为 Markdown 表格
                    if len(table_data) > 0:
                        # 表头
                        user_query += "| " + " | ".join(table_data[0]) + " |\n"
                        user_query += "|" + "|".join(["---"] * len(table_data[0])) + "|\n"
                        # 数据行
                        for row in table_data[1:]:
                            user_query += "| " + " | ".join(row) + " |\n"
                    user_query += "\n"
        
        user_query += "\n# 任务\n请根据以上业务需求文档，提取并定义完整的 API 接口规范，输出 JSON 格式。"
        
        self.logger.info(
            f"构建 Word→接口 Prompt 完成 | "
            f"system长度: {len(system_prompt)} | "
            f"user长度: {len(user_query)}"
        )
        
        return {
            "system_prompt": system_prompt,
            "user_query": user_query
        }
    
    def build_generate_testcases_prompt(
        self,
        interface_spec: Dict[str, Any],
        strategies: list = None,
        count_per_strategy: int = 3,
        enhanced_context: Optional[str] = None
    ) -> Dict[str, str]:
        """
        构建生成测试用例的 Prompt
        
        Args:
            interface_spec: 接口规范
            strategies: 测试策略列表
            count_per_strategy: 每策略用例数
            enhanced_context: 增强上下文
            
        Returns:
            包含 system_prompt 和 user_query 的字典
        """
        if strategies is None:
            strategies = ["positive", "negative"]
        
        # 加载 System Prompt 模板
        system_prompt = self.load_prompt_template("generate_testcases")
        
        # 加载测试用例 Schema
        testcase_schema = self.load_json_schema("testcase_schema")
        
        # 添加 Schema 到 System Prompt
        system_prompt += "\n\n# 输出格式 (JSON Schema)\n```json\n"
        system_prompt += json.dumps(testcase_schema, ensure_ascii=False, indent=2)
        system_prompt += "\n```"
        
        # 构建 User Query
        user_query = "# 接口规范\n\n"
        user_query += f"**接口名称**: {interface_spec.get('name', '')}\n"
        user_query += f"**请求路径**: {interface_spec.get('method', '')} {interface_spec.get('path', '')}\n"
        user_query += f"**功能描述**: {interface_spec.get('description', '')}\n\n"
        
        # 参数信息
        parameters = interface_spec.get("parameters", [])
        if parameters:
            user_query += "## 请求参数\n```json\n"
            user_query += json.dumps(parameters, ensure_ascii=False, indent=2)
            user_query += "\n```\n\n"
        
        # 请求体
        request_body = interface_spec.get("request_body")
        if request_body:
            user_query += "## 请求体\n```json\n"
            user_query += json.dumps(request_body, ensure_ascii=False, indent=2)
            user_query += "\n```\n\n"
        
        # 响应定义
        responses = interface_spec.get("responses")
        if responses:
            user_query += "## 响应定义\n```json\n"
            user_query += json.dumps(responses, ensure_ascii=False, indent=2)
            user_query += "\n```\n\n"
        
        # 增强上下文
        if enhanced_context:
            user_query += f"## 参考信息\n{enhanced_context}\n\n"
        
        # 测试要求
        user_query += f"# 测试要求\n"
        user_query += f"- 测试策略: {', '.join(strategies)}\n"
        user_query += f"- 每种策略生成 {count_per_strategy} 个测试用例\n"
        user_query += f"- 输出格式: JSON (遵循上述 Schema)\n"
        
        self.logger.info(
            f"构建测试用例生成 Prompt 完成 | "
            f"system长度: {len(system_prompt)} | "
            f"user长度: {len(user_query)}"
        )
        
        return {
            "system_prompt": system_prompt,
            "user_query": user_query
        }
    
    def estimate_token_count(self, text: str) -> int:
        """
        估算文本 token 数量（粗略估计）
        
        Args:
            text: 文本内容
            
        Returns:
            token 数量估计值
        """
        # 简单估算：中文1字符≈1.5token，英文1单词≈1.3token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_words = len([w for w in text.split() if w.isalpha()])
        other_chars = len(text) - chinese_chars
        
        estimated_tokens = int(chinese_chars * 1.5 + english_words * 1.3 + other_chars * 0.5)
        return estimated_tokens


def get_prompt_builder(prompts_dir: Optional[str] = None) -> PromptBuilder:
    """
    获取 PromptBuilder 实例（工厂函数）
    
    Args:
        prompts_dir: Prompts 目录路径
        
    Returns:
        PromptBuilder 实例
    """
    return PromptBuilder(prompts_dir)
