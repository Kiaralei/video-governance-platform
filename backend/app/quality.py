"""Stage 8：质检 + 数据回流工具。对齐设计 §4.3 / §6。

- Fleiss' Kappa（评估者间信度 IRR）。
- 数据回流四类样本分类 + quality gate。
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Optional


KAPPA_THRESHOLD = 0.80


class FlywheelSource(str, Enum):
    GROUND_TRUTH = "ground_truth"   # 机审与人审一致 -> 高置信正样本
    DISAGREEMENT = "disagreement"   # 机审 != 人审 -> 纠错样本（overkill / miss）
    GOLDEN = "golden"               # 黄金题 -> 校准样本
    CORRECTION = "correction"       # 申诉改判 -> 改判样本


def fleiss_kappa(ratings: list[list[str]], categories: Optional[list[str]] = None) -> dict:
    """Fleiss' Kappa。ratings: 每个 item 一个评分列表（同一 item 多个评审者的裁定）。

    kappa = (Pbar - Pe) / (1 - Pe)
    仅统计评审者数 >= 2 的 item。
    """
    items = [r for r in ratings if len(r) >= 2]
    n_items = len(items)
    if n_items == 0:
        return {"kappa": None, "items": 0, "note": "样本不足（需每项至少 2 个评审者）"}

    if categories is None:
        cats = sorted({c for r in items for c in r})
    else:
        cats = list(categories)

    # 每 item 的评审者数可不同：P_i = (sum n_ij^2 - n_i) / (n_i (n_i - 1))
    p_is = []
    category_totals = Counter()
    total_ratings = 0
    for r in items:
        counts = Counter(r)
        n_i = len(r)
        total_ratings += n_i
        for c in cats:
            category_totals[c] += counts.get(c, 0)
        sum_sq = sum(counts.get(c, 0) ** 2 for c in cats)
        p_i = (sum_sq - n_i) / (n_i * (n_i - 1)) if n_i > 1 else 1.0
        p_is.append(p_i)

    p_bar = sum(p_is) / n_items
    p_e = sum((category_totals[c] / total_ratings) ** 2 for c in cats) if total_ratings else 0.0
    # p_e >= 1.0：所有评分落在同一类别，无区分度，kappa 数学上未定义（0/0）。
    # 不能报 1.0"完美一致"，否则会把退化/失灵的流水线误判为高信度并通过质量门。
    if p_e >= 1.0:
        return {
            "kappa": None,
            "p_observed": round(p_bar, 4),
            "p_expected": round(p_e, 4),
            "items": n_items,
            "categories": cats,
            "meets_threshold": False,
            "threshold": KAPPA_THRESHOLD,
            "note": "无区分度（所有裁定同一类别），kappa 未定义",
        }
    kappa = (p_bar - p_e) / (1.0 - p_e)
    return {
        "kappa": round(kappa, 4),
        "p_observed": round(p_bar, 4),
        "p_expected": round(p_e, 4),
        "items": n_items,
        "categories": cats,
        "meets_threshold": kappa >= KAPPA_THRESHOLD,
        "threshold": KAPPA_THRESHOLD,
    }


def classify_sample(machine_recommendation: str, human_decision: str) -> tuple[str, str]:
    """按机审建议 vs 人审裁定给出 (source_type, error_type)。

    error_type: overkill(机审过严：机 block 人 pass) / miss(机审漏放：机 pass 人 block)。
    """
    machine = (machine_recommendation or "").lower()
    human = (human_decision or "").lower()

    if machine in ("pass", "block") and machine != human:
        if machine == "block" and human == "pass":
            return FlywheelSource.DISAGREEMENT.value, "overkill"
        if machine == "pass" and human == "block":
            return FlywheelSource.DISAGREEMENT.value, "miss"
        return FlywheelSource.DISAGREEMENT.value, ""
    # 机审 uncertain 或与人审一致 -> 人审确立的地面真值。
    return FlywheelSource.GROUND_TRUTH.value, ""


def passes_quality_gate(source_type: str, is_golden_correct: Optional[bool]) -> bool:
    """质量门：黄金题仅取答对的样本；其余四类默认入池。"""
    if source_type == FlywheelSource.GOLDEN.value:
        return bool(is_golden_correct)
    return True
