"""Stage 4 决策引擎测试：策略注册表、多维度并行、取严链聚合、四态生命周期、零改造扩展。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.decision_engine import (
    BaseReviewStrategy,
    DecisionEngineService,
    RuleEngine,
    StrategyRegistry,
)
from backend.app.decision_engine.types import (
    DimensionDecision,
    DimensionVerdict,
    PolicyDecision,
    SeveritySuggestion,
    StrategyConfig,
)
from backend.app.services import GovernanceService


# 注册一个测试专用策略，验证"零改造扩展新维度" —— 只需继承 + 实现 review + 注册。
@StrategyRegistry.register("dim_test_custom")
class _AlwaysViolationStrategy(BaseReviewStrategy):
    def build_prompt(self, evidence):
        return ""

    def review(self, evidence, policy_version):
        return DimensionVerdict(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            decision=DimensionDecision.VIOLATION,
            confidence=0.99,
            severity_suggestion=SeveritySuggestion.HIGH,
            reason="test always violation",
            policy_version=policy_version,
        )


def _config(dimension_id: str, **kw) -> StrategyConfig:
    return StrategyConfig(dimension_id=dimension_id, dimension_name=dimension_id, **kw)


class RuleEngineTest(unittest.TestCase):
    """规则引擎取严链 + L1->L2 映射，纯单元测试。"""

    def setUp(self) -> None:
        self.registry = StrategyRegistry()
        self.registry.load_configs(
            {
                "dim_a": _config("dim_a", auto_block_threshold=0.90, human_review_threshold=0.50),
                "dim_b": _config("dim_b", auto_block_threshold=0.90, human_review_threshold=0.50),
            }
        )
        self.engine = RuleEngine(self.registry)

    def _verdict(self, dimension_id, decision, confidence, severity=None):
        return DimensionVerdict(
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            decision=decision,
            confidence=confidence,
            severity_suggestion=severity,
            reason="",
            policy_version="pv_1",
        )

    def test_all_no_violation_auto_pass(self):
        verdicts = [
            self._verdict("dim_a", DimensionDecision.NO_VIOLATION, 0.9),
            self._verdict("dim_b", DimensionDecision.NO_VIOLATION, 0.9),
        ]
        summary = self.engine.aggregate(verdicts, {"pre_filter_results": {}})
        self.assertEqual(summary.final_decision, PolicyDecision.AUTO_PASS)
        self.assertEqual(summary.machine_recommendation, "pass")

    def test_strictest_wins(self):
        # 一个 NO_VIOLATION + 一个高置信 VIOLATION -> 取最严 auto_block。
        verdicts = [
            self._verdict("dim_a", DimensionDecision.NO_VIOLATION, 0.95),
            self._verdict("dim_b", DimensionDecision.VIOLATION, 0.95),
        ]
        summary = self.engine.aggregate(verdicts, {"pre_filter_results": {}})
        self.assertEqual(summary.final_decision, PolicyDecision.AUTO_BLOCK)
        self.assertEqual(summary.machine_recommendation, "block")

    def test_uncertain_maps_to_needs_human_and_uncertain_recommendation(self):
        verdicts = [self._verdict("dim_a", DimensionDecision.UNCERTAIN, 0.0)]
        summary = self.engine.aggregate(verdicts, {"pre_filter_results": {}})
        self.assertEqual(summary.final_decision, PolicyDecision.NEEDS_HUMAN_REVIEW)
        # v3.0 关键修复：needs_human_review -> "uncertain"，不偏向 block。
        self.assertEqual(summary.machine_recommendation, "uncertain")

    def test_low_confidence_violation_needs_human(self):
        verdicts = [self._verdict("dim_a", DimensionDecision.VIOLATION, 0.6)]
        summary = self.engine.aggregate(verdicts, {"pre_filter_results": {}})
        self.assertEqual(summary.final_decision, PolicyDecision.NEEDS_HUMAN_REVIEW)

    def test_critical_severity_escalates(self):
        verdicts = [
            self._verdict("dim_a", DimensionDecision.VIOLATION, 0.95, SeveritySuggestion.CRITICAL)
        ]
        summary = self.engine.aggregate(verdicts, {"pre_filter_results": {}})
        self.assertEqual(summary.final_decision, PolicyDecision.CRITICAL_ESCALATE)

    def test_csam_hash_short_circuits(self):
        summary = self.engine.aggregate(
            [self._verdict("dim_a", DimensionDecision.NO_VIOLATION, 0.99)],
            {"pre_filter_results": {"csam_hash_hit": True}},
        )
        self.assertEqual(summary.final_decision, PolicyDecision.CRITICAL_ESCALATE)
        self.assertIn("csam_hash_hit", summary.triggered_rules)

    def test_cloud_api_high_confidence_blocks(self):
        summary = self.engine.aggregate(
            [self._verdict("dim_a", DimensionDecision.NO_VIOLATION, 0.99)],
            {"pre_filter_results": {"cloud_api_hits": [{"severity": "high", "confidence": 0.95, "rule_id": "porn"}]}},
        )
        self.assertEqual(summary.final_decision, PolicyDecision.AUTO_BLOCK)

    def test_cloud_api_block_reports_nonzero_risk_score(self):
        # 回归：被拦截内容不应报 risk_score=0.0（review 发现的 bug）。
        summary = self.engine.aggregate(
            [],
            {"pre_filter_results": {"cloud_api_hits": [{"severity": "high", "confidence": 0.97, "rule_id": "nudity"}]}},
        )
        self.assertEqual(summary.final_decision, PolicyDecision.AUTO_BLOCK)
        self.assertGreaterEqual(summary.risk_score, 0.9)

    def test_uncertain_needs_human_reports_nonzero_risk_score(self):
        # 回归：UNCERTAIN 驱动的待复核不应报 risk_score=0.0。
        summary = self.engine.aggregate(
            [self._verdict("dim_a", DimensionDecision.UNCERTAIN, 0.0)],
            {"pre_filter_results": {}},
        )
        self.assertEqual(summary.final_decision, PolicyDecision.NEEDS_HUMAN_REVIEW)
        self.assertGreaterEqual(summary.risk_score, 0.5)


class DecisionEngineParallelTest(unittest.TestCase):
    def test_strategy_exception_degrades_to_uncertain(self):
        registry = StrategyRegistry()

        @StrategyRegistry.register("dim_boom")
        class _BoomStrategy(BaseReviewStrategy):
            def build_prompt(self, evidence):
                return ""

            def review(self, evidence, policy_version):
                raise RuntimeError("boom")

        registry.load_configs({"dim_boom": _config("dim_boom", status="active")})
        service = DecisionEngineService(registry)
        summary = service.run({"pre_filter_results": {}}, policy_version="pv_1")
        # 单策略异常 -> UNCERTAIN -> needs_human_review，不影响其他维度。
        self.assertEqual(summary.final_decision, PolicyDecision.NEEDS_HUMAN_REVIEW)
        self.assertTrue(summary.dimension_verdicts[0].llm_unavailable)

    def test_hung_strategy_times_out_without_blocking(self):
        # 回归：卡死的 review() 不应把整条决策流程阻塞在 shutdown(wait=True) 上。
        import time as _time

        from backend.app.decision_engine import service as service_module

        registry = StrategyRegistry()

        @StrategyRegistry.register("dim_hang")
        class _HangStrategy(BaseReviewStrategy):
            def build_prompt(self, evidence):
                return ""

            def review(self, evidence, policy_version):
                _time.sleep(3)  # 远超 0.3s 超时阈值，模拟卡死的网络调用
                return None  # 不会被采纳（已超时降级）

        registry.load_configs({"dim_hang": _config("dim_hang", status="active")})
        with patch.object(service_module, "STRATEGY_TIMEOUT_SECONDS", 0.3):
            engine = DecisionEngineService(registry)
            started = _time.monotonic()
            summary = engine.run({"pre_filter_results": {}}, policy_version="pv_1")
            elapsed = _time.monotonic() - started
        # 应在超时阈值附近返回（远小于 30s 的 sleep），且降级为 UNCERTAIN。
        self.assertLess(elapsed, 5.0)
        self.assertEqual(summary.dimension_verdicts[0].decision, DimensionDecision.UNCERTAIN)
        self.assertTrue(summary.dimension_verdicts[0].llm_unavailable)


class RegistryHotReloadTest(unittest.TestCase):
    def test_copy_on_write_reload_swaps_snapshot(self):
        registry = StrategyRegistry()
        registry.load_configs({"dim_a": _config("dim_a", status="active")})
        first = registry.configs_snapshot()
        registry.load_configs({"dim_a": _config("dim_a", status="shadow")})
        second = registry.configs_snapshot()
        # 旧快照对象不被原地修改（copy-on-write）。
        self.assertEqual(first["dim_a"].status, "active")
        self.assertEqual(second["dim_a"].status, "shadow")
        self.assertIsNot(first, second)


class ServiceIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _service(self, tmp) -> GovernanceService:
        return GovernanceService(Path(tmp) / "test.sqlite3")

    def test_gambling_content_blocks_via_strictest_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            queued = service.ingest_content(
                {
                    "title": "gambling promo",
                    "description": "scan the qr to claim your betting bonus at our casino",
                    "creator_id": "creator_bet",
                }
            )
            service.drain_pipeline()
            detail = service.get_machine_review(queued["content_id"])
            summary = detail["decision_summary"]
            # 博彩 + 引流(qr/scan) -> critical_escalate；取严链盖过其他 pass 维度。
            self.assertIn(summary["final_decision"], ("auto_block", "critical_escalate"))
            self.assertEqual(detail["recommendation"], "block")
            gambling = [v for v in detail["verdicts"] if v["dimension_id"] == "dim_gambling"][0]
            self.assertEqual(gambling["decision"], "VIOLATION")

    def test_seeded_dimensions_are_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            dims = service.list_dimensions()["items"]
            ids = {d["dimension_id"] for d in dims}
            self.assertIn("dim_general_policy", ids)
            self.assertIn("dim_gambling", ids)
            self.assertTrue(all(d["status"] == "active" for d in dims if d["dimension_id"] != "dim_test_custom"))

    def test_lifecycle_transitions_and_maker_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_dimension(
                {"dimension_id": "dim_test_custom", "dimension_name": "测试维度", "enabled": True},
                actor="pm_1",
            )
            # 非法转移：draft -> active 直接跳级应被拒。
            with self.assertRaises(Exception):
                service.transition_dimension("dim_test_custom", "active", actor="pm_1")
            # draft -> shadow 合法。
            service.transition_dimension("dim_test_custom", "shadow", actor="pm_1")
            # shadow -> active 需先审批，且审批人不能是创建人。
            with self.assertRaises(Exception):
                service.transition_dimension("dim_test_custom", "active", actor="pm_1")
            with self.assertRaises(Exception):
                service.approve_dimension("dim_test_custom", actor="pm_1")  # maker==checker
            service.approve_dimension("dim_test_custom", actor="approver_1")
            service.transition_dimension("dim_test_custom", "active", actor="pm_1")
            dims = {d["dimension_id"]: d for d in service.list_dimensions()["items"]}
            self.assertEqual(dims["dim_test_custom"]["status"], "active")

    def test_active_dimension_config_is_frozen_against_single_actor(self):
        # 回归：单人不能在生产悄悄削弱已上线维度（绕过 Maker-Checker）。
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_dimension(
                {"dimension_id": "dim_test_custom", "dimension_name": "测试维度", "enabled": True},
                actor="pm_1",
            )
            service.transition_dimension("dim_test_custom", "shadow", actor="pm_1")
            service.approve_dimension("dim_test_custom", actor="approver_1")
            service.transition_dimension("dim_test_custom", "active", actor="pm_1")

            # active 时改治理敏感字段应被拒。
            with self.assertRaises(Exception):
                service.update_dimension("dim_test_custom", {"auto_block_threshold": 0.0}, actor="pm_1")

            # 回退到 shadow 会作废旧审批：直接再上线应被拒（需重新签核）。
            service.transition_dimension("dim_test_custom", "shadow", actor="pm_1")
            service.update_dimension("dim_test_custom", {"auto_block_threshold": 0.0}, actor="pm_1")
            with self.assertRaises(Exception):
                service.transition_dimension("dim_test_custom", "active", actor="pm_1")
            # 重新独立签核后方可上线。
            service.approve_dimension("dim_test_custom", actor="approver_1")
            service.transition_dimension("dim_test_custom", "active", actor="pm_1")
            dims = {d["dimension_id"]: d for d in service.list_dimensions()["items"]}
            self.assertEqual(dims["dim_test_custom"]["status"], "active")

    def test_zero_modification_new_dimension_takes_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            # 上线一个恒返回 VIOLATION 的自定义维度（走完整生命周期）。
            service.create_dimension(
                {"dimension_id": "dim_test_custom", "dimension_name": "测试维度", "enabled": True},
                actor="pm_1",
            )
            service.transition_dimension("dim_test_custom", "shadow", actor="pm_1")
            service.approve_dimension("dim_test_custom", actor="approver_1")
            service.transition_dimension("dim_test_custom", "active", actor="pm_1")

            queued = service.ingest_content(
                {"title": "neutral", "description": "a calm cooking clip", "creator_id": "c"}
            )
            service.drain_pipeline()
            detail = service.get_machine_review(queued["content_id"])
            ids = {v["dimension_id"] for v in detail["verdicts"]}
            # 新维度无需改动引擎即被纳入并行执行与聚合。
            self.assertIn("dim_test_custom", ids)
            self.assertEqual(detail["recommendation"], "block")  # 恒违规 0.99 -> auto_block

    def test_shadow_dimension_does_not_affect_final_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.create_dimension(
                {"dimension_id": "dim_test_custom", "dimension_name": "测试维度", "enabled": True},
                actor="pm_1",
            )
            service.transition_dimension("dim_test_custom", "shadow", actor="pm_1")

            queued = service.ingest_content(
                {"title": "neutral", "description": "a calm cooking clip", "creator_id": "c"}
            )
            service.drain_pipeline()
            detail = service.get_machine_review(queued["content_id"])
            summary = detail["decision_summary"]
            # shadow 维度并行评估但不进最终聚合：中性内容仍 auto_pass。
            self.assertEqual(summary["final_decision"], "auto_pass")
            shadow_ids = {v["dimension_id"] for v in summary["shadow_verdicts"]}
            self.assertIn("dim_test_custom", shadow_ids)


class PolicyApiRbacTest(unittest.TestCase):
    def test_policy_endpoints_enforce_rbac(self):
        from fastapi.testclient import TestClient

        from backend.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "test.sqlite3")
            with TestClient(app) as client:
                client.post("/api/v1/dev/seed-users")

                def token(username):
                    return client.post(
                        "/api/v1/auth/login", json={"username": username, "password": "demo-pass"}
                    ).json()["access_token"]

                reviewer = {"Authorization": f"Bearer {token('reviewer_demo')}"}
                pm = {"Authorization": f"Bearer {token('policy_pm_demo')}"}
                approver = {"Authorization": f"Bearer {token('policy_approver_demo')}"}

                # 未认证 -> 401
                self.assertEqual(client.get("/api/v1/policy/dimensions").status_code, 401)
                # reviewer 无策略读权限 -> 403
                self.assertEqual(client.get("/api/v1/policy/dimensions", headers=reviewer).status_code, 403)
                # pm 可读
                self.assertEqual(client.get("/api/v1/policy/dimensions", headers=pm).status_code, 200)
                # pm 建维度（走完整生命周期）
                created = client.post(
                    "/api/v1/policy/dimensions",
                    headers=pm,
                    json={"dimension_id": "dim_test_custom", "dimension_name": "测试", "enabled": True},
                )
                self.assertEqual(created.status_code, 200)
                # reviewer 无写权限 -> 403
                self.assertEqual(
                    client.post(
                        "/api/v1/policy/dimensions",
                        headers=reviewer,
                        json={"dimension_id": "dim_x", "dimension_name": "x"},
                    ).status_code,
                    403,
                )
                # pm 转 shadow，approver 审批，pm 上线
                self.assertEqual(
                    client.post(
                        "/api/v1/policy/dimensions/dim_test_custom/transition",
                        headers=pm,
                        json={"target_status": "shadow"},
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/policy/dimensions/dim_test_custom/approve", headers=approver
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/policy/dimensions/dim_test_custom/transition",
                        headers=pm,
                        json={"target_status": "active"},
                    ).status_code,
                    200,
                )


if __name__ == "__main__":
    unittest.main()
