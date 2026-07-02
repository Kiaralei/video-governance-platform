"""未成年合规维度 —— 偏保守：疑似未成年 + 风险线索至少强制人审。"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict, EvidenceRef

_MINOR_TERMS = ("child", "kid", "minor", "teen", "toddler", "儿童", "未成年", "小孩")
_MINOR_OBJECTS = {"child", "minor", "kid", "baby", "toddler"}
_RISK_TERMS = (
    "sexy", "nude", "gun", "weapon", "drug", "bet", "gambling", "buy now",
    "扫码", "qr", "contact", "wechat", "危险",
)


@StrategyRegistry.register("dim_minor_compliance")
class MinorComplianceStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断是否为正常亲子/教育/家庭场景；若疑似未成年且伴随性化/危险/诱导/导流线索，"
            "应偏保守。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        llm = self._llm_verdict(evidence, policy_version)
        if llm is not None:
            return llm
        text = self._text_blob(evidence)
        objects = set(self._object_labels(evidence))
        minor_present = any(t in text for t in _MINOR_TERMS) or bool(objects & _MINOR_OBJECTS)
        risk_hits = [t for t in _RISK_TERMS if t in text]

        if not minor_present:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=0.9,
                reason="未检测到未成年线索。",
                policy_version=policy_version,
                model_version="minor_rules_v1",
            )
        if risk_hits:
            # 疑似未成年 + 风险线索 -> UNCERTAIN（映射为强制人审），不自动定性。
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.5,
                reason=f"疑似未成年且伴随风险线索 {risk_hits}，强制人工复核。",
                policy_version=policy_version,
                model_version="minor_rules_v1",
                evidence_refs=[EvidenceRef(ref_type="keyword", description=t) for t in risk_hits],
            )
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.NO_VIOLATION,
            confidence=0.7,
            reason="疑似未成年但未见明显风险线索，判为正常家庭/教育场景。",
            policy_version=policy_version,
            model_version="minor_rules_v1",
        )
