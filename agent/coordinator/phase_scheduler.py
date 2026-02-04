# -*- coding: utf-8 -*-
"""
Phase 调度器

管理 Phase 的执行顺序、依赖检查和并行调度。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

# Handle both package and standalone imports
try:
    from ..worker import WorkerResult
except ImportError:
    from worker import WorkerResult

try:
    from .task_planner import Phase, WorkerAssignment
except ImportError:
    from task_planner import Phase, WorkerAssignment

logger = logging.getLogger(__name__)


@dataclass
class PhaseResult:
    """Phase 执行结果"""

    phase_name: str
    status: str = "pending"  # pending, running, success, partial, failed
    worker_results: Dict[str, WorkerResult] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "phase_name": self.phase_name,
            "status": self.status,
            "worker_results": {
                name: result.to_dict()
                for name, result in self.worker_results.items()
            },
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseResult":
        """从字典创建"""
        # Handle both package and standalone imports
        try:
            from ..worker import WorkerResult as WR
        except ImportError:
            from worker import WorkerResult as WR
        worker_results = {
            name: WR.from_dict(result)
            for name, result in data.get("worker_results", {}).items()
        }
        return cls(
            phase_name=data.get("phase_name", ""),
            status=data.get("status", "pending"),
            worker_results=worker_results,
            error=data.get("error"),
        )

    def is_success(self) -> bool:
        """是否成功"""
        return self.status in ("success", "partial")

    def get_output(self, worker_name: Optional[str] = None) -> Any:
        """
        获取输出

        Args:
            worker_name: Worker 名称，为 None 时返回所有输出

        Returns:
            输出内容
        """
        if worker_name:
            result = self.worker_results.get(worker_name)
            return result.output if result else None

        return {
            name: result.output
            for name, result in self.worker_results.items()
        }


class PhaseScheduler:
    """
    Phase 调度器

    负责：
    1. 管理 Phase 执行顺序
    2. 检查 Phase 依赖
    3. 支持并行 Worker 调度
    4. 处理超时和取消
    """

    def __init__(
        self,
        max_parallel: int = 5,
        phase_timeout: int = 600,
    ):
        """
        初始化调度器

        Args:
            max_parallel: 最大并行 Worker 数
            phase_timeout: Phase 超时时间（秒）
        """
        self.max_parallel = max_parallel
        self.phase_timeout = phase_timeout

        # 执行状态
        self._completed_phases: Set[str] = set()
        self._phase_results: Dict[str, PhaseResult] = {}
        self._cancelled = False

        # 同步原语
        self._semaphore: Optional[asyncio.Semaphore] = None

    def reset(self) -> None:
        """重置调度器状态"""
        self._completed_phases = set()
        self._phase_results = {}
        self._cancelled = False

    def cancel(self) -> None:
        """取消执行"""
        self._cancelled = True

    def is_ready(self, phase: Phase) -> bool:
        """
        检查 Phase 是否就绪（依赖满足）

        Args:
            phase: Phase 定义

        Returns:
            是否就绪
        """
        for dep in phase.depends_on:
            if dep not in self._completed_phases:
                return False
            # 检查依赖是否成功
            dep_result = self._phase_results.get(dep)
            if dep_result and dep_result.status == "failed":
                logger.warning("Phase %s dependency %s failed", phase.name, dep)
                return False
        return True

    def mark_completed(self, phase: Phase, result: PhaseResult) -> None:
        """
        标记 Phase 完成

        Args:
            phase: Phase 定义
            result: 执行结果
        """
        phase_key = f"phase_{phase.phase}"
        self._completed_phases.add(phase_key)
        self._phase_results[phase_key] = result

    async def schedule_workers(
        self,
        phase: Phase,
        worker_executor: Callable[[WorkerAssignment], Any],
        context: Dict[str, Any],
    ) -> PhaseResult:
        """
        调度 Phase 中的 Workers

        Args:
            phase: Phase 定义
            worker_executor: Worker 执行函数
            context: 上下文

        Returns:
            Phase 执行结果
        """
        result = PhaseResult(phase_name=phase.name, status="running")

        if not phase.workers:
            result.status = "success"
            return result

        try:
            if phase.parallel:
                # 并行执行
                worker_results = await self._execute_parallel(
                    phase.workers,
                    worker_executor,
                    context,
                )
            else:
                # 顺序执行
                worker_results = await self._execute_sequential(
                    phase.workers,
                    worker_executor,
                    context,
                )

            result.worker_results = worker_results
            result.status = self._determine_status(worker_results)

        except asyncio.TimeoutError:
            result.status = "failed"
            result.error = f"Phase timed out after {self.phase_timeout}s"

        except asyncio.CancelledError:
            result.status = "failed"
            result.error = "Phase was cancelled"
            raise

        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            logger.exception("Phase %s execution failed: %s", phase.name, exc)

        return result

    async def _execute_parallel(
        self,
        assignments: List[WorkerAssignment],
        executor: Callable[[WorkerAssignment], Any],
        context: Dict[str, Any],
    ) -> Dict[str, WorkerResult]:
        """
        并行执行 Workers

        Args:
            assignments: Worker 分配列表
            executor: 执行函数
            context: 上下文

        Returns:
            Worker 结果映射
        """
        self._semaphore = asyncio.Semaphore(self.max_parallel)

        async def limited_execute(assignment: WorkerAssignment) -> tuple[str, Any]:
            async with self._semaphore:
                if self._cancelled:
                    raise asyncio.CancelledError()
                result = await executor(assignment)
                return assignment.worker, result

        # 创建任务
        tasks = [
            asyncio.create_task(limited_execute(a))
            for a in assignments
        ]

        # 等待所有任务完成（带超时）
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.phase_timeout,
            )
        except asyncio.TimeoutError:
            # 取消未完成的任务
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

        # 处理结果
        worker_results = {}
        for i, result in enumerate(results):
            assignment = assignments[i]
            if isinstance(result, Exception):
                worker_results[assignment.worker] = self._create_error_result(
                    assignment,
                    str(result),
                )
            else:
                name, worker_result = result
                worker_results[name] = worker_result

        return worker_results

    async def _execute_sequential(
        self,
        assignments: List[WorkerAssignment],
        executor: Callable[[WorkerAssignment], Any],
        context: Dict[str, Any],
    ) -> Dict[str, WorkerResult]:
        """
        顺序执行 Workers

        Args:
            assignments: Worker 分配列表
            executor: 执行函数
            context: 上下文

        Returns:
            Worker 结果映射
        """
        worker_results = {}

        for assignment in assignments:
            if self._cancelled:
                raise asyncio.CancelledError()

            try:
                result = await asyncio.wait_for(
                    executor(assignment),
                    timeout=self.phase_timeout,
                )
                worker_results[assignment.worker] = result
            except asyncio.TimeoutError:
                worker_results[assignment.worker] = self._create_error_result(
                    assignment,
                    f"Worker timed out after {self.phase_timeout}s",
                )
            except Exception as exc:
                worker_results[assignment.worker] = self._create_error_result(
                    assignment,
                    str(exc),
                )

        return worker_results

    def _determine_status(self, worker_results: Dict[str, WorkerResult]) -> str:
        """
        确定 Phase 状态

        Args:
            worker_results: Worker 结果

        Returns:
            状态字符串
        """
        if not worker_results:
            return "failed"

        statuses = []
        for result in worker_results.values():
            if hasattr(result, "status"):
                status = result.status
                if hasattr(status, "value"):
                    status = status.value
                statuses.append(status)
            else:
                statuses.append("unknown")

        if all(s == "success" for s in statuses):
            return "success"
        elif all(s in ("failed", "timeout", "error") for s in statuses):
            return "failed"
        elif any(s == "success" for s in statuses):
            return "partial"
        else:
            return "failed"

    def _create_error_result(
        self,
        assignment: WorkerAssignment,
        error: str,
    ) -> WorkerResult:
        """
        创建错误结果

        Args:
            assignment: Worker 分配
            error: 错误信息

        Returns:
            错误结果
        """
        from ..worker import WorkerResult, TaskStatus

        return WorkerResult(
            task_id="",
            worker_name=assignment.worker,
            status=TaskStatus.FAILED,
            error=error,
        )

    def get_execution_order(self, phases: List[Phase]) -> List[Phase]:
        """
        获取执行顺序

        根据依赖关系对 Phases 排序。

        Args:
            phases: Phase 列表

        Returns:
            排序后的 Phase 列表
        """
        # 构建依赖图
        phase_map = {f"phase_{p.phase}": p for p in phases}
        in_degree = {f"phase_{p.phase}": len(p.depends_on) for p in phases}
        graph = {f"phase_{p.phase}": [] for p in phases}

        for phase in phases:
            phase_key = f"phase_{phase.phase}"
            for dep in phase.depends_on:
                if dep in graph:
                    graph[dep].append(phase_key)

        # 拓扑排序
        queue = [k for k, v in in_degree.items() if v == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(phase_map[node])

            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(phases):
            logger.warning("Dependency cycle detected, using original order")
            return phases

        return result

    def get_ready_phases(self, phases: List[Phase]) -> List[Phase]:
        """
        获取就绪的 Phases

        Args:
            phases: 所有 Phase 列表

        Returns:
            就绪的 Phase 列表
        """
        ready = []
        for phase in phases:
            phase_key = f"phase_{phase.phase}"
            if phase_key not in self._completed_phases and self.is_ready(phase):
                ready.append(phase)
        return ready
