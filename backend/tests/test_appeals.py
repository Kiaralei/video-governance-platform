"""Stage 7 测试：申诉状态机、独立性、不可加重硬约束、恢复连锁。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.services import ConflictError, GovernanceService, ValidationError


class AppealTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _blocked_content(self, service: GovernanceService, reviewer="reviewer_a") -> str:
        """产出一个被 BLOCK 的内容，返回 content_id。"""
        cid = service.ingest_content(
            {"title": "clip", "description": "neutral content", "creator_id": "creator_x"}
        )["content_id"]
        service.drain_pipeline()
        task_id = service.list_queue()["items"][0]["task_id"]
        service.claim_task(task_id, reviewer)
        service.decide_task(task_id, {"decision": "block", "reason": "policy", "reviewer_id": reviewer})
        return cid

    def _passed_content(self, service: GovernanceService, reviewer="reviewer_a") -> str:
        cid = service.ingest_content(
            {"title": "clip", "description": "neutral content", "creator_id": "creator_y"}
        )["content_id"]
        service.drain_pipeline()
        task_id = service.list_queue()["items"][0]["task_id"]
        service.claim_task(task_id, reviewer)
        service.decide_task(task_id, {"decision": "pass", "reason": "fine", "reviewer_id": reviewer})
        return cid

    def test_appeal_only_on_blocked_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            passed = self._passed_content(service)
            with self.assertRaises(ConflictError):
                service.submit_appeal(passed, "creator_y", "let me through")

    def test_full_overturn_flow_with_recovery_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service, reviewer="reviewer_a")
            appeal = service.submit_appeal(cid, "creator_x", "this was wrong")
            appeal_id = appeal["appeal_id"]
            self.assertEqual(appeal["status"], "open")

            # 独立性：原审核员不能领取二审。
            with self.assertRaises(ConflictError):
                service.assign_appeal(appeal_id, "reviewer_a")

            service.assign_appeal(appeal_id, "reviewer_b")
            result = service.decide_appeal(appeal_id, "reviewer_b", "overturn", "证据不足，改判")
            self.assertEqual(result["status"], "overturned")
            self.assertEqual(result["recovery_chain"]["new_decision"], "pass")

            # 恢复可见性：内容处置回滚为 pass。
            audit = service.get_audit(content_id=cid)
            actions = [a["action"] for a in audit["items"]]
            for chain in ("appeal_overturned", "visibility_restored", "penalty_rolled_back",
                          "qa_negative_feedback", "correction_sample_queued"):
                self.assertIn(chain, actions)

    def test_overturn_cannot_be_reappealed_or_escalated(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service, reviewer="reviewer_a")
            appeal_id = service.submit_appeal(cid, "creator_x", "wrong")["appeal_id"]
            service.assign_appeal(appeal_id, "reviewer_b")
            service.decide_appeal(appeal_id, "reviewer_b", "overturn", "改判")

            # 改判后内容为 pass，不可再申诉（PASS 不可加重到 BLOCK）。
            with self.assertRaises(ConflictError):
                service.submit_appeal(cid, "creator_x", "again")

    def test_reject_keeps_original_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service, reviewer="reviewer_a")
            appeal_id = service.submit_appeal(cid, "creator_x", "please")["appeal_id"]
            service.assign_appeal(appeal_id, "reviewer_b")
            result = service.decide_appeal(appeal_id, "reviewer_b", "reject", "维持原判")
            self.assertEqual(result["status"], "rejected")
            audit_actions = [a["action"] for a in service.get_audit(content_id=cid)["items"]]
            self.assertIn("appeal_rejected", audit_actions)
            self.assertNotIn("appeal_overturned", audit_actions)

    def test_cannot_decide_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service)
            appeal_id = service.submit_appeal(cid, "creator_x", "x")["appeal_id"]
            # open 状态不能直接裁决（必须先 in_review）。
            with self.assertRaises(ConflictError):
                service.decide_appeal(appeal_id, "reviewer_b", "overturn", "y")

    def test_duplicate_open_appeal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service)
            service.submit_appeal(cid, "creator_x", "first")
            with self.assertRaises(ConflictError):
                service.submit_appeal(cid, "creator_x", "second")

    def test_appellant_cannot_self_adjudicate(self):
        # 回归（high）：申诉人不能领取/裁决自己提交的申诉（职责分离）。
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service, reviewer="reviewer_a")
            # 申诉人 = appellant_bob（非原审核员）。
            service.submit_appeal(cid, "appellant_bob", "unfair")
            appeal_id = service.list_appeals()["items"][0]["appeal_id"]
            with self.assertRaises(ConflictError):
                service.assign_appeal(appeal_id, "appellant_bob")
            # 即便绕过领取，裁决也应拒绝申诉人本人。
            service.assign_appeal(appeal_id, "reviewer_b")
            with self.assertRaises(ConflictError):
                service.decide_appeal(appeal_id, "appellant_bob", "overturn", "self")

    def test_independent_reviewer_only_can_decide(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            cid = self._blocked_content(service, reviewer="reviewer_a")
            appeal_id = service.submit_appeal(cid, "creator_x", "x")["appeal_id"]
            service.assign_appeal(appeal_id, "reviewer_b")
            # 非领取人不能裁决。
            with self.assertRaises(ConflictError):
                service.decide_appeal(appeal_id, "reviewer_c", "reject", "y")


class AppealApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def test_appeal_endpoints_rbac_and_flow(self):
        from fastapi.testclient import TestClient

        from backend.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "t.sqlite3")
            with TestClient(app) as client:
                client.post("/api/v1/dev/seed-users")

                def tok(u):
                    return client.post(
                        "/api/v1/auth/login", json={"username": u, "password": "demo-pass"}
                    ).json()["access_token"]

                reviewer = {"Authorization": f"Bearer {tok('reviewer_demo')}"}
                appeal_h = {"Authorization": f"Bearer {tok('admin_demo')}"}

                # 产出一个被 block 的内容。
                cid = client.post(
                    "/api/v1/content/upload", json={"title": "T", "description": "D", "creator_id": "c"}
                ).json()["content_id"]
                client.post("/api/v1/pipeline/drain", json={})
                task_id = client.get("/api/v1/review/human/queue", headers=reviewer).json()["items"][0]["task_id"]
                client.post(f"/api/v1/review/human/{task_id}/claim", headers=reviewer)
                client.post(
                    f"/api/v1/review/human/{task_id}/decide", headers=reviewer,
                    json={"decision": "block", "reason": "bad"},
                )

                # 提交申诉（任意登录用户）。
                appeal_id = client.post(
                    "/api/v1/appeal/submit", headers=reviewer, json={"content_id": cid, "reason": "wrong"}
                ).json()["appeal_id"]

                # reviewer 无 appeal.decide 权限 -> 403。
                self.assertEqual(
                    client.post(f"/api/v1/appeal/{appeal_id}/claim", headers=reviewer).status_code, 409
                )
                # 系统管理员领取 + 改判。
                self.assertEqual(
                    client.post(f"/api/v1/appeal/{appeal_id}/claim", headers=appeal_h).status_code, 200
                )
                decided = client.post(
                    f"/api/v1/appeal/{appeal_id}/decide", headers=appeal_h,
                    json={"outcome": "overturn", "reason": "改判"},
                )
                self.assertEqual(decided.status_code, 200)
                self.assertEqual(decided.json()["status"], "overturned")


if __name__ == "__main__":
    unittest.main()
