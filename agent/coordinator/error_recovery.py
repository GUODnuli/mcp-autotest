# -*- coding: utf-8 -*-
"""
错误恢复模块

处理 Worker 失败，决定恢复策略。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agentscope.model import ChatModelBase

# Handle both package and standalone imports
try:
    from .task_planner import Phase
    from .phase_scheduler import PhaseResult
    from .result_evaluator import PhaseEvaluation
except ImportError:
    from task_planner import Phase
    from phase_scheduler import PhaseResult
    from result_evaluator import PhaseEvaluation

logger = logging.getLogger(__name__)


class RecoveryActionType(str, Enum):
    """恢复动作类型"""
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"
    ADJUST = "adjust"


@dataclass
class RecoveryAction:
    """恢复动作"""

    action: str  # retry, skip, fallback, abort, adjust
    fallback_worker: Optional[str] = None
    max_retries: int = 3
    reason: str = ""
    adjustments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "action": self.action,
            "fallback_worker": self.fallback_worker,
            "max_retries": self.max_retries,
            "reason": self.reason,
            "adjustments": self.adjustments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryAction":
        """从字典创建"""
        return cls(
            action=data.get("action", "abort"),
            fallback_worker=data.get("fallback_worker"),
            max_retries=data.get("max_retries", 3),
            reason=data.get("reason", ""),
            adjustments=data.get("adjustments", []),
        )


class ErrorRecovery:
    """
    错误恢复模块

    处理执行失败，决定恢复策略：
    1. retry - 重试失败的 Worker
    2. skip - 跳过非关键 Worker
    3. fallback - 使用替代 Worker
    4. abort - 终止执行
    5. adjust - 调整后续计划
    """

    def __init__(
        self,
        model: ChatModelBase,
        max_retries: int = 3,
    ):
        """
        初始化错误恢复模块

        Args:
            model: LLM 模型实例
            max_retries: 默认最大重试次数
        """
        self.model = model
        self.max_retries = max_retries

        # 错误计数
        self._error_counts: Dict[str, int] = {}

    def reset(self) -> None:
        """重置错误计数"""
        self._error_counts = {}

    async def recover(
        self,
        phase: Phase,
        result: PhaseResult,
        evaluation: PhaseEvaluation,
        available_workers: Optional[List[str]] = None,
    ) -> RecoveryAction:
        """
        确定恢复策略

        Args:
            phase: 失败的 Phase
            result: Phase 执行结果
            evaluation: 评估结果
            available_workers: 可用 Worker 列表

        Returns:
            恢复动作
        """
        # 更新错误计数
        phase_key = f"phase_{phase.phase}"
        self._error_counts[phase_key] = self._error_counts.get(phase_key, 0) + 1
        retry_count = self._error_counts[phase_key]

        # 快速路径：超过重试限制
        if retry_count > self.max_retries:
            return RecoveryAction(
                action="abort",
                reason=f"Exceeded max retries ({self.max_retries})",
            )

        # 分析失败类型
        failure_analysis = self._analyze_failure(result, evaluation)

        # 根据失败类型决定策略
        if failure_analysis["is_transient"]:
            # 瞬时错误：重试
            return RecoveryAction(
                action="retry",
                max_retries=self.max_retries - retry_count,
                reason="Transient error detected, retrying",
            )

        if failure_analysis["is_critical"]:
            # 关键错误：中止
            return RecoveryAction(
                action="abort",
                reason=f"Critical error: {failure_analysis['error_type']}",
            )

        if failure_analysis["has_fallback"]:
            # 有替代方案：使用 fallback
            return RecoveryAction(
                action="fallback",
                fallback_worker=failure_analysis.get("fallback_worker"),
                reason="Using fallback worker",
            )

        # 使用 LLM 决定复杂情况
        return await self._decide_with_llm(phase, result, evaluation, available_workers)

    def _analyze_failure(
        self,
        result: PhaseResult,
        evaluation: PhaseEvaluation,
    ) -> Dict[str, Any]:
        """
        分析失败原因

        Args:
            result: Phase 结果
            evaluation: 评估结果

        Returns:
            失败分析
        """
        analysis = {
            "is_transient": False,
            "is_critical": False,
            "has_fallback": False,
            "error_type": "unknown",
            "failed_workers": [],
        }

        # 收集失败信息
        for name, wr in result.worker_results.items():
            if hasattr(wr, "status"):
                status = str(wr.status)
                if status in ("failed", "TaskStatus.FAILED", "timeout", "TaskStatus.TIMEOUT"):
                    analysis["failed_workers"].append(name)

                    error = getattr(wr, "error", "") or ""

                    # 检测瞬时错误
                    transient_indicators = [
                        "timeout", "connection", "rate limit",
                        "temporarily", "retry", "503", "429"
                    ]
                    if any(ind in error.lower() for ind in transient_indicators):
                        analysis["is_transient"] = True

                    # 检测关键错误
                    critical_indicators = [
                        "authentication", "authorization", "forbidden",
                        "invalid api key", "access denied", "401", "403"
                    ]
                    if any(ind in error.lower() for ind in critical_indicators):
                        analysis["is_critical"] = True
                        analysis["error_type"] = "authentication/authorization"

        return analysis

    async def _decide_with_llm(
        self,
        phase: Phase,
        result: PhaseResult,
        evaluation: PhaseEvaluation,
        available_workers: Optional[List[str]],
    ) -> RecoveryAction:
        """
        使用 LLM 决定恢复策略

        Args:
            phase: Phase 定义
            result: Phase 结果
            evaluation: 评估结果
            available_workers: 可用 Workers

        Returns:
            恢复动作
        """
        prompt = self._build_recovery_prompt(phase, result, evaluation, available_workers)

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.model(messages)
            return self._parse_recovery_action(response)
        except Exception as exc:
            logger.warning("LLM recovery decision failed: %s", exc)
            # 默认重试
            return RecoveryAction(
                action="retry",
                max_retries=1,
                reason="LLM decision failed, defaulting to retry",
            )

    def _build_recovery_prompt(
        self,
        phase: Phase,
        result: PhaseResult,
        evaluation: PhaseEvaluation,
        available_workers: Optional[List[str]],
    ) -> str:
        """
        构建恢复决策提示词

        Args:
            phase: Phase 定义
            result: Phase 结果
            evaluation: 评估结果
            available_workers: 可用 Workers

        Returns:
            提示词
        """
        parts = []

        # Phase 信息
        parts.append(f"## Failed Phase\n- Name: {phase.name}\n- Phase: {phase.phase}")

        # 失败详情
        failed_details = []
        for name, wr in result.worker_results.items():
            status = str(getattr(wr, "status", "unknown"))
            error = getattr(wr, "error", "None")
            failed_details.append(f"- **{name}**: {status}\n  Error: {error}")
        parts.append(f"## Worker Results\n" + "\n".join(failed_details))

        # 评估结果
        parts.append(f"## Evaluation\n{json.dumps(evaluation.to_dict(), indent=2)}")

        # 可用 Workers
        if available_workers:
            parts.append(f"## Available Workers\n{', '.join(available_workers)}")

        # 决策要求
        parts.append("""## Recovery Decision

