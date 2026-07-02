"""Stage 5 测试：ws-token、WebSocket 握手/心跳/事件推送、案件锁 TTL、SLA 扫描。"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.app.models import HumanReviewTask
from backend.app.services import ConflictError, GovernanceService


def _past(seconds: int = 60) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _soon(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class CaseLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _ready_task(self, service: GovernanceService) -> str:
        service.ingest_content(
            {
                "title": "daily vlog",
                "description": "an ordinary personal update without enough policy context",
                "creator_id": "c",
            }
        )
        service.drain_pipeline()
        return service.list_queue()["items"][0]["task_id"]

    def _set_lock_expiry(self, service, task_id, value) -> None:
        with service._session_factory.begin() as s:
            s.get(HumanReviewTask, task_id).lock_expires_at = value

    def test_claim_sets_lock_and_blocks_other_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            claimed = service.claim_task(task_id, "reviewer_a")
            self.assertEqual(claimed["task"]["assigned_to"], "reviewer_a")
            self.assertIsNotNone(claimed["task"]["lock_expires_at"])
            # 他人抢锁被拒。
            with self.assertRaises(ConflictError):
                service.claim_task(task_id, "reviewer_b")
            # 本人重复领取 = 幂等续租。
            again = service.claim_task(task_id, "reviewer_a")
            self.assertEqual(again["task"]["assigned_to"], "reviewer_a")

    def test_expired_lock_can_be_taken_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            self._set_lock_expiry(service, task_id, _past())  # 手动令锁过期
            taken = service.claim_task(task_id, "reviewer_b")
            self.assertEqual(taken["task"]["assigned_to"], "reviewer_b")

    def test_heartbeat_extends_lock_and_requires_holder(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            hb = service.heartbeat_task(task_id, "reviewer_a")
            self.assertIn("lock_expires_at", hb)
            with self.assertRaises(ConflictError):
                service.heartbeat_task(task_id, "reviewer_b")  # 非持锁人

    def test_release_frees_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            service.release_task(task_id, "reviewer_a")
            # 释放后他人可领取。
            taken = service.claim_task(task_id, "reviewer_b")
            self.assertEqual(taken["task"]["assigned_to"], "reviewer_b")

    def test_sweep_releases_expired_locks_and_warns_sla(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            self._set_lock_expiry(service, task_id, _past())
            # 令 SLA 进入 30 分钟告警窗口。
            with service._session_factory.begin() as s:
                s.get(HumanReviewTask, task_id).sla_deadline = _soon(300)
            result = service.sweep_locks_and_sla()
            self.assertGreaterEqual(result["expired_locks"], 1)
            self.assertGreaterEqual(result["sla_warnings"], 1)
            # 过期锁已释放。
            with service._session_factory() as s:
                task = s.get(HumanReviewTask, task_id)
                self.assertIsNone(task.assigned_to)
                self.assertTrue(task.sla_warned)
            # 再次 sweep 不重复告警。
            self.assertEqual(service.sweep_locks_and_sla()["sla_warnings"], 0)

    def test_decide_rejects_non_lock_holder(self):
        # 回归（critical）：他人持有效锁时不得裁定。
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            with self.assertRaises(ConflictError):
                service.decide_task(
                    task_id, {"decision": "block", "reason": "hijack", "reviewer_id": "reviewer_b"}
                )
            # 持锁人可正常裁定。
            done = service.decide_task(
                task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_a"}
            )
            self.assertEqual(done["decision"], "pass")

    def test_decide_allowed_when_lock_expired(self):
        # 锁已过期则不再排他，任何审核员可裁定（配合接管语义）。
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            self._set_lock_expiry(service, task_id, _past())
            done = service.decide_task(
                task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_b"}
            )
            self.assertEqual(done["decision"], "pass")

    def test_decide_clears_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "t.sqlite3")
            task_id = self._ready_task(service)
            service.claim_task(task_id, "reviewer_a")
            service.decide_task(task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_a"})
            with service._session_factory() as s:
                task = s.get(HumanReviewTask, task_id)
                self.assertIsNone(task.lock_expires_at)


class WebSocketTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _client(self, tmp):
        from fastapi.testclient import TestClient

        from backend.app.api import create_app

        return TestClient(create_app(db_path=Path(tmp) / "t.sqlite3"))

    def _login(self, client, username):
        return client.post(
            "/api/v1/auth/login", json={"username": username, "password": "demo-pass"}
        ).json()["access_token"]

    def test_ws_token_endpoint_and_handshake_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._client(tmp) as client:
                client.post("/api/v1/dev/seed-users")
                access = self._login(client, "reviewer_demo")
                headers = {"Authorization": f"Bearer {access}"}
                ws_token = client.post("/api/v1/auth/ws-token", headers=headers).json()["ws_token"]

                with client.websocket_connect(f"/ws/review?token={ws_token}") as ws:
                    self.assertEqual(ws.receive_json()["type"], "connected")
                    ws.send_text("HEARTBEAT")
                    self.assertEqual(ws.receive_json()["type"], "HEARTBEAT_ACK")
                    ws.send_text('{"type": "PING"}')
                    self.assertEqual(ws.receive_json()["type"], "PONG")

    def test_ws_rejects_invalid_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._client(tmp) as client:
                with self.assertRaises(Exception):
                    with client.websocket_connect("/ws/review?token=not-a-jwt") as ws:
                        ws.receive_json()

    def test_decision_pushes_event_to_senior(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._client(tmp) as client:
                client.post("/api/v1/dev/seed-users")
                reviewer = {"Authorization": f"Bearer {self._login(client, 'reviewer_demo')}"}
                senior_access = self._login(client, "reviewer_demo")
                senior = {"Authorization": f"Bearer {senior_access}"}
                senior_ws = client.post("/api/v1/auth/ws-token", headers=senior).json()["ws_token"]

                client.post("/api/v1/content/upload", json={"title": "T", "description": "D", "creator_id": "c"})
                client.post("/api/v1/pipeline/drain", json={})
                task_id = client.get("/api/v1/review/human/queue", headers=reviewer).json()["items"][0]["task_id"]

                with client.websocket_connect(f"/ws/review?token={senior_ws}") as ws:
                    self.assertEqual(ws.receive_json()["type"], "connected")
                    client.post(f"/api/v1/review/human/{task_id}/claim", headers=reviewer)
                    client.post(
                        f"/api/v1/review/human/{task_id}/decide",
                        headers=reviewer,
                        json={"decision": "pass", "reason": "ok"},
                    )
                    evt = ws.receive_json()
                    while evt["type"] != "task_decided":
                        evt = ws.receive_json()
                    self.assertEqual(evt["type"], "task_decided")
                    self.assertEqual(evt["payload"]["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
