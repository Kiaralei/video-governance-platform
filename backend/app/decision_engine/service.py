"""DecisionEngineService —— 编排所有已注册策略的执行，调用规则引擎聚合最终决策。

多维度并行：用 ThreadPoolExecutor 并发跑各维度 review()，单策略 25s 超时，异常/超时降级为
UNCERTAIN（进人审），互不影响。shadow 维度并行评估但不参与聚合。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Optional

from .base import BaseReviewStrategy
from .registry import StrategyRegistry
from .rule_engine import RuleEngine
from .types import DecisionSummary, DimensionDecision, DimensionVerdict

STRATEGY_TIMEOUT_SECONDS = 25.0
MAX_PARALLELISM = 8


class DecisionEngineService:
    def __init__(self, registry: Optional[StrategyRegistry] = None):
        self.registry = registry or StrategyRegistry.get_instance()
        self.rule_engine = RuleEngine(self.registry)

    def run(
        self,
        evidence: dict[str, Any],
        policy_version: str = "",
        rule_version: str = "",
        jurisdiction: str = "global",
    ) -> DecisionSummary:
        """跑完整机审：并行执行 active + shadow 维度，聚合 active 维度产出决策。"""
        active = self.registry.get_active_strategies(jurisdiction)
        shadow = self.registry.get_shadow_strategies(jurisdiction)

        active_verdicts = self._run_strategies(active, evidence, policy_version, is_shadow=False)
        shadow_verdicts = self._run_strategies(shadow, evidence, policy_version, is_shadow=True)

        return self.rule_engine.aggregate(
            verdicts=active_verdicts,
            evidence=evidence,
            policy_version=policy_version,
            rule_version=rule_version,
            shadow_verdicts=shadow_verdicts,
        )

    def _run_strategies(
        self,
        strategies: list[BaseReviewStrategy],
        evidence: dict[str, Any],
        policy_version: str,
        is_shadow: bool,
    ) -> list[DimensionVerdict]:
        if not strategies:
            return []
        verdicts: list[DimensionVerdict] = []
        workers = min(MAX_PARALLELISM, len(strategies))
        # 不用 `with` 上下文：其 __exit__ 会 shutdown(wait=True) 阻塞在卡死的 review() 线程上。
        # 这里用 wait(timeout) 对整批设总超时（并发，非逐个串行等待），再 shutdown(wait=False,
        # cancel_futures=True) 立即返回 —— 卡死的策略线程自行了结（各自还有网络超时），不阻塞主流程。
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            future_map = {
                pool.submit(strategy.review, evidence, policy_version): strategy
                for strategy in strategies
            }
            done, not_done = wait(future_map.keys(), timeout=STRATEGY_TIMEOUT_SECONDS)
            for future in done:
                strategy = future_map[future]
                try:
                    verdict = future.result()
                except Exception as exc:  # 单策略异常降级，不影响其他维度
                    verdict = self._degraded(
                        strategy, policy_version, f"策略执行异常: {type(exc).__name__}"
                    )
                verdict.shadow = is_shadow
                verdicts.append(verdict)
            for future in not_done:
                strategy = future_map[future]
                verdict = self._degraded(strategy, policy_version, "策略执行超时")
                verdict.shadow = is_shadow
                verdicts.append(verdict)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        # 稳定排序，保证落库/断言的可确定性。
        verdicts.sort(key=lambda v: v.dimension_id)
        return verdicts

    def _degraded(
        self, strategy: BaseReviewStrategy, policy_version: str, reason: str
    ) -> DimensionVerdict:
        return DimensionVerdict(
            dimension_id=strategy.dimension_id,
            dimension_name=strategy.dimension_name,
            decision=DimensionDecision.UNCERTAIN,
            confidence=0.0,
            reason=reason,
            policy_version=policy_version,
            model_version="",
            source="local_rules",
            llm_unavailable=True,
        )
