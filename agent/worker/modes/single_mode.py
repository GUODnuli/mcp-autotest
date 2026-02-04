# -*- coding: utf-8 -*-
"""
Single 执行模式

单次 LLM 调用，返回工具调用序列或直接结果。
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

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


class SingleModeExecutor:
    """
    单次执行模式执行器

    一次 LLM 调用，可能返回工具调用序列。
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
        执行单次任务

        Args:
            task: 要执行的任务

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.config.name,
            iterations=1,
        )

        self._emit_progress("single_started", {"task_id": task.task_id})

        try:
            # 构建消息
            messages = self._build_messages(task)

            # 调用模型（带超时）
            response = await asyncio.wait_for(
                self._call_model(messages),
                timeout=self.config.timeout,
            )

            # 处理响应
            if self._has_tool_calls(response):
                # 执行工具调用序列
                result.output = await self._execute_tool_calls(response)
            else:
                # 直接返回文本结果
                result.output = self._extract_text(response)

            result.status = TaskStatus.SUCCESS

            # 统计 token 使用
            if hasattr(response, "usage"):
                result.token_usage = response.usage.get("total_tokens", 0)

        except asyncio.TimeoutError:
            result.status = TaskStatus.TIMEOUT
            result.error = f"Single execution timed out after {self.config.timeout}s"
            raise
        except Exception as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)
            logger.exception("Single execution failed: %s", exc)

        self._emit_progress("single_completed", {
            "task_id": task.task_id,
            "status": result.status.value,
        })

        return result

    def _build_messages(self, task: WorkerTask) -> List[Dict[str, Any]]:
        """
        构建消息列表

        Args:
            task: 任务

        Returns:
            消息列表
        """
        import json

        # 系统消息
        messages = [
            {"role": "system", "content": self.config.system_prompt}
        ]

        # 构建用户消息
        user_content_parts = []

        if task.task_description:
            user_content_parts.append(f"## Task\n{task.task_description}")

        if task.input_data:
            user_content_parts.append(
                f"## Input\n```json\n{json.dumps(task.input_data, ensure_ascii=False, indent=2)}\n```"
            )

        if task.context:
            user_content_parts.append(
                f"## Context\n```json\n{json.dumps(task.context, ensure_ascii=False, indent=2)}\n```"
            )

        messages.append({
            "role": "user",
            "content": "\n\n".join(user_content_parts),
        })

        return messages

    async def _call_model(self, messages: List[Dict[str, Any]]) -> Any:
        """
        调用模型

        Args:
            messages: 消息列表

        Returns:
            模型响应
        """
        # 使用 AgentScope 模型调用
        response = self.model(messages)
        return response

    def _has_tool_calls(self, response: Any) -> bool:
        """
        检查响应是否包含工具调用

        Args:
            response: 模型响应

        Returns:
            是否包含工具调用
        """
        if hasattr(response, "tool_calls"):
            return bool(response.tool_calls)
        if isinstance(response, dict):
            return bool(response.get("tool_calls"))
        return False

    async def _execute_tool_calls(self, response: Any) -> Dict[str, Any]:
        """
        执行工具调用序列

        Args:
            response: 包含工具调用的响应

        Returns:
            工具调用结果
        """
        tool_calls = getattr(response, "tool_calls", [])
        if isinstance(response, dict):
            tool_calls = response.get("tool_calls", [])

        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})

            if isinstance(tool_args, str):
                import json
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    tool_args = {"raw": tool_args}

            self._emit_progress("tool_call", {
                "tool_name": tool_name,
                "arguments": tool_args,
            })

            try:
                # 获取工具函数
                tool_func = self.toolkit.get_tool(tool_name)
                if tool_func:
                    # 执行工具
                    if asyncio.iscoroutinefunction(tool_func):
                        tool_result = await tool_func(**tool_args)
                    else:
                        tool_result = tool_func(**tool_args)

                    results.append({
                        "tool": tool_name,
                        "status": "success",
                        "result": tool_result,
                    })
                else:
                    results.append({
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Tool not found: {tool_name}",
                    })

            except Exception as exc:
                results.append({
                    "tool": tool_name,
                    "status": "error",
                    "error": str(exc),
                })

        return {
            "tool_calls": results,
            "success_count": sum(1 for r in results if r["status"] == "success"),
            "error_count": sum(1 for r in results if r["status"] == "error"),
        }

    def _extract_text(self, response: Any) -> str:
        """
        提取文本响应

        Args:
            response: 模型响应

        Returns:
            文本内容
        """
        if hasattr(response, "text"):
            return response.text
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict):
            return response.get("content", str(response))
        return str(response)

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
