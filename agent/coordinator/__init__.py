# -*- coding: utf-8 -*-
"""
Coordinator 模块

提供主 Agent 协调器功能，管理任务分解和 Worker 调度。
"""
# Handle both package and standalone imports
try:
    from .coordinator import Coordinator, CoordinatorConfig
    from .task_planner import TaskPlanner, ExecutionPlan, Phase, WorkerAssignment
    from .phase_scheduler import PhaseScheduler, PhaseResult
    from .result_evaluator import ResultEvaluator, PhaseEvaluation
    from .error_recovery import ErrorRecovery, RecoveryAction
except ImportError:
    from coordinator import Coordinator, CoordinatorConfig
    from task_planner import TaskPlanner, ExecutionPlan, Phase, WorkerAssignment
    from phase_scheduler import PhaseScheduler, PhaseResult
    from result_evaluator import ResultEvaluator, PhaseEvaluation
    from error_recovery import ErrorRecovery, RecoveryAction

__all__ = [
    # Coordinator
    "Coordinator",
    "CoordinatorConfig",
    # Task Planner
    "TaskPlanner",
    "ExecutionPlan",
    "Phase",
    "WorkerAssignment",
    # Phase Scheduler
    "PhaseScheduler",
    "PhaseResult",
    # Result Evaluator
    "ResultEvaluator",
    "PhaseEvaluation",
    # Error Recovery
    "ErrorRecovery",
    "RecoveryAction",
]
