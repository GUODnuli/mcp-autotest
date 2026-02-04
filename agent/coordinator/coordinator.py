# -*- coding: utf-8 -*-
"""
Coordinator (主协调器)

负责任务接收、分解、Worker 调度、结果聚合的核心模块。
"""
import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import yaml
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit

# Handle both package and standalone imports
try:
    from ..worker import WorkerConfig, WorkerLoader, WorkerTask, WorkerResult, WorkerRunner, TaskStatus
except ImportError:
    from worker import WorkerConfig, WorkerLoader, WorkerTask, WorkerResult, WorkerRunner, TaskStatus

if TYPE_CHECKING:
    from .task_planner import Phase

try:
    from .task_planner import TaskPlanner, ExecutionPlan
    from .phase_scheduler import PhaseScheduler, PhaseResult
    from .result_evaluator import ResultEvaluator
    from .error_recovery import ErrorRecovery, RecoveryAction
except ImportError:
    from task_planner import TaskPlanner, ExecutionPlan
    from phase_scheduler import PhaseScheduler, PhaseResult
    from result_evaluator import ResultEvaluator
    from error_recovery import ErrorRecovery, RecoveryAction

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorConfig:
    """Coordinator 配置"""

    # 目录配置
    agents_dir: Path = field(default_factory=lambda: Path(".testagent/agents"))
    skills_dir: Path = field(default_factory=lambda: Path(".testagent/skills"))
    prompts_dir: Path = field(default_factory=lambda: Path("prompts/coordinator"))

    # 执行配置
    max_phases: int = 10
    max_retries: int = 3
    timeout: int = 1800  # 30 分钟

    # 并行配置
    max_parallel_workers: int = 5

    # 模型配置
    planner_model: Optional[str] = None  # 用于任务规划的模型

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agents_dir": str(self.agents_dir),
            "skills_dir": str(self.skills_dir),
            "prompts_dir": str(self.prompts_dir),
            "max_phases": self.max_phases,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "max_parallel_workers": self.max_parallel_workers,
            "planner_model": self.planner_model,
        }


@dataclass
class CoordinatorState:
    """Coordinator 运行状态"""

    session_id: str
    task_id: str
    objective: str

    # 执行状态
    current_phase: int = 0
    status: str = "pending"  # pending, running, completed, failed

    # 计划
    plan: Optional[ExecutionPlan] = None

    # 结果收集
    phase_results: List[PhaseResult] = field(default_factory=list)
    worker_results: Dict[str, WorkerResult] = field(default_factory=dict)

    # 上下文
    context: Dict[str, Any] = field(default_factory=dict)


