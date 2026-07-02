"""Stage 6 测试：优先级队列、原子领取、独立性约束、反疲劳（CSAM 曝光 + 强制休息）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.app import services as services_module
from backend.app.config import settings as base_settings
from backend.app.models import HumanReviewTask
from backend.app.services import GovernanceService, new_id, now_iso


GAMBLING = {
    "title": "gambling promo",
    "description": "scan the qr to claim your betting bonus at our casino",
    "creator_id": "creator_bet",
}
NEUTRAL = {
    "title": "daily vlog",
    "description": "an ordinary personal update without enough policy context",
    "creator_id": "c",
}


class ReviewQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _service(self, tmp) -> GovernanceService:
        return GovernanceService(Path(tmp) / "t.sqlite3")

    def _ingest(self, service, payload) -> str:
        cid = service.ingest_content(payload)["content_id"]
        return cid

    def test_priority_ordering_critical_before_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._ingest(service, NEUTRAL)
            self._ingest(service, {"title": "daily vlog two", "description": "another ordinary update", "creator_id": "c"})
            service.drain_pipeline()
            queue = service.list_queue()["items"]
            with service._session_factory.begin() as s:
                task = s.get(HumanReviewTask, queue[1]["task_id"])
                task.priority = 1
                task.is_sensitive = True

            # 队列按优先级排序：priority=1 的任务排在常规任务之前。
            queue = service.list_queue()["items"]
            self.assertEqual(queue[0]["priority"], 1)
            self.assertTrue(queue[0]["is_sensitive"])

            # fetch_next 领到的是最高优先级案件。
            result = service.fetch_next("reviewer_a")
            self.assertEqual(result["status"], "assigned")
            self.assertEqual(result["task"]["priority"], 1)
            self.assertEqual(result["task"]["assigned_to"], "reviewer_a")
            self.assertEqual(result["task"]["status"], "in_review")

    def test_fetch_next_empty_when_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self.assertEqual(service.fetch_next("reviewer_a")["status"], "empty")

    def test_current_case_returns_assigned_in_review_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._ingest(service, NEUTRAL)
            service.drain_pipeline()
            assigned = service.fetch_next("reviewer_a")

            current = service.current_case("reviewer_a")
            self.assertEqual(current["status"], "assigned")
            self.assertEqual(current["task"]["task_id"], assigned["task"]["task_id"])
            self.assertEqual(service.current_case("reviewer_b")["status"], "empty")

    def test_independence_excludes_prior_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._ingest(service, NEUTRAL)
            service.drain_pipeline()
            first = service.fetch_next("reviewer_a")
            task_id = first["task"]["task_id"]
            content_id = first["task"]["content_id"]
            ep_id = first["task"]["evidence_package_id"]
            service.decide_task(task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_a"})

            # 模拟同一 content 的二审任务（如申诉复审）。
            self._insert_pending_task(service, content_id, ep_id)
            # 原审核员因独立性约束领不到。
            self.assertEqual(service.fetch_next("reviewer_a")["status"], "empty")
            # 其他审核员可以领取。
            self.assertEqual(service.fetch_next("reviewer_b")["status"], "assigned")

    def test_forced_break_after_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            patched = replace(base_settings, forced_break_after=1)
            with patch.object(services_module, "settings", patched):
                self._ingest(service, NEUTRAL)
                self._ingest(service, {"title": "t2", "description": "another calm recipe", "creator_id": "c"})
                service.drain_pipeline()
                r1 = service.fetch_next("reviewer_a")
                service.decide_task(
                    r1["task"]["task_id"], {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_a"}
                )
                # 已裁定 1 单，达到强制休息阈值 -> 不再派单。
                self.assertEqual(service.fetch_next("reviewer_a")["status"], "break_required")

    def test_csam_exposure_limit_skips_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            patched = replace(base_settings, csam_per_shift_limit=1)
            with patch.object(services_module, "settings", patched):
                # 先让 reviewer 裁定一个敏感案件 -> 达到 CSAM 上限。
                self._ingest(service, NEUTRAL)
                service.drain_pipeline()
                task_id = service.list_queue()["items"][0]["task_id"]
                with service._session_factory.begin() as s:
                    s.get(HumanReviewTask, task_id).is_sensitive = True
                r = service.fetch_next("reviewer_a")
                self.assertTrue(r["task"]["is_sensitive"])
                service.decide_task(
                    r["task"]["task_id"], {"decision": "block", "reason": "sensitive", "reviewer_id": "reviewer_a"}
                )
                # 再来一个敏感 + 一个非敏感案件。
                self._ingest(service, NEUTRAL)
                self._ingest(service, {"title": "daily vlog three", "description": "ordinary update", "creator_id": "c"})
                service.drain_pipeline()
                queue = service.list_queue()["items"]
                with service._session_factory.begin() as s:
                    s.get(HumanReviewTask, queue[0]["task_id"]).is_sensitive = True
                # 超敏感曝光上限 -> 只派非敏感案件。
                nxt = service.fetch_next("reviewer_a")
                self.assertEqual(nxt["status"], "assigned")
                self.assertFalse(nxt["task"]["is_sensitive"])

    def test_release_of_decided_task_is_rejected(self):
        # 回归（high）：已裁定任务不能被 release 复活回 pending。
        from backend.app.services import ConflictError

        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._ingest(service, NEUTRAL)
            service.drain_pipeline()
            r = service.fetch_next("reviewer_a")
            task_id = r["task"]["task_id"]
            service.decide_task(task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_a"})
            with self.assertRaises(ConflictError):
                service.release_task(task_id, "reviewer_a")
            # 任务仍为 decided，未回到队列。
            self.assertEqual(service.list_queue()["total"], 0)

    def test_decision_attributed_to_actual_decider_on_expired_lock(self):
        # 回归（medium）：过期锁未清时，裁定归属实际裁定人而非旧持锁人。
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._ingest(service, NEUTRAL)
            service.drain_pipeline()
            r = service.fetch_next("reviewer_a")
            task_id = r["task"]["task_id"]
            # 令 A 的锁过期但不 sweep（assigned_to 仍为 A）。
            with service._session_factory.begin() as s:
                from datetime import datetime, timedelta, timezone

                s.get(HumanReviewTask, task_id).lock_expires_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=60)
                ).isoformat()
            service.decide_task(task_id, {"decision": "pass", "reason": "ok", "reviewer_id": "reviewer_b"})
            with service._session_factory() as s:
                self.assertEqual(s.get(HumanReviewTask, task_id).assigned_to, "reviewer_b")

    def _insert_pending_task(
        self, service, content_id, evidence_package_id, priority: int = 5, is_sensitive: bool = False
    ) -> str:
        task_id = new_id("task")
        ts = now_iso()
        with service._session_factory.begin() as s:
            s.add(
                HumanReviewTask(
                    id=task_id,
                    content_id=content_id,
                    evidence_package_id=evidence_package_id,
                    status="pending",
                    priority=priority,
                    is_sensitive=is_sensitive,
                    jurisdiction="global",
                    sla_warned=False,
                    created_at=ts,
                    updated_at=ts,
                )
            )
        return task_id


if __name__ == "__main__":
    unittest.main()
