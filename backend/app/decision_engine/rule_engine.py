"""RuleEngine —— 处置决策的唯一责任主体。

大模型负责理解归因（DimensionVerdict / L1），规则引擎负责最终动作（PolicyDecision / L2）。
聚合走"取严链"：max(各维度决策, key=严重度)。
"""

from __future__ import annotations

from typing import Any, Optional

from .registry import StrategyRegistry
from .types import (
    SEVERITY_ORDER,
    DecisionSummary,
    DimensionDecision,
    DimensionVerdict,
    PolicyDecision,
    SeveritySuggestion,
    StrategyConfig,
)


# needs_human_review -> "uncertain"（v3.0 修复）：不偏向拦截，让审核员基于证据独立判断。
_RECOMMENDATION_MAP = {
    PolicyDecision.AUTO_PASS: "pass",
    PolicyDecision.AUTO_BLOCK: "block",
    PolicyDecision.NEEDS_HUMAN_REVIEW: "uncertain",
    PolicyDecision.CRITICAL_ESCALATE: "block",
}

# 各最终决策的 risk_score 下限：被拦截/待复核的内容不应报 0 风险分。
_RISK_FLOOR = {
    PolicyDecision.AUTO_PASS: 0.0,
    PolicyDecision.NEEDS_HUMAN_REVIEW: 0.5,
    PolicyDecision.AUTO_BLOCK: 0.9,
    PolicyDecision.CRITICAL_ESCALATE: 0.95,
}


class RuleEngine:
    def __init__(self, registry: Optional[StrategyRegistry] = None):
        self.registry = registry or StrategyRegistry.get_instance()

    def aggregate(
        self,
        verdicts: list[DimensionVerdict],
        evidence: dict[str, Any],
        policy_version: str = "",
        rule_version: str = "",
        shadow_verdicts: Optional[list[DimensionVerdict]] = None,
    ) -> DecisionSummary:
        """聚合所有信号产出最终决策。

        优先级：
          1. CSAM 哈希命中 -> CRITICAL_ESCALATE（短路）
          2. 初筛云 API 高置信 critical/high 命中 -> AUTO_BLOCK / CRITICAL_ESCALATE
          3. 逐维度 DimensionVerdict -> 按阈值映射
          4. 取严链合并 -> 取最严
          5. 全部低风险 / 无信号 -> AUTO_PASS
        """
        triggered_rules: list[str] = []
        decisions: list[PolicyDecision] = []
        pre_filter = evidence.get("pre_filter_results", {}) or {}

        # 规则 1：CSAM 哈希命中 —— 强制 critical，短路。
        if pre_filter.get("csam_hash_hit"):
            triggered_rules.append("csam_hash_hit")
            return DecisionSummary(
                final_decision=PolicyDecision.CRITICAL_ESCALATE,
                risk_score=1.0,
                machine_recommendation=_RECOMMENDATION_MAP[PolicyDecision.CRITICAL_ESCALATE],
                triggered_rules=triggered_rules,
                dimension_verdicts=verdicts,
                shadow_verdicts=shadow_verdicts or [],
                policy_version=policy_version,
                rule_version=rule_version,
            )

        # risk_score 累积所有风险信号（违规维度置信度 + 云 API 命中置信度）。
        risk_score = 0.0

        # 规则 2：初筛云 API 高置信命中。
        for hit in pre_filter.get("cloud_api_hits", []) or []:
            severity = str(hit.get("severity", "")).lower()
            confidence = float(hit.get("confidence", 0.0))
            if confidence >= 0.90 and severity in ("critical", "high"):
                mapped = (
                    PolicyDecision.CRITICAL_ESCALATE
                    if severity == "critical"
                    else PolicyDecision.AUTO_BLOCK
                )
                decisions.append(mapped)
                triggered_rules.append(f"cloud_api:{hit.get('rule_id', severity)}")
                risk_score = max(risk_score, confidence)

        # 规则 3：逐维度评估。
        snapshot = self.registry.configs_snapshot()
        for verdict in verdicts:
            config = snapshot.get(verdict.dimension_id)
            per_dim = self._evaluate_verdict(verdict, config)
            decisions.append(per_dim)
            if per_dim != PolicyDecision.AUTO_PASS:
                triggered_rules.append(f"{verdict.dimension_id}:{per_dim.value}")
            # 违规维度贡献其置信度；UNCERTAIN（不确定）也计入一个基准风险，避免"进人审却 0 分"。
            if verdict.decision == DimensionDecision.VIOLATION:
                risk_score = max(risk_score, verdict.confidence)
            elif verdict.decision == DimensionDecision.UNCERTAIN:
                risk_score = max(risk_score, 0.5)

        # 规则 4：取严链合并。
        if decisions:
            final = max(decisions, key=lambda d: SEVERITY_ORDER[d])
        else:
            final = PolicyDecision.AUTO_PASS

        # 按最终决策施加 risk_score 下限/上限，保证"被拦截/待复核"内容不会报 0 分。
        risk_score = max(risk_score, _RISK_FLOOR[final])
        if final == PolicyDecision.AUTO_PASS:
            risk_score = min(risk_score, 0.2)

        return DecisionSummary(
            final_decision=final,
            risk_score=risk_score,
            machine_recommendation=_RECOMMENDATION_MAP[final],
            triggered_rules=triggered_rules,
            dimension_verdicts=verdicts,
            shadow_verdicts=shadow_verdicts or [],
            policy_version=policy_version,
            rule_version=rule_version,
        )

    def _evaluate_verdict(
        self, verdict: DimensionVerdict, config: Optional[StrategyConfig]
    ) -> PolicyDecision:
        """单维度评估映射规则。"""
        auto_threshold = config.auto_block_threshold if config else 0.90
        review_threshold = config.human_review_threshold if config else 0.50

        # LLM 不可用 / 不确定 -> 交人审。
        if verdict.llm_unavailable or verdict.decision == DimensionDecision.UNCERTAIN:
            return PolicyDecision.NEEDS_HUMAN_REVIEW

        if verdict.decision == DimensionDecision.VIOLATION:
            if (
                verdict.severity_suggestion == SeveritySuggestion.CRITICAL
                and verdict.confidence >= auto_threshold
            ):
                return PolicyDecision.CRITICAL_ESCALATE
            if verdict.confidence >= auto_threshold:
                return PolicyDecision.AUTO_BLOCK
            if verdict.confidence >= review_threshold:
                return PolicyDecision.NEEDS_HUMAN_REVIEW
            # 低置信违规：仍偏保守，进人审而非直接放行。
            return PolicyDecision.NEEDS_HUMAN_REVIEW

        # NO_VIOLATION
        return PolicyDecision.AUTO_PASS
