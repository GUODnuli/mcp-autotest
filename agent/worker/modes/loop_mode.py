# -*- coding: utf-8 -*-
"""
Loop 执行模式

循环执行直到满足完成条件或达到最大迭代次数。
"""
import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

# Handle both package and standalone imports
try:
    from ..worker_loader import WorkerConfig
    from ..worker_runner import WorkerTask, WorkerResult, TaskStatus
    from .react_mode import ReactModeExecutor
except ImportError:
    from worker_loader import WorkerConfig
    from worker_runner import WorkerTask, WorkerResult, TaskStatus
    from react_mode import ReactModeExecutor

logger = logging.getLogger(__name__)


class LoopModeExecutor:
    """
    循环执行模式执行器

    迭代执行直到满足完成条件或达到 max_iterations。
    每次迭代使用 ReAct 模式执行，结果传递给下一轮。
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

        # 内部使用 ReactModeExecutor 执行每轮迭代
        self._react_executor = ReactModeExecutor(
            config=config,
            model=model,
            toolkit=toolkit,
            progress_callback=progress_callback,
        )

    async def execute(self, task: WorkerTask) -> WorkerResult:
        """
        执行循环任务

        Args:
            task: 要执行的任务

        Returns:
            执行结果
        """
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.config.name,
        )

        iteration = 0
        outputs: List[Any] = []
        current_input = task.input_data.copy()
        total_tokens = 0

        start_time = time.time()
        timeout_remaining = self.config.timeout

        self._emit_progress("loop_started", {
            "task_id": task.task_id,
            "max_iterations": self.config.max_iterations,
        })

        try:
            while iteration < self.config.max_iterations:
                iteration += 1
                elapsed = time.time() - start_time
                timeout_remaining = self.config.timeout - elapsed

                if timeout_remaining <= 0:
                    raise asyncio.TimeoutError()

                self._emit_progress("iteration_started", {
                    "task_id": task.task_id,
                    "iteration": iteration,
                    "max_iterations": self.config.max_iterations,
                    "timeout_remaining": int(timeout_remaining),
                })

                # 创建迭代任务
                iter_task = self._create_iteration_task(
                    task=task,
                    iteration=iteration,
                    current_input=current_input,
                    previous_outputs=outputs,
                )

                # 执行迭代
                iter_result = await asyncio.wait_for(
                    self._react_executor.execute(iter_task),
                    timeout=timeout_remaining,
                )

                # 收集结果
                outputs.append(iter_result.output)
                total_tokens += iter_result.token_usage

                self._emit_progress("iteration_completed", {
                    "task_id": task.task_id,
                    "iteration": iteration,
                    "status": iter_result.status.value,
                })

                # 检查完成条件
                if self._check_completion(iter_result, task, iteration):
                    result.status = TaskStatus.SUCCESS
                    result.output = iter_result.output
                    result.reasoning = iter_result.reasoning
                    break

                # 检查失败
                if iter_result.status == TaskStatus.FAILED:
                    result.status = TaskStatus.PARTIAL
                    result.error = f"Iteration {iteration} failed: {iter_result.error}"
                    result.output = outputs[-2] if len(outputs) > 1 else None
                    break

                # 准备下一轮输入
                current_input = self._prepare_next_input(
                    iter_result=iter_result,
                    current_input=current_input,
                    iteration=iteration,
                )

        except asyncio.TimeoutError:
            result.status = TaskStatus.TIMEOUT
            result.error = f"Loop timed out after {self.config.timeout}s at iteration {iteration}"
            if outputs:
                result.output = outputs[-1]
            raise

        except asyncio.CancelledError:
            result.status = TaskStatus.CANCELLED
            result.error = f"Loop cancelled at iteration {iteration}"
            if outputs:
                result.output = outputs[-1]
            raise

        # 如果未成功，设置为部分完成
        if result.status == TaskStatus.PENDING:
            result.status = TaskStatus.PARTIAL
            result.output = outputs[-1] if outputs else None
            result.reasoning = f"Reached max iterations ({self.config.max_iterations}) without completion"

        result.iterations = iteration
        result.token_usage = total_tokens

        self._emit_progress("loop_completed", {
            "task_id": task.task_id,
            "status": result.status.value,
            "total_iterations": iteration,
            "total_tokens": total_tokens,
        })

        return result

    def _create_iteration_task(
        self,
        task: WorkerTask,
        iteration: int,
        current_input: Dict[str, Any],
        previous_outputs: List[Any],
    ) -> WorkerTask:
        """
        创建迭代任务

        Args:
            task: 原始任务
            iteration: 当前迭代次数
            current_input: 当前输入
            previous_outputs: 之前的输出列表

        Returns:
            迭代任务
        """
        # 构建迭代上下文
        iter_context = {
            **task.context,
            "iteration": iteration,
            "max_iterations": self.config.max_iterations,
            "is_first_iteration": iteration == 1,
        }

        # 添加历史信息（限制大小）
        if previous_outputs:
            # 只保留最近 3 轮的输出
            recent_outputs = previous_outputs[-3:]
            iter_context["recent_outputs"] = recent_outputs
            iter_context["total_previous_iterations"] = len(previous_outputs)

        # 增强任务描述
        enhanced_description = task.task_description
        if iteration > 1:
            enhanced_description = f"""[Iteration {iteration}/{self.config.max_iterations}]

