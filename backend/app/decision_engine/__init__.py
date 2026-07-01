"""决策引擎（Stage 4）—— 策略注册表 + 多维度并行执行 + 规则引擎"取严链"聚合。

设计要点（对齐 technical-design.md §3）：
- L1 LLM 维度判断层（DimensionVerdict）：大模型只做理解与归因，不出处置动作。
- L2 规则引擎决策层（PolicyDecision）：处置决策的【唯一责任主体】，取严链合并。
- L3 处置动作层：MVP 仅 pass / block，由人审映射。

零改造扩展：新增审核维度只需 ①继承 BaseReviewStrategy ②实现 review()
③在 dimension_registry 表注册。决策引擎、人审、申诉、审计核心代码无需改动。
"""

from __future__ import annotations

from .base import BaseReviewStrategy
from .registry import StrategyRegistry
from .rule_engine import RuleEngine
from .service import DecisionEngineService
from .types import (
    DecisionSummary,
    DimensionDecision,
    DimensionVerdict,
    EvidenceRef,
    PolicyDecision,
    SeveritySuggestion,
    StrategyConfig,
)

# 导入 strategies 触发装饰器注册（副作用导入）。
from . import strategies as _strategies  # noqa: F401

__all__ = [
    "BaseReviewStrategy",
    "StrategyRegistry",
    "RuleEngine",
    "DecisionEngineService",
    "DecisionSummary",
    "DimensionDecision",
    "DimensionVerdict",
    "EvidenceRef",
    "PolicyDecision",
    "SeveritySuggestion",
    "StrategyConfig",
]
