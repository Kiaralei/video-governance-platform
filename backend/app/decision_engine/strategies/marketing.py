"""营销属性/画风维度（quality 轴）—— 软广、强营销、导流、低俗画风。"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict, EvidenceRef

_MARKETING_TERMS = (
    "buy now", "discount", "sale", "coupon", "promo", "order", "下单", "优惠", "折扣",
    "带货", "link in bio", "dm me", "私信", "加微信", "wechat", "qr", "scan", "扫码",
)


@StrategyRegistry.register("dim_marketing_review")
class MarketingStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断视频是否为软广/强营销/导流/带货，画风是否低俗夸张。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        llm = self._llm_verdict(evidence, policy_version)
        if llm is not None:
            return llm
        text = self._text_blob(evidence)
        hits = [t for t in _MARKETING_TERMS if t in text]
        if not hits:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=0.88,
                reason="未检测到明显营销/导流信号。",
                policy_version=policy_version,
                model_version="marketing_rules_v1",
            )
        # 营销属于 quality 轴，阈值偏低但不轻易 auto_block；多为人审。
        confidence = min(0.5 + 0.1 * len(hits), 0.85)
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.VIOLATION,
            confidence=confidence,
            reason=f"命中营销/导流信号: {hits}。",
            policy_version=policy_version,
            model_version="marketing_rules_v1",
            evidence_refs=[EvidenceRef(ref_type="keyword", description=t, text_excerpt=t) for t in hits],
        )
