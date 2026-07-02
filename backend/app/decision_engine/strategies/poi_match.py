"""Content and attached business context consistency review."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..base import BaseReviewStrategy
from ..registry import StrategyRegistry
from ..types import DimensionDecision, DimensionVerdict, EvidenceRef

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "with", "for", "is", "at",
    "this", "that", "video", "clip", "demo", "global", "official", "premium", "local",
    "www", "com", "https", "http", "cart", "shop", "product", "item",
}

_CATEGORY_HINTS: dict[str, set[str]] = {
    "restaurant": {"restaurant", "food", "meal", "dish", "sushi", "noodle", "coffee", "cafe", "dining"},
    "food": {"food", "meal", "dish", "recipe", "cooking", "sushi", "noodle", "coffee"},
    "travel": {"travel", "hotel", "city", "trip", "poi", "scenic", "park"},
    "retail": {"shopping", "store", "product", "haul", "unboxing"},
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").lower()
    raw = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text)
    return [item for item in raw if item not in _STOPWORDS and len(item) >= 2]


def _context_from(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("business_context")
    return raw if isinstance(raw, dict) else {}


def _domain_tokens(url: str) -> list[str]:
    if not url:
        return []
    host = urlparse(url).netloc or urlparse(f"https://{url}").netloc
    return _tokens(host.replace(".", " "))


@StrategyRegistry.register("dim_poi_match")
class PoiMatchStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence: dict[str, Any]) -> str:
        return (
            "判断视频内容是否与标题、简介、挂载 POI、商品和购物车链接一致。\n"
            f"<evidence>{self._build_evidence_summary(evidence)}</evidence>"
        )

    def review(self, evidence: dict[str, Any], policy_version: str) -> DimensionVerdict:
        meta = evidence.get("metadata", {}) or {}
        context = _context_from(meta)
        poi = context.get("poi") if isinstance(context.get("poi"), dict) else {}
        product = context.get("product") if isinstance(context.get("product"), dict) else {}
        cart = context.get("shopping_cart") if isinstance(context.get("shopping_cart"), dict) else {}
        merchant = context.get("merchant") if isinstance(context.get("merchant"), dict) else {}

        content_tokens = set(_tokens(self._text_blob(evidence)))
        for tag in self._scene_tags(evidence):
            content_tokens.update(_tokens(tag))
        for label in self._object_labels(evidence):
            content_tokens.update(_tokens(label))

        constraints = [
            ("POI", poi.get("name") or meta.get("poi")),
            ("POI category", poi.get("category") or meta.get("poi_category")),
            ("product", product.get("title") or meta.get("product_title")),
            ("product category", product.get("category") or meta.get("product_category")),
            ("merchant", merchant.get("name") or meta.get("merchant_name")),
        ]
        constraint_tokens: dict[str, list[str]] = {
            name: _tokens(value)
            for name, value in constraints
            if _tokens(value) and str(value or "").lower() != "global"
        }

        for token in _domain_tokens(str(cart.get("url") or meta.get("shopping_cart_url") or "")):
            if token not in {"example", "local"}:
                constraint_tokens.setdefault("cart domain", []).append(token)

        if not constraint_tokens:
            return self._match(policy_version, 0.9, "未挂载具体 POI、商品或购物车信息，不触发内容一致性约束。")

        matched: dict[str, list[str]] = {}
        missing: dict[str, list[str]] = {}
        for name, tokens in constraint_tokens.items():
            hints = set(tokens)
            for token in tokens:
                hints.update(_CATEGORY_HINTS.get(token, set()))
            hits = sorted(token for token in hints if token in content_tokens)
            if hits:
                matched[name] = hits
            else:
                missing[name] = tokens

        total = len(constraint_tokens)
        ratio = (total - len(missing)) / total if total else 1.0
        if ratio >= 0.6:
            reason = f"挂载信息与内容证据基本一致，匹配项 {sorted(matched)}，覆盖率 {ratio:.0%}。"
            return self._match(policy_version, 0.62 + 0.25 * ratio, reason)

        missing_text = "; ".join(f"{name}: {', '.join(tokens[:4])}" for name, tokens in missing.items())
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.UNCERTAIN,
            confidence=0.56,
            reason=f"视频内容与挂载信息匹配不足，缺少可核验证据：{missing_text}。建议人工核对 POI/商品/购物车是否误挂。",
            policy_version=policy_version,
            model_version="context_match_rules_v2",
            evidence_refs=[
                EvidenceRef(ref_type="business_context", description=name, text_excerpt=", ".join(tokens[:5]))
                for name, tokens in missing.items()
            ],
        )

    def _match(self, policy_version: str, confidence: float, reason: str) -> DimensionVerdict:
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.NO_VIOLATION,
            confidence=min(confidence, 0.95),
            reason=reason,
            policy_version=policy_version,
            model_version="context_match_rules_v2",
        )
