"""毒品/暴力内容检测维度。"""

from __future__ import annotations

from typing import Any

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict, EvidenceRef, SeveritySuggestion

_TERMS = ("drug", "cocaine", "heroin", "violence", "weapon", "gun", "knife", "blood", "毒品", "暴力")
_OBJECTS = {"drug", "weapon", "knife", "gun", "syringe", "rifle", "pistol", "blood"}


@StrategyRegistry.register("dim_drug_violence")
class DrugViolenceStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断视频是否展示或推广毒品，或存在暴力/血腥行为。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        llm = self._llm_verdict(evidence, policy_version)
        if llm is not None:
            return llm
        text = self._text_blob(evidence)
        objects = set(self._object_labels(evidence))
        term_hits = [t for t in _TERMS if t in text]
        object_hits = objects & _OBJECTS
        if not term_hits and not object_hits:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=0.93,
                reason="未检测到毒品或暴力相关物体/话术。",
                policy_version=policy_version,
                model_version="drug_violence_rules_v1",
            )
        # 物体检测命中比纯文本更可信。
        confidence = min(0.65 + 0.13 * len(object_hits) + 0.07 * len(term_hits), 0.96)
        severity = SeveritySuggestion.CRITICAL if object_hits else SeveritySuggestion.HIGH
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.VIOLATION,
            confidence=confidence,
            severity_suggestion=severity,
            reason=f"命中毒品/暴力信号: 物体={sorted(object_hits)}, 话术={term_hits}。",
            policy_version=policy_version,
            model_version="drug_violence_rules_v1",
            evidence_refs=[
                EvidenceRef(ref_type="detection", description=label) for label in sorted(object_hits)
            ],
        )
