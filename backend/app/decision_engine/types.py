"""决策引擎的值类型（枚举 + 数据类）。

用 dataclass 而非 pydantic：这些是引擎内部结构，无需请求体校验开销，序列化用
to_dict() 显式落库（machine_reviews.verdicts_json / decision_summary_json）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class DimensionDecision(str, Enum):
    """L1：LLM 维度判断层枚举。大模型只输出这一层。"""

    VIOLATION = "VIOLATION"
    NO_VIOLATION = "NO_VIOLATION"
    UNCERTAIN = "UNCERTAIN"


class SeveritySuggestion(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PolicyDecision(str, Enum):
    """L2：规则引擎决策层枚举。处置决策的唯一责任主体输出这一层。"""

    AUTO_PASS = "auto_pass"
    AUTO_BLOCK = "auto_block"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    CRITICAL_ESCALATE = "critical_escalate"


# 取严链：数值越大越严。max() 即"取最严"。
SEVERITY_ORDER: dict[PolicyDecision, int] = {
    PolicyDecision.CRITICAL_ESCALATE: 4,
    PolicyDecision.AUTO_BLOCK: 3,
    PolicyDecision.NEEDS_HUMAN_REVIEW: 2,
    PolicyDecision.AUTO_PASS: 1,
}


# 策略四态生命周期 —— 合法状态转移矩阵（对齐 PRD §8.5）。
class DimensionStatus(str, Enum):
    DRAFT = "draft"
    SHADOW = "shadow"
    ACTIVE = "active"
    ARCHIVED = "archived"


VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    DimensionStatus.DRAFT.value: {DimensionStatus.SHADOW.value},
    DimensionStatus.SHADOW.value: {DimensionStatus.ACTIVE.value, DimensionStatus.DRAFT.value},
    DimensionStatus.ACTIVE.value: {DimensionStatus.ARCHIVED.value, DimensionStatus.SHADOW.value},
    # 停用后允许恢复到草稿重新编辑，再走试运行/审批/上线，避免绕过治理流程直接复活。
    DimensionStatus.ARCHIVED.value: {DimensionStatus.DRAFT.value},
}


@dataclass
class EvidenceRef:
    """可追溯的证据指针（帧 / ASR 片段 / OCR 区域 / 物体检测）。"""

    ref_type: str
    description: str
    frame_id: Optional[str] = None
    timestamp_ms: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    text_excerpt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class StrategyConfig:
    """策略维度配置，从 dimension_registry 表加载。"""

    dimension_id: str
    dimension_name: str
    dimension_axis: str = "safety"  # safety / quality / business
    enabled: bool = True
    llm_review_enabled: bool = True
    auto_block_threshold: float = 0.90
    human_review_threshold: float = 0.50
    prompt_template_id: str = ""
    severity_tiers: dict[str, Any] = field(default_factory=dict)
    jurisdiction_overrides: dict[str, Any] = field(default_factory=dict)
    sor_template_id: str = ""
    status: str = DimensionStatus.DRAFT.value
    version: int = 1


@dataclass
class DimensionVerdict:
    """LLM 对单个策略维度的结构化输出。只做理解归因，不做处置决策。"""

    dimension_id: str
    dimension_name: str
    decision: DimensionDecision
    confidence: float
    reason: str
    policy_version: str
    severity_suggestion: Optional[SeveritySuggestion] = None
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    model_version: str = ""
    source: str = "local_rules"  # local_rules / llm
    llm_unavailable: bool = False
    shadow: bool = False  # shadow 维度不参与最终聚合

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "dimension_name": self.dimension_name,
            "decision": self.decision.value,
            "confidence": round(self.confidence, 4),
            "severity_suggestion": (
                self.severity_suggestion.value if self.severity_suggestion else None
            ),
            "reason": self.reason,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "policy_version": self.policy_version,
            "model_version": self.model_version,
            "source": self.source,
            "llm_unavailable": self.llm_unavailable,
            "shadow": self.shadow,
        }


@dataclass
class DecisionSummary:
    """规则引擎聚合产出的最终机审决策。"""

    final_decision: PolicyDecision
    risk_score: float
    machine_recommendation: str  # pass / block / uncertain
    triggered_rules: list[str] = field(default_factory=list)
    dimension_verdicts: list[DimensionVerdict] = field(default_factory=list)
    shadow_verdicts: list[DimensionVerdict] = field(default_factory=list)
    policy_version: str = ""
    rule_version: str = ""

    def action(self) -> dict[str, Any]:
        publish = self.final_decision == PolicyDecision.AUTO_PASS
        route_to_human = self.final_decision == PolicyDecision.NEEDS_HUMAN_REVIEW
        priority = "high" if self.final_decision == PolicyDecision.CRITICAL_ESCALATE else "normal"
        return {
            "publish": publish,
            "route_to_human_review": route_to_human,
            "priority": priority,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_decision": self.final_decision.value,
            "risk_score": round(self.risk_score, 4),
            "machine_recommendation": self.machine_recommendation,
            "triggered_rules": self.triggered_rules,
            "action": self.action(),
            "policy_version": self.policy_version,
            "rule_version": self.rule_version,
            "shadow_verdicts": [v.to_dict() for v in self.shadow_verdicts],
        }