class Coordinator:
    """
    主协调器

    负责：
    1. 加载可用 Workers 和 Skills
    2. 接收用户请求，使用 LLM 分解任务
    3. 调度 Workers 执行任务
    4. 聚合结果，判断是否完成
    5. 错误恢复和计划调整
    """

    def __init__(
        self,
        model: ChatModelBase,
        toolkit: Toolkit,
        config: Optional[CoordinatorConfig] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        初始化 Coordinator

        Args:
            model: LLM 模型实例
            toolkit: 工具集
            config: Coordinator 配置
            progress_callback: 进度回调函数
        """
        self.model = model
        self.toolkit = toolkit
        self.config = config or CoordinatorConfig()
        self.progress_callback = progress_callback

        # 初始化子组件
        self._worker_loader = WorkerLoader(self.config.agents_dir)
        self._task_planner = TaskPlanner(model, self.config.prompts_dir)
        self._phase_scheduler = PhaseScheduler(
            max_parallel=self.config.max_parallel_workers
        )
        self._result_evaluator = ResultEvaluator(model)
        self._error_recovery = ErrorRecovery(model)

        # 运行状态
        self._state: Optional[CoordinatorState] = None
        self._workers: Dict[str, WorkerConfig] = {}
        self._skills: List[Dict[str, Any]] = []

        # 取消标志
        self._cancelled = False

    async def initialize(self) -> None:
        """
        初始化 Coordinator

        加载 Workers 和 Skills。
        """
        # 加载 Workers
        self._workers = self._worker_loader.load()
        logger.info("Loaded %d workers", len(self._workers))

        # 加载 Skills（从 toolkit 获取已注册的 skills）
        self._skills = self._load_skills()
        logger.info("Loaded %d skills", len(self._skills))

        self._emit_progress("coordinator_initialized", {
            "workers": list(self._workers.keys()),
            "skills": [s.get("name") for s in self._skills],
        })

    async def execute(
        self,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行任务

        Args:
            objective: 任务目标描述
            context: 初始上下文
            session_id: 会话 ID

        Returns:
            执行结果
        """
        # 初始化状态
        self._state = CoordinatorState(
            session_id=session_id or str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            objective=objective,
            context=context or {},
            status="running",
        )

        self._cancelled = False

        self._emit_progress("task_started", {
            "task_id": self._state.task_id,
            "session_id": self._state.session_id,
            "objective": objective,
        })

        try:
            # 阶段 1: 任务分解
            plan = await self._plan_task(objective, context)
            self._state.plan = plan

            self._emit_progress("plan_created", {
                "task_id": self._state.task_id,
                "phases": len(plan.phases),
                "plan": plan.to_dict(),
            })

            # 阶段 2: 执行计划
            result = await self._execute_plan(plan)

            # 阶段 3: 判断完成
            if self._is_task_complete(result):
                self._state.status = "completed"
            else:
                # 可能需要生成补充计划
                supplementary_result = await self._handle_incomplete(result)
                if supplementary_result:
                    result = self._merge_results(result, supplementary_result)

            self._emit_progress("task_completed", {
                "task_id": self._state.task_id,
                "status": self._state.status,
            })

            return {
                "task_id": self._state.task_id,
                "status": self._state.status,
                "objective": objective,
                "result": result,
                "phase_results": [pr.to_dict() for pr in self._state.phase_results],
            }

        except asyncio.CancelledError:
            self._state.status = "cancelled"
            raise
        except Exception as exc:
            self._state.status = "failed"
            logger.exception("Coordinator execution failed: %s", exc)
            return {
                "task_id": self._state.task_id,
                "status": "failed",
                "error": str(exc),
            }

    def cancel(self) -> None:
        """取消执行"""
        self._cancelled = True
        if self._phase_scheduler:
            self._phase_scheduler.cancel()

    async def _plan_task(
        self,
        objective: str,
        context: Optional[Dict[str, Any]],
    ) -> ExecutionPlan:
        """
        任务分解

        使用 LLM 分析目标，生成执行计划。

        Args:
            objective: 任务目标
            context: 上下文

        Returns:
            执行计划
        """
        self._emit_progress("planning_started", {
            "task_id": self._state.task_id,
            "objective": objective,
        })

        # 获取 Worker 和 Skill 摘要
        worker_summary = self._worker_loader.get_worker_summary()
        skill_summary = self._skills

        # 调用 TaskPlanner
        plan = await self._task_planner.create_plan(
            objective=objective,
            context=context or {},
            available_workers=worker_summary,
            available_skills=skill_summary,
        )

        self._emit_progress("planning_completed", {
            "task_id": self._state.task_id,
            "phases": len(plan.phases),
        })

        return plan

    async def _execute_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """
        执行计划

        按 Phase 顺序执行，支持并行 Worker 调度。

        Args:
            plan: 执行计划

        Returns:
            聚合结果
        """
        results = {}

        for phase_index, phase in enumerate(plan.phases):
            if self._cancelled:
                break

            self._state.current_phase = phase_index + 1

            self._emit_progress("phase_started", {
                "task_id": self._state.task_id,
                "phase": phase_index + 1,
                "name": phase.name,
                "parallel": phase.parallel,
                "workers": [w.worker for w in phase.workers],
            })

            # 检查依赖
            if not self._check_dependencies(phase, results):
                logger.warning("Phase %d dependencies not met, skipping", phase_index + 1)
                continue

            # 执行 Phase
            phase_result = await self._execute_phase(phase, results)
            self._state.phase_results.append(phase_result)

            # 更新结果上下文
            results[f"phase_{phase_index + 1}"] = phase_result.to_dict()
            for worker_name, worker_result in phase_result.worker_results.items():
                results[worker_name] = worker_result.to_dict()
                self._state.worker_results[worker_name] = worker_result

            # 评估 Phase 结果
            evaluation = await self._result_evaluator.evaluate(
                phase=phase,
                result=phase_result,
                context=self._state.context,
            )

            self._emit_progress("phase_completed", {
                "task_id": self._state.task_id,
                "phase": phase_index + 1,
                "status": phase_result.status,
                "evaluation": evaluation.to_dict(),
            })

            # 处理评估结果
            if not evaluation.can_proceed:
                # 尝试错误恢复
                recovery = await self._error_recovery.recover(
                    phase=phase,
                    result=phase_result,
                    evaluation=evaluation,
                )

                if recovery.action == "abort":
                    logger.warning("Phase %d failed and recovery aborted", phase_index + 1)
                    break
                elif recovery.action == "retry":
                    # 重试 Phase
                    phase_result = await self._retry_phase(phase, results, recovery)
                    self._state.phase_results[-1] = phase_result
                elif recovery.action == "skip":
                    logger.info("Skipping failed phase %d as non-critical", phase_index + 1)
                    continue

        return results

    async def _execute_phase(
        self,
        phase: "Phase",
        context: Dict[str, Any],
    ) -> PhaseResult:
        """
        执行单个 Phase

        Args:
            phase: Phase 定义
            context: 当前上下文

        Returns:
            Phase 执行结果
        """
        # 准备 Worker 任务
        tasks = []
        for assignment in phase.workers:
            # 获取 Worker 配置
            worker_config = self._workers.get(assignment.worker)
            if not worker_config:
                logger.warning("Worker not found: %s", assignment.worker)
                continue

            # 解析输入变量
            resolved_input = self._resolve_variables(assignment.input, context)

            # 创建任务
            task = WorkerTask(
                session_id=self._state.session_id,
                worker_name=assignment.worker,
                task_description=assignment.task,
                input_data=resolved_input,
                context={
                    **self._state.context,
                    "phase": phase.name,
                    "objective": self._state.objective,
                },
            )

            tasks.append((worker_config, task))

        # 执行 Workers
        if phase.parallel:
            worker_results = await self._execute_workers_parallel(tasks)
        else:
            worker_results = await self._execute_workers_sequential(tasks)

        # 构建 Phase 结果
        return PhaseResult(
            phase_name=phase.name,
            worker_results=worker_results,
            status=self._determine_phase_status(worker_results),
        )

    async def _execute_workers_parallel(
        self,
        tasks: List[tuple[WorkerConfig, WorkerTask]],
    ) -> Dict[str, WorkerResult]:
        """
        并行执行 Workers

        Args:
            tasks: (WorkerConfig, WorkerTask) 列表

        Returns:
            Worker 名称到结果的映射
        """
        async def run_worker(config: WorkerConfig, task: WorkerTask) -> tuple[str, WorkerResult]:
            runner = WorkerRunner(
                config=config,
                model=self.model,
                toolkit=self.toolkit,
                progress_callback=self.progress_callback,
            )
            result = await runner.run(task)
            return config.name, result

        # 并行执行
        semaphore = asyncio.Semaphore(self.config.max_parallel_workers)

        async def limited_run(config: WorkerConfig, task: WorkerTask):
            async with semaphore:
                return await run_worker(config, task)

        coroutines = [limited_run(config, task) for config, task in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # 处理结果
        worker_results = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                config, task = tasks[i]
                worker_results[config.name] = WorkerResult(
                    task_id=task.task_id,
                    worker_name=config.name,
                    status=TaskStatus.FAILED,
                    error=str(result),
                )
            else:
                name, worker_result = result
                worker_results[name] = worker_result

        return worker_results

    async def _execute_workers_sequential(
        self,
        tasks: List[tuple[WorkerConfig, WorkerTask]],
    ) -> Dict[str, WorkerResult]:
        """
        顺序执行 Workers

        Args:
            tasks: (WorkerConfig, WorkerTask) 列表

        Returns:
            Worker 名称到结果的映射
        """
        worker_results = {}

        for config, task in tasks:
            if self._cancelled:
                break

            runner = WorkerRunner(
                config=config,
                model=self.model,
                toolkit=self.toolkit,
                progress_callback=self.progress_callback,
            )

            result = await runner.run(task)
            worker_results[config.name] = result

            # 更新任务上下文，传递给后续 Worker
            task.context[f"{config.name}_result"] = result.output

        return worker_results

    async def _retry_phase(
        self,
        phase: "Phase",
        context: Dict[str, Any],
        recovery: RecoveryAction,
    ) -> PhaseResult:
        """
        重试 Phase

        Args:
            phase: Phase 定义
            context: 当前上下文
            recovery: 恢复策略

        Returns:
            重试结果
        """
        for attempt in range(recovery.max_retries):
            self._emit_progress("phase_retry", {
                "task_id": self._state.task_id,
                "phase": phase.name,
                "attempt": attempt + 1,
            })

            result = await self._execute_phase(phase, context)
            if result.status == "success":
                return result

        return result

    def _check_dependencies(
        self,
        phase: "Phase",
        results: Dict[str, Any],
    ) -> bool:
        """
        检查 Phase 依赖

        Args:
            phase: Phase 定义
            results: 已有结果

        Returns:
            依赖是否满足
        """
        for dep in phase.depends_on:
            if dep not in results:
                return False
            dep_result = results[dep]
            if isinstance(dep_result, dict) and dep_result.get("status") == "failed":
                return False
        return True

    def _resolve_variables(
        self,
        data: Any,
        context: Dict[str, Any],
    ) -> Any:
        """
        解析变量引用

        支持 $phase_1.output 格式的变量。使用递归遍历替代 JSON 字符串操作。

        Args:
            data: 输入数据（可以是 dict, list, str 或其他类型）
            context: 上下文

        Returns:
            解析后的数据
        """
        if isinstance(data, dict):
            return {k: self._resolve_variables(v, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_variables(item, context) for item in data]
        elif isinstance(data, str):
            # 检查是否是变量引用
            if data.startswith("$"):
                return self._resolve_single_variable(data[1:], context)
            # 检查字符串中是否包含变量引用
            pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)'
            matches = list(re.finditer(pattern, data))
            if matches:
                # 如果整个字符串就是一个变量引用，返回实际值（保持类型）
                if len(matches) == 1 and matches[0].group(0) == data:
                    return self._resolve_single_variable(matches[0].group(1), context)
                # 否则进行字符串替换
                result = data
                for match in reversed(matches):  # 从后往前替换，避免索引偏移
                    var_value = self._resolve_single_variable(match.group(1), context)
                    if var_value is not None:
                        if isinstance(var_value, (dict, list)):
                            var_str = json.dumps(var_value, ensure_ascii=False)
                        else:
                            var_str = str(var_value)
                        result = result[:match.start()] + var_str + result[match.end():]
                return result
            return data
        else:
            return data

    def _resolve_single_variable(self, var_path: str, context: Dict[str, Any]) -> Any:
        """
        解析单个变量引用

        Args:
            var_path: 变量路径，如 "phase_1.output"
            context: 上下文

        Returns:
            变量值，如果未找到返回 None
        """
        parts = var_path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _determine_phase_status(self, worker_results: Dict[str, WorkerResult]) -> str:
        """
        确定 Phase 状态

        Args:
            worker_results: Worker 结果

        Returns:
            Phase 状态
        """
        if not worker_results:
            return "failed"

        statuses = [r.status.value for r in worker_results.values()]

        if all(s == "success" for s in statuses):
            return "success"
        elif all(s == "failed" for s in statuses):
            return "failed"
        elif any(s == "success" for s in statuses):
            return "partial"
        else:
            return "failed"

    def _is_task_complete(self, results: Dict[str, Any]) -> bool:
        """
        判断任务是否完成

        Args:
            results: 执行结果

        Returns:
            是否完成
        """
        if not self._state.plan:
            return False

        # 检查所有 Phase 是否成功
        for phase_result in self._state.phase_results:
            if phase_result.status == "failed":
                return False

        # 检查完成条件
        completion_criteria = self._state.plan.completion_criteria
        if completion_criteria:
            # TODO: 使用 LLM 评估完成条件
            pass

        return True

    async def _handle_incomplete(self, results: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理未完成的任务

        可能生成补充计划。

        Args:
            results: 当前结果

        Returns:
            补充执行结果
        """
        # TODO: 实现补充计划生成
        return None

    def _merge_results(
        self,
        main_results: Dict[str, Any],
        supplementary_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        合并结果

        Args:
            main_results: 主结果
            supplementary_results: 补充结果

        Returns:
            合并后的结果
        """
        merged = main_results.copy()
        merged["supplementary"] = supplementary_results
        return merged

    def _load_skills(self) -> List[Dict[str, Any]]:
        """
        加载 Skills 信息

        Returns:
            Skill 摘要列表
        """
        skills = []

        if not self.config.skills_dir.exists():
            return skills

        for skill_path in self.config.skills_dir.glob("*/SKILL.md"):
            skill_dir = skill_path.parent
            skill_name = skill_dir.name

            # 解析 SKILL.md
            try:
                content = skill_path.read_text(encoding="utf-8")
                match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if match:
                    metadata = yaml.safe_load(match.group(1)) or {}
                    skills.append({
                        "name": metadata.get("name", skill_name),
                        "description": metadata.get("description", ""),
                        "tags": metadata.get("tags", []),
                    })
            except Exception as exc:
                logger.warning("Failed to load skill %s: %s", skill_name, exc)

        return skills

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
