# -*- coding: utf-8 -*-
"""
结果评估器

使用 LLM 评估 Phase 执行结果，判断是否达成目标。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentscope.model import ChatModelBase

# Handle both package and standalone imports
try:
    from .task_planner import Phase
    from .phase_scheduler import PhaseResult
except ImportError:
    from task_planner import Phase
    from phase_scheduler import PhaseResult

logger = logging.getLogger(__name__)


@dataclass
class PhaseEvaluation:
    """Phase 评估结果"""

    phase_completed: bool = False
    quality_score: float = 0.0  # 0-1 范围
    retry_workers: List[str] = field(default_factory=list)
    plan_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    can_proceed: bool = True
    reason: str = ""
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "phase_completed": self.phase_completed,
            "quality_score": self.quality_score,
            "retry_workers": self.retry_workers,
            "plan_adjustments": self.plan_adjustments,
            "can_proceed": self.can_proceed,
            "reason": self.reason,
            "suggestions": self.suggestions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseEvaluation":
        """从字典创建"""
        return cls(
            phase_completed=data.get("phase_completed", False),
            quality_score=data.get("quality_score", 0.0),
            retry_workers=data.get("retry_workers", []),
            plan_adjustments=data.get("plan_adjustments", []),
            can_proceed=data.get("can_proceed", True),
            reason=data.get("reason", ""),
            suggestions=data.get("suggestions", []),
        )


class ResultEvaluator:
    """
    结果评估器

    使用 LLM 评估 Phase 执行结果：
    1. 判断 Phase 目标是否达成
    2. 评估输出质量
    3. 确定是否需要重试
    4. 建议计划调整
    """

    def __init__(self, model: ChatModelBase):
        """
        初始化评估器

        Args:
            model: LLM 模型实例
        """
        self.model = model

    async def evaluate(
        self,
        phase: Phase,
        result: PhaseResult,
        context: Dict[str, Any],
    ) -> PhaseEvaluation:
        """
        评估 Phase 结果

        Args:
            phase: Phase 定义
            result: Phase 执行结果
            context: 上下文

        Returns:
            评估结果
        """
        # 快速路径：明确的失败状态
        if result.status == "failed":
            return PhaseEvaluation(
                phase_completed=False,
                quality_score=0.0,
                can_proceed=False,
                reason=result.error or "Phase execution failed",
                retry_workers=list(result.worker_results.keys()),
            )

        # 快速路径：所有 Workers 成功
        if result.status == "success":
            # 可以选择性地使用 LLM 进行更深入的质量评估
            return PhaseEvaluation(
                phase_completed=True,
                quality_score=1.0,
                can_proceed=True,
                reason="All workers completed successfully",
            )

        # 部分成功：需要 LLM 评估
        return await self._evaluate_with_llm(phase, result, context)

    async def _evaluate_with_llm(
        self,
        phase: Phase,
        result: PhaseResult,
        context: Dict[str, Any],
    ) -> PhaseEvaluation:
        """
        使用 LLM 进行评估

        Args:
            phase: Phase 定义
            result: Phase 结果
            context: 上下文

        Returns:
            评估结果
        """
        prompt = self._build_evaluation_prompt(phase, result, context)

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.model(messages)
            return self._parse_evaluation(response)
        except Exception as exc:
            logger.warning("LLM evaluation failed: %s", exc)
            # 回退到基于规则的评估
            return self._rule_based_evaluation(result)

    def _build_evaluation_prompt(
        self,
        phase: Phase,
        result: PhaseResult,
        context: Dict[str, Any],
    ) -> str:
        """
        构建评估提示词

        Args:
            phase: Phase 定义
            result: Phase 结果
            context: 上下文

        Returns:
            提示词
        """
        parts = []

        # Phase 信息
        parts.append(f"## Phase Information\n- Name: {phase.name}\n- Workers: {[w.worker for w in phase.workers]}")

        # 执行结果
        worker_summaries = []
        for name, wr in result.worker_results.items():
            status = wr.status.value if hasattr(wr.status, "value") else str(wr.status)
            output_preview = str(wr.output)[:200] if wr.output else "None"
            worker_summaries.append(
                f"- **{name}**: {status}\n  Output: {output_preview}..."
            )
        parts.append(f"## Worker Results\n" + "\n".join(worker_summaries))

        # 评估要求
        parts.append("""## Evaluation Task

Please evaluate the phase execution and respond with JSON:

```json
{
  "phase_completed": true/false,
  "quality_score": 0.0-1.0,
  "retry_workers": ["worker_name"],
  "plan_adjustments": [],
  "can_proceed": true/false,
  "reason": "Explanation",
  "suggestions": ["suggestion1", "suggestion2"]
}
```

Consider:
1. Did all required workers complete their tasks?
2. Are the outputs valid and useful?
3. Are there any critical failures that block progress?
4. What improvements or retries might help?
""")

        return "\n\n".join(parts)

    def _parse_evaluation(self, response: Any) -> PhaseEvaluation:
        """
        解析 LLM 评估响应

        Args:
            response: LLM 响应

        Returns:
            评估结果
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
            return PhaseEvaluation.from_dict(data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse evaluation JSON")
            return PhaseEvaluation(
                phase_completed=True,
                quality_score=0.5,
                can_proceed=True,
                reason="Could not parse evaluation, proceeding with caution",
            )

    def _rule_based_evaluation(self, result: PhaseResult) -> PhaseEvaluation:
        """
        基于规则的评估（回退方案）

        Args:
            result: Phase 结果

        Returns:
            评估结果
        """
        total_workers = len(result.worker_results)
        successful = sum(
            1 for wr in result.worker_results.values()
            if hasattr(wr, "status") and str(wr.status) in ("success", "TaskStatus.SUCCESS")
        )

        quality_score = successful / total_workers if total_workers > 0 else 0.0

        failed_workers = [
            name for name, wr in result.worker_results.items()
            if hasattr(wr, "status") and str(wr.status) not in ("success", "TaskStatus.SUCCESS")
        ]

        return PhaseEvaluation(
            phase_completed=quality_score >= 0.5,
            quality_score=quality_score,
            retry_workers=failed_workers,
            can_proceed=quality_score >= 0.5,
            reason=f"{successful}/{total_workers} workers succeeded",
        )

    def _system_prompt(self) -> str:
        """
        获取评估系统提示词

        Returns:
            系统提示词
        """
        return """You are a Result Evaluator for a multi-agent task execution system.

Your role is to evaluate the results of phase execution and determine:
1. Whether the phase objectives were achieved
2. The quality of the outputs
3. Whether to retry failed workers
4. Whether execution can proceed to the next phase

Be objective and thorough in your evaluation. Consider both technical success
(did the operation complete?) and semantic success (is the output useful?).

Always respond with valid JSON in the specified format.
"""