{task.task_description}

Note: This is iteration {iteration}. Review previous results and continue the work.
If the task is complete, include "DONE" in your response.
"""

        return WorkerTask(
            task_id=f"{task.task_id}_iter_{iteration}",
            session_id=task.session_id,
            worker_name=task.worker_name,
            task_description=enhanced_description,
            input_data=current_input,
            context=iter_context,
        )

    def _check_completion(
        self,
        iter_result: WorkerResult,
        task: WorkerTask,
        iteration: int,
    ) -> bool:
        """
        检查完成条件

        Args:
            iter_result: 迭代结果
            task: 原始任务
            iteration: 当前迭代次数

        Returns:
            是否完成
        """
        # 检查状态
        if iter_result.status not in (TaskStatus.SUCCESS, TaskStatus.PARTIAL):
            return False

        # 检查输出中的完成标记
        output = iter_result.output
        if output:
            output_str = str(output).upper()
            completion_markers = ["DONE", "COMPLETE", "FINISHED", "TASK_COMPLETED"]
            for marker in completion_markers:
                if marker in output_str:
                    return True

        # 检查自定义完成函数
        completion_func = self.config.extra.get("completion_check")
        if completion_func and callable(completion_func):
            try:
                return completion_func(iter_result, task, iteration)
            except Exception as exc:
                logger.warning("Completion check function failed: %s", exc)

        # 检查上下文中的完成条件
        completion_criteria = task.context.get("completion_criteria")
        if completion_criteria and callable(completion_criteria):
            try:
                return completion_criteria(iter_result)
            except Exception as exc:
                logger.warning("Completion criteria check failed: %s", exc)

        return False

    def _prepare_next_input(
        self,
        iter_result: WorkerResult,
        current_input: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """
        准备下一轮迭代的输入

        Args:
            iter_result: 当前迭代结果
            current_input: 当前输入
            iteration: 当前迭代次数

        Returns:
            下一轮输入
        """
        next_input = current_input.copy()

        # 添加上一轮结果
        next_input["previous_result"] = iter_result.output
        next_input["previous_reasoning"] = iter_result.reasoning
        next_input["iteration"] = iteration + 1

        # 检查自定义输入准备函数
        prepare_func = self.config.extra.get("prepare_next_input")
        if prepare_func and callable(prepare_func):
            try:
                custom_input = prepare_func(iter_result, current_input, iteration)
                if isinstance(custom_input, dict):
                    next_input.update(custom_input)
            except Exception as exc:
                logger.warning("Prepare next input function failed: %s", exc)

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
