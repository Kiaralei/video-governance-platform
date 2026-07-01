"""博彩/彩票合规维度。"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict, EvidenceRef, SeveritySuggestion

_TERMS = ("gambling", "bet", "betting", "casino", "lottery", "wager", "odds", "bonus", "博彩", "赌")
_OBJECTS = {"lottery_ticket", "gambling_equipment", "poker_chip", "dice", "slot_machine"}
_LURE = ("qr", "scan", "扫码", "wechat", "telegram", "invite", "进群")


@StrategyRegistry.register("dim_gambling")
class GamblingStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断视频是否推广非法博彩/彩票或存在博彩引流。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        text = self._text_blob(evidence)
        objects = set(self._object_labels(evidence))
        hits = [t for t in _TERMS if t in text]
        object_hits = objects & _OBJECTS
        if not hits and not object_hits:
            return self._clean(policy_version)

        # 博彩关键词 + 引流信号 = 高危引流，建议 critical。
        lure = any(l in text for l in _LURE)
        confidence = min(0.6 + 0.12 * (len(hits) + len(object_hits)) + (0.15 if lure else 0.0), 0.97)
        severity = SeveritySuggestion.CRITICAL if lure else SeveritySuggestion.HIGH
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.VIOLATION,
            confidence=confidence,
            severity_suggestion=severity,
            reason=f"命中博彩相关信号: {sorted(set(hits) | object_hits)}"
            + ("；且含引流线索。" if lure else "。"),
            policy_version=policy_version,
            model_version="gambling_rules_v1",
            evidence_refs=[EvidenceRef(ref_type="keyword", description=t, text_excerpt=t) for t in hits],
        )

    def _clean(self, policy_version: str) -> DimensionVerdict:
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.NO_VIOLATION,
            confidence=0.95,
            reason="未检测到博彩相关信号。",
            policy_version=policy_version,
            model_version="gambling_rules_v1",
        )
