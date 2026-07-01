"""内容与信息匹配维度（quality 轴）—— 视频内容是否与标题/简介/挂载地点一致。"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "with", "for", "is", "at",
    "视频", "内容", "一个", "the video", "this",
}


@StrategyRegistry.register("dim_poi_match")
class PoiMatchStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断视频内容是否与标题、简介、挂载地点(POI)一致。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        meta = evidence.get("metadata", {}) or {}
        poi = str(meta.get("poi", "") or "").strip().lower()
        # 无 POI 或 POI 为 global：不做强约束。
        if not poi or poi == "global":
            return self._match(policy_version, 0.9, "无具体挂载地点，不做一致性约束。")

        # 把 ASR/OCR/标题拼成内容词集，检查 POI 关键词是否被内容覆盖。
        content = self._text_blob(evidence)
        poi_tokens = [t for t in poi.replace(",", " ").split() if t and t not in _STOPWORDS]
        if not poi_tokens:
            return self._match(policy_version, 0.85, "POI 无有效关键词。")

        matched = [t for t in poi_tokens if t in content]
        ratio = len(matched) / len(poi_tokens)
        if ratio >= 0.5:
            return self._match(policy_version, 0.6 + 0.3 * ratio, f"POI 关键词覆盖率 {ratio:.0%}。")
        # 内容与挂载地点明显不符 -> 交人审（UNCERTAIN）。
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.UNCERTAIN,
            confidence=0.5,
            reason=f"内容与挂载地点(POI='{poi}')匹配度低({ratio:.0%})，建议人工核对。",
            policy_version=policy_version,
            model_version="poi_rules_v1",
        )

    def _match(self, policy_version: str, confidence: float, reason: str) -> DimensionVerdict:
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.NO_VIOLATION,
            confidence=min(confidence, 0.95),
            reason=reason,
            policy_version=policy_version,
            model_version="poi_rules_v1",
        )
