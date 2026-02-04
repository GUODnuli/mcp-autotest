# -*- coding: utf-8 -*-
"""
Worker 执行器

根据 Worker 配置执行任务，支持 react/single/loop 三种执行模式。
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

from .worker_loader import WorkerConfig

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # 部分成功
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class WorkerTask:
    """Worker 任务定义"""

    # 任务标识
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None

    # 任务内容
    worker_name: str = ""
    task_description: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)

    # 执行上下文
    context: Dict[str, Any] = field(default_factory=dict)

    # 配置覆盖
    config_override: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "worker_name": self.worker_name,
            "task_description": self.task_description,
            "input_data": self.input_data,
            "context": self.context,
            "config_override": self.config_override,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerTask":
        """从字典创建实例"""
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            session_id=data.get("session_id"),
            worker_name=data.get("worker_name", ""),
            task_description=data.get("task_description", ""),
            input_data=data.get("input_data", {}),
            context=data.get("context", {}),
            config_override=data.get("config_override", {}),
        )


@dataclass
class WorkerResult:
    """Worker 执行结果"""

    # 结果标识
    task_id: str
    worker_name: str

    # 执行状态
    status: TaskStatus = TaskStatus.PENDING

    # 输出内容
    output: Any = None
    reasoning: str = ""

    # 执行统计
    iterations: int = 0
    token_usage: int = 0
    duration_ms: int = 0

    # 错误信息
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "worker_name": self.worker_name,
            "status": self.status.value,
            "output": self.output,
            "reasoning": self.reasoning,
            "iterations": self.iterations,
            "token_usage": self.token_usage,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerResult":
        """从字典创建实例"""
        return cls(
            task_id=data.get("task_id", ""),
            worker_name=data.get("worker_name", ""),
            status=TaskStatus(data.get("status", "pending")),
            output=data.get("output"),
            reasoning=data.get("reasoning", ""),
            iterations=data.get("iterations", 0),
            token_usage=data.get("token_usage", 0),
            duration_ms=data.get("duration_ms", 0),
            error=data.get("error"),
        )

    def is_success(self) -> bool:
        """是否执行成功"""
        return self.status in (TaskStatus.SUCCESS, TaskStatus.PARTIAL)


class WorkerRunner:
    """
    Worker 执行器

    根据 WorkerConfig 中的 mode 配置，选择不同的执行策略：
    - react: ReAct 模式，多轮推理+工具调用，自主决定何时完成
    - single: 单次执行，接收输入，调用工具序列，返回结果
    - loop: 循环执行直到满足条件或达到 max_iterations
    """

    def __init__(
        self,
        config: WorkerConfig,
        model: ChatModelBase,
        toolkit: Optional[Toolkit] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        初始化 Worker 执行器

        Args:
            config: Worker 配置
            model: LLM 模型实例
            toolkit: 工具集（可选，如果为 None 将创建空工具集）
            progress_callback: 进度回调函数，签名为 (event_type, data)
        """
        self.config = config
        self.model = model
        self.toolkit = toolkit or Toolkit()
        self.progress_callback = progress_callback

        # 运行状态
        self._cancelled = False
        self._current_task: Optional[WorkerTask] = None

    async def run(self, task: WorkerTask) -> WorkerResult:
        """
        执行任务

        根据配置的 mode 选择执行策略。

        Args:
            task: 要执行的任务

        Returns:
            执行结果
        """
        self._current_task = task
        self._cancelled = False

        # 应用配置覆盖
        effective_config = self._apply_config_override(task.config_override)

        start_time = time.time()
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.config.name,
            status=TaskStatus.RUNNING,
        )

        self._emit_progress("task_started", {
            "task_id": task.task_id,
            "worker_name": self.config.name,
            "mode": effective_config.mode,
        })

        try:
            # 根据执行模式选择策略
            if effective_config.mode == "react":
                result = await self._run_react(task, effective_config)
            elif effective_config.mode == "single":
                result = await self._run_single(task, effective_config)
            elif effective_config.mode == "loop":
                result = await self._run_loop(task, effective_config)
            else:
                result.status = TaskStatus.FAILED
                result.error = f"Unknown execution mode: {effective_config.mode}"

        except asyncio.TimeoutError:
            result.status = TaskStatus.TIMEOUT
            result.error = f"Task timed out after {effective_config.timeout}s"
            logger.warning("Worker %s task %s timed out", self.config.name, task.task_id)

        except asyncio.CancelledError:
            result.status = TaskStatus.CANCELLED
            result.error = "Task was cancelled"
            logger.info("Worker %s task %s was cancelled", self.config.name, task.task_id)

        except Exception as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)
            logger.exception("Worker %s task %s failed: %s", self.config.name, task.task_id, exc)

        finally:
            result.duration_ms = int((time.time() - start_time) * 1000)
            self._current_task = None

        self._emit_progress("task_completed", {
            "task_id": task.task_id,
            "status": result.status.value,
            "duration_ms": result.duration_ms,
        })

        return result

    def cancel(self) -> None:
        """取消当前任务"""
        self._cancelled = True

    async def _run_react(self, task: WorkerTask, config: WorkerConfig) -> WorkerResult:
        """
        ReAct 模式执行

        使用 ReActAgent 进行多轮推理和工具调用。

        Args:
            task: 任务
            config: 有效配置

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=config.name,
        )

        # 构建提示词
        prompt = self._build_task_prompt(task, config)

        # 创建 ReActAgent
        agent = ReActAgent(
            name=f"Worker_{config.name}",
            sys_prompt=config.system_prompt,
            model=self.model,
            toolkit=self.toolkit,
            memory=InMemoryMemory(),
            max_iters=config.max_iterations,
        )

        # 执行任务（带超时）
        async def execute():
            return await agent(Msg("user", prompt, "coordinator"))

        try:
            response = await asyncio.wait_for(
                execute(),
                timeout=config.timeout,
            )

            # 提取输出
            result.output = self._extract_output(response)
            result.reasoning = self._extract_reasoning(response)
            result.status = TaskStatus.SUCCESS

            # 统计信息
            if hasattr(agent, "token_usage"):
                result.token_usage = agent.token_usage
            if hasattr(agent, "iteration_count"):
                result.iterations = agent.iteration_count

        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)

        return result

    async def _run_single(self, task: WorkerTask, config: WorkerConfig) -> WorkerResult:
        """
        单次执行模式

        一次 LLM 调用，可能包含工具调用序列。

        Args:
            task: 任务
            config: 有效配置

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=config.name,
        )

        # 构建提示词
        prompt = self._build_task_prompt(task, config)

        # 单次模型调用
        try:
            messages = [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": prompt},
            ]

            response = await asyncio.wait_for(
                self._call_model(messages),
                timeout=config.timeout,
            )

            result.output = response
            result.status = TaskStatus.SUCCESS
            result.iterations = 1

        except asyncio.TimeoutError:
            raise
        except Exception as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)

        return result

    async def _run_loop(self, task: WorkerTask, config: WorkerConfig) -> WorkerResult:
        """
        循环执行模式

        迭代执行直到满足完成条件或达到 max_iterations。

        Args:
            task: 任务
            config: 有效配置

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=config.name,
        )

        iteration = 0
        outputs: List[Any] = []
        current_input = task.input_data.copy()

        start_time = time.time()
        timeout_remaining = config.timeout

        while iteration < config.max_iterations and not self._cancelled:
            iteration += 1

            self._emit_progress("iteration_started", {
                "task_id": task.task_id,
                "iteration": iteration,
                "max_iterations": config.max_iterations,
            })

            # 创建迭代任务
            iter_task = WorkerTask(
                task_id=f"{task.task_id}_iter_{iteration}",
                session_id=task.session_id,
                worker_name=task.worker_name,
                task_description=task.task_description,
                input_data=current_input,
                context={**task.context, "iteration": iteration, "previous_outputs": outputs},
            )

            # 执行单次迭代（使用 react 模式）
            iter_result = await asyncio.wait_for(
                self._run_react(iter_task, config),
                timeout=timeout_remaining,
            )

            outputs.append(iter_result.output)
            result.token_usage += iter_result.token_usage

            # 检查完成条件
            if self._check_completion(iter_result, task, config):
                result.status = TaskStatus.SUCCESS
                result.output = iter_result.output
                result.reasoning = iter_result.reasoning
                break

            # 更新输入（用于下一轮迭代）
            current_input = self._prepare_next_input(iter_result, current_input)

            # 更新剩余超时
            elapsed = time.time() - start_time
            timeout_remaining = config.timeout - elapsed
            if timeout_remaining <= 0:
                raise asyncio.TimeoutError()

        result.iterations = iteration

        if result.status != TaskStatus.SUCCESS:
            result.status = TaskStatus.PARTIAL
            result.output = outputs[-1] if outputs else None
            result.reasoning = f"Reached max iterations ({config.max_iterations})"

        return result

    async def _call_model(self, messages: List[Dict[str, str]]) -> str:
        """
        调用模型

        Args:
            messages: 消息列表

        Returns:
            模型响应文本
        """
        # 使用 AgentScope 模型的 __call__ 方法
        response = self.model(messages)
        if hasattr(response, "text"):
            return response.text
        return str(response)

    def _build_task_prompt(self, task: WorkerTask, config: WorkerConfig) -> str:
        """
        构建任务提示词

        Args:
            task: 任务
            config: 配置

        Returns:
            完整的任务提示词
        """
        parts = []

        # 任务描述
        if task.task_description:
            parts.append(f"## Task\n{task.task_description}")

        # 输入数据
        if task.input_data:
            parts.append(f"## Input\n```json\n{json.dumps(task.input_data, ensure_ascii=False, indent=2)}\n```")

        # 上下文信息
        if task.context:
            parts.append(f"## Context\n```json\n{json.dumps(task.context, ensure_ascii=False, indent=2)}\n```")

        return "\n\n".join(parts)

    def _apply_config_override(self, override: Dict[str, Any]) -> WorkerConfig:
        """
        应用配置覆盖

        Args:
            override: 覆盖配置

        Returns:
            合并后的配置
        """
        if not override:
            return self.config

        # 创建配置副本
        config_dict = self.config.to_dict()
        config_dict.update(override)
        return WorkerConfig.from_dict(config_dict)

    def _extract_output(self, response: Any) -> Any:
        """
        从响应中提取输出

        Args:
            response: Agent 响应

        Returns:
            提取的输出内容
        """
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict):
            return response.get("content", response)
        return str(response)

    def _extract_reasoning(self, response: Any) -> str:
        """
        从响应中提取推理过程

        Args:
            response: Agent 响应

        Returns:
            推理过程文本
        """
        if hasattr(response, "metadata"):
            return response.metadata.get("reasoning", "")
        return ""

    def _check_completion(
        self,
        iter_result: WorkerResult,
        task: WorkerTask,
        config: WorkerConfig,
    ) -> bool:
        """
        检查循环模式的完成条件

        Args:
            iter_result: 迭代结果
            task: 原始任务
            config: 配置

        Returns:
            是否满足完成条件
        """
        # 默认完成条件：结果中包含完成标记
        if iter_result.output and isinstance(iter_result.output, str):
            completion_markers = ["DONE", "COMPLETE", "FINISHED"]
            for marker in completion_markers:
                if marker in iter_result.output.upper():
                    return True

        # 检查自定义完成条件
        completion_func = config.extra.get("completion_check")
        if completion_func and callable(completion_func):
            return completion_func(iter_result, task)

        return False

    def _prepare_next_input(
        self,
        iter_result: WorkerResult,
        current_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        准备下一轮迭代的输入

        Args:
            iter_result: 当前迭代结果
            current_input: 当前输入

        Returns:
            下一轮迭代的输入
        """
        next_input = current_input.copy()
        next_input["previous_result"] = iter_result.output
        return next_input

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