Decide on the recovery strategy and respond with JSON:

```json
{
  "action": "retry|skip|fallback|abort|adjust",
  "fallback_worker": "worker_name",
  "max_retries": 3,
  "reason": "Explanation",
  "adjustments": []
}
```

Actions:
- **retry**: Retry the failed workers
- **skip**: Skip this phase (if non-critical)
- **fallback**: Use an alternative worker
- **abort**: Stop execution (critical failure)
- **adjust**: Modify the execution plan
""")

        return "\n\n".join(parts)

    def _parse_recovery_action(self, response: Any) -> RecoveryAction:
        """
        解析 LLM 恢复决策响应

        Args:
            response: LLM 响应

        Returns:
            恢复动作
        """
        # 获取响应文本
        if hasattr(response, "text"):
            text = response.text
        elif hasattr(response, "content"):
            text = response.content
        else:
            text = str(response)

        # 提取 JSON
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text

        try:
            data = json.loads(json_str)
            return RecoveryAction.from_dict(data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse recovery action JSON")
            return RecoveryAction(
                action="retry",
                max_retries=1,
                reason="Could not parse recovery decision",
            )

    def _system_prompt(self) -> str:
        """
        获取恢复决策系统提示词

        Returns:
            系统提示词
        """
        return """You are an Error Recovery Specialist for a multi-agent task execution system.

Your role is to analyze failures and decide on the best recovery strategy:

1. **retry** - Use when the error seems transient (timeouts, rate limits, connection issues)
2. **skip** - Use when the failed task is non-critical and won't block progress
3. **fallback** - Use when an alternative worker can accomplish the same goal
4. **abort** - Use when the failure is critical and cannot be recovered
5. **adjust** - Use when the execution plan needs modification

Consider:
- Error patterns (transient vs permanent)
- Task criticality (is it blocking?)
- Available alternatives
- Retry history (avoid infinite loops)

Always respond with valid JSON in the specified format.
Be decisive and provide clear reasoning.
"""
