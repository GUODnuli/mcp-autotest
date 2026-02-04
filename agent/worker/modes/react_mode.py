# -*- coding: utf-8 -*-
"""
ReAct 执行模式

使用 ReActAgent 进行多轮推理和工具调用。
"""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

# Handle both package and standalone imports
try:
    from ..worker_loader import WorkerConfig
    from ..worker_runner import WorkerTask, WorkerResult, TaskStatus
except ImportError:
    from worker_loader import WorkerConfig
    from worker_runner import WorkerTask, WorkerResult, TaskStatus

logger = logging.getLogger(__name__)


class ReactModeExecutor:
    """
    ReAct 模式执行器

    使用 ReActAgent 进行多轮推理和工具调用，自主决定何时完成任务。
    """

    def __init__(
        self,
        config: WorkerConfig,
        model: ChatModelBase,
        toolkit: Toolkit,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        初始化执行器

        Args:
            config: Worker 配置
            model: LLM 模型实例
            toolkit: 工具集
            progress_callback: 进度回调
        """
        self.config = config
        self.model = model
        self.toolkit = toolkit
        self.progress_callback = progress_callback

    async def execute(self, task: WorkerTask) -> WorkerResult:
        """
        执行 ReAct 模式任务

        Args:
            task: 要执行的任务

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.config.name,
        )

        # 创建 ReActAgent
        agent = ReActAgent(
            name=f"Worker_{self.config.name}",
            sys_prompt=self.config.system_prompt,
            model=self.model,
            toolkit=self._filter_toolkit(),
            memory=InMemoryMemory(),
            max_iters=self.config.max_iterations,
        )

        # 构建任务提示
        prompt = self._build_prompt(task)

        self._emit_progress("react_started", {
            "task_id": task.task_id,
            "max_iterations": self.config.max_iterations,
        })

        try:
            # 执行 Agent（带超时）
            response = await asyncio.wait_for(
                self._run_agent(agent, prompt),
                timeout=self.config.timeout,
            )

            result.output = self._extract_output(response)
            result.reasoning = self._extract_reasoning(response)
            result.status = TaskStatus.SUCCESS

            # 获取统计信息
            if hasattr(agent, "token_usage"):
                result.token_usage = agent.token_usage
            if hasattr(agent, "iteration_count"):
                result.iterations = agent.iteration_count
            else:
                result.iterations = self._count_iterations(agent)

        except asyncio.TimeoutError:
            result.status = TaskStatus.TIMEOUT
            result.error = f"ReAct execution timed out after {self.config.timeout}s"
            raise
        except Exception as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)
            logger.exception("ReAct execution failed: %s", exc)

        self._emit_progress("react_completed", {
            "task_id": task.task_id,
            "status": result.status.value,
            "iterations": result.iterations,
        })

        return result

    async def _run_agent(self, agent: ReActAgent, prompt: str) -> Any:
        """
        运行 Agent

        Args:
            agent: ReActAgent 实例
            prompt: 任务提示

        Returns:
            Agent 响应
        """
        return await agent(Msg("user", prompt, "coordinator"))

    def _build_prompt(self, task: WorkerTask) -> str:
        """
        构建任务提示

        Args:
            task: 任务

        Returns:
            提示文本
        """
        import json

        parts = []

        # 任务描述
        if task.task_description:
            parts.append(f"## Task\n{task.task_description}")

        # 输入数据
        if task.input_data:
            parts.append(f"## Input\n```json\n{json.dumps(task.input_data, ensure_ascii=False, indent=2)}\n```")

        # 上下文
        if task.context:
            # 过滤掉过大的上下文
            filtered_context = {
                k: v for k, v in task.context.items()
                if not isinstance(v, (list, dict)) or len(str(v)) < 1000
            }
            if filtered_context:
                parts.append(f"## Context\n```json\n{json.dumps(filtered_context, ensure_ascii=False, indent=2)}\n```")

        return "\n\n".join(parts)

    def _filter_toolkit(self) -> Toolkit:
        """
        根据配置过滤工具集

        只保留配置中允许的工具。

        Returns:
            过滤后的工具集
        """
        if not self.config.tools:
            # 如果没有指定工具，返回完整工具集
            return self.toolkit

        # 创建新的工具集，只包含允许的工具
        filtered = Toolkit()
        allowed_tools = set(self.config.tools)

        for tool_name in self.toolkit.get_tool_names():
            if tool_name in allowed_tools:
                tool_func = self.toolkit.get_tool(tool_name)
                if tool_func:
                    filtered.register_tool_function(tool_func)

        return filtered

    def _extract_output(self, response: Any) -> Any:
        """
        提取输出内容

        Args:
            response: Agent 响应

        Returns:
            输出内容
        """
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict):
            return response.get("content", response)
        return str(response)

    def _extract_reasoning(self, response: Any) -> str:
        """
        提取推理过程

        Args:
            response: Agent 响应

        Returns:
            推理过程文本
        """
        if hasattr(response, "metadata"):
            metadata = response.metadata
            if isinstance(metadata, dict):
                return metadata.get("reasoning", "")
        return ""

    def _count_iterations(self, agent: ReActAgent) -> int:
        """
        统计迭代次数

        Args:
            agent: Agent 实例

        Returns:
            迭代次数
        """
        if hasattr(agent, "memory") and agent.memory:
            # 从 memory 中统计消息数量来估算迭代次数
            messages = agent.memory.get_memory()
            if isinstance(messages, list):
                # 每轮迭代大约包含 2-3 条消息
                return max(1, len(messages) // 2)
        return 1

    def _emit_progress(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发送进度事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if self.progress_callback:
            try:
                self.progress_callback(event_type, data)
            except Exception as exc:
                logger.warning("Progress callback failed: %s", exc)
