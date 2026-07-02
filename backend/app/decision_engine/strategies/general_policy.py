"""通用策略维度 —— 承接 Stage 1 的整体机审能力。

配置了 LLM 则用本维度 build_prompt 调 LLM 做整体判断（经 BaseReviewStrategy._llm_verdict）；
否则退化为关键词规则。
把原 services._run_machine_review 的逻辑收敛成一个标准维度，其他专项维度并行叠加。
"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict

_BLOCK_TERMS = {"gambling", "bet", "bonus", "weapon", "hate"}
_PASS_TERMS = {"cooking", "recipe", "education", "travel", "music"}


@StrategyRegistry.register("dim_general_policy")
class GeneralPolicyStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "你是内容安全审查专家。基于以下证据判断整体是否违反平台通用策略，"
            "输出 decision/confidence/reason/evidence_refs。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        llm = self._llm_verdict(evidence, policy_version)
        if llm is not None:
            return llm

        text = self._text_blob(evidence)
        block_score = sum(1 for t in _BLOCK_TERMS if t in text)
        pass_score = sum(1 for t in _PASS_TERMS if t in text)
        if block_score > pass_score:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.VIOLATION,
                confidence=min(0.55 + block_score * 0.12, 0.92),
                reason="关键词和元数据证据显示内容可能存在策略风险。",
                policy_version=policy_version,
                model_version="keyword_rules_v1",
            )
        if pass_score > 0 and block_score == 0:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=min(0.62 + pass_score * 0.08, 0.86),
                reason="证据整体风险较低，但最终裁定仍由人审完成。",
                policy_version=policy_version,
                model_version="keyword_rules_v1",
            )
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.UNCERTAIN,
            confidence=0.5,
            reason="机审没有形成强建议，需要人工判断。",
            policy_version=policy_version,
            model_version="keyword_rules_v1",
        )
