"""Stage 9 测试：审计哈希链校验、Prometheus 指标、SoR 对外理由。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.models import AuditLog
from backend.app.observability import render_prometheus
from backend.app.services import GovernanceService


GAMBLING = {
    "title": "gambling promo",
    "description": "scan the qr to claim your betting bonus at our casino",
    "creator_id": "creator_bet",
}


class AuditIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_intact_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            service.ingest_content(GAMBLING)
            service.drain_pipeline()
            result = service.verify_audit_integrity()
            self.assertTrue(result["valid"])
            self.assertGreater(result["checked"], 0)
            self.assertIsNone(result["break_point"])

    def test_tampered_entry_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            service.ingest_content(GAMBLING)
            service.drain_pipeline()
            # 篡改一条审计的 detail，entry_hash 不再匹配。
            with service._session_factory.begin() as s:
                row = s.execute(AuditLog.__table__.select()).first()
                s.get(AuditLog, row.id).detail_json = '{"tampered": true}'
            result = service.verify_audit_integrity()
            self.assertFalse(result["valid"])
            self.assertIsNotNone(result["break_point"])


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_metrics_snapshot_renders_prometheus(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            service.ingest_content(GAMBLING)
            service.drain_pipeline()
            text = render_prometheus(service.metrics_snapshot())
            self.assertIn("vgp_human_review_queue_size", text)
            self.assertIn("vgp_pipeline_decision_total", text)
            self.assertIn("# TYPE vgp_pipeline_jobs gauge", text)


class SoRTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_sor_for_blocked_content_excludes_internal_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = service.ingest_content(GAMBLING)["content_id"]
            service.drain_pipeline()
            task_id = service.list_queue()["items"][0]["task_id"]
            service.claim_task(task_id, "reviewer_a")
            service.decide_task(
                task_id,
                {"decision": "block", "reason": "INTERNAL-secret-threshold-0.9", "reviewer_id": "reviewer_a"},
            )
            sor = service.generate_sor(cid)
            self.assertEqual(sor["decision"], "block")
            self.assertIn("未通过", sor["sor_text"])
            self.assertIn("dim_gambling", sor["triggered_dimensions"])
            # 对外理由绝不泄露内部理由。
            self.assertNotIn("INTERNAL", sor["sor_text"])
            self.assertFalse(sor["contains_internal_reason"])


class ObservabilityApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_endpoints(self):
        from fastapi.testclient import TestClient

        from backend.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "t.sqlite3")
            with TestClient(app) as client:
                client.post("/api/v1/dev/seed-users")
                client.post("/api/v1/content/upload", json={"title": "T", "description": "D", "creator_id": "c"})
                client.post("/api/v1/pipeline/drain", json={})

                # /metrics 公开可抓取。
                metrics = client.get("/metrics")
                self.assertEqual(metrics.status_code, 200)
                self.assertIn("vgp_human_review_queue_size", metrics.text)

                # 健康/就绪。
                self.assertEqual(client.get("/api/v1/system/health").json()["status"], "ok")
                self.assertTrue(client.get("/api/v1/system/ready").json()["ready"])

                # 审计完整性校验需 audit.read（compliance_auditor / policy_pm）。
                self.assertEqual(client.post("/api/v1/audit/integrity/verify").status_code, 401)
                pm = client.post(
                    "/api/v1/auth/login", json={"username": "policy_pm_demo", "password": "demo-pass"}
                ).json()["access_token"]
                verify = client.post(
                    "/api/v1/audit/integrity/verify", headers={"Authorization": f"Bearer {pm}"}
                )
                self.assertEqual(verify.status_code, 200)
                self.assertTrue(verify.json()["valid"])


if __name__ == "__main__":
    unittest.main()
