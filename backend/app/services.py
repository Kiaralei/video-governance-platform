from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .database import create_db_engine, init_db, is_postgres_enabled, make_session_factory
from .evidence import EvidenceExtractor
from .llm_review import is_llm_configured, review_with_configured_llm
from .models import (
    AuditLog,
    ContentItem,
    DeadLetterTask,
    EvidencePackage,
    HumanReviewTask,
    MachineReview,
    MediaAsset,
    PipelineJob,
)


PASS = "pass"
BLOCK = "block"
PENDING = "pending"
DECIDED = "decided"
JOB_QUEUED = "queued"
JOB_PROCESSING = "processing"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def loads(data: str) -> Any:
    return json.loads(data)


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


class GovernanceService:
    """Single-tenant, global-jurisdiction MVP workflow service."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        self.engine = create_db_engine(db_path)
        init_db(self.engine)
        self._session_factory = make_session_factory(self.engine)

    def reset(self) -> dict[str, Any]:
        # 按外键依赖倒序删除，避免约束冲突。
        with self._session_factory.begin() as session:
            for model in (
                DeadLetterTask,
                AuditLog,
                HumanReviewTask,
                MachineReview,
                EvidencePackage,
                MediaAsset,
                PipelineJob,
                ContentItem,
            ):
                session.execute(delete(model))
        return {"status": "reset"}

    def seed(self) -> dict[str, Any]:
        examples = [
            {
                "title": "低风险做饭教程",
                "description": "创作者展示家常菜做法，并提到一家家庭餐厅。",
                "creator_id": "creator_alina",
                "poi": "global",
                "video_url": "https://example.local/videos/cooking-demo.mp4",
            },
            {
                "title": "高风险博彩引流",
                "description": "视频文字引导用户扫码领取 betting bonus。",
                "creator_id": "creator_bento",
                "poi": "global",
                "video_url": "https://example.local/videos/betting-promo.mp4",
            },
        ]
        created = [self.ingest_content(item) for item in examples]
        return {"items": created}

    def ingest_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        creator_id = str(payload.get("creator_id", "anonymous")).strip() or "anonymous"
        if not title:
            raise ValidationError("标题不能为空")
        if not description:
            raise ValidationError("描述不能为空")

        content_id = new_id("cnt")
        job_id = new_id("job")
        timestamp = now_iso()

        with self._session_factory.begin() as session:
            backlog = session.execute(
                select(func.count())
                .select_from(PipelineJob)
                .where(PipelineJob.status.in_([JOB_QUEUED, JOB_PROCESSING]))
            ).scalar_one()
            if backlog >= settings.max_pipeline_backlog:
                raise ConflictError("机审队列已满，请稍后重试")

            session.add(
                ContentItem(
                    id=content_id,
                    tenant_id=settings.tenant_id,
                    jurisdiction=settings.jurisdiction,
                    title=title,
                    description=description,
                    creator_id=creator_id,
                    poi=payload.get("poi", "global"),
                    video_url=payload.get("video_url", ""),
                    status="machine_queued",
                    final_decision=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.add(
                PipelineJob(
                    id=job_id,
                    content_id=content_id,
                    status=JOB_QUEUED,
                    stage="queued",
                    attempts=0,
                    max_attempts=3,
                    error=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                    started_at=None,
                    finished_at=None,
                )
            )
            self._append_audit(
                session,
                content_id=content_id,
                task_id=None,
                actor="system",
                action="content_queued",
                detail={
                    "job_id": job_id,
                    "routing": "machine_pipeline",
                    "csam_enabled": False,
                    "critical_detection_enabled": False,
                },
            )

        self._dispatch_pipeline(job_id)
        return self.get_pipeline_job(job_id)

    def _dispatch_pipeline(self, job_id: str) -> None:
        """配置了 Celery broker 时派发异步 chain；否则不派发，交给 drain / 线程 worker。

        测试与本地无 broker 环境下保持“先入队、后 drain”的语义不变。
        """
        if not settings.celery_broker_url:
            return
        from .tasks import dispatch_pipeline  # 延迟导入，避免与 tasks 循环依赖

        dispatch_pipeline(job_id)

    def ingest_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValidationError("批量摄取请求必须包含 items 数组")
        if not items:
            raise ValidationError("items 不能为空")
        if len(items) > settings.max_batch_ingest_items:
            raise ValidationError(f"单次批量摄取最多允许 {settings.max_batch_ingest_items} 条")

        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({"index": index, "error": "条目必须是 JSON 对象"})
                continue
            try:
                created.append(self.ingest_content(item))
            except (ValidationError, ConflictError) as exc:
                errors.append({"index": index, "error": str(exc)})

        return {
            "accepted": len(created),
            "failed": len(errors),
            "total": len(items),
            "items": created,
            "errors": errors,
        }

    def get_pipeline_job(self, job_id: str) -> dict[str, Any]:
        sql = text(
            """
            SELECT j.*, c.title, c.description, c.creator_id, c.status AS content_status,
                   c.final_decision,
                   e.id AS evidence_package_id,
                   m.id AS machine_review_id, m.recommendation, m.confidence, m.rationale,
                   t.id AS task_id, t.status AS task_status
            FROM pipeline_jobs j
            JOIN content_items c ON c.id = j.content_id
            LEFT JOIN evidence_packages e ON e.content_id = c.id
            LEFT JOIN machine_reviews m ON m.content_id = c.id
            LEFT JOIN human_review_tasks t ON t.content_id = c.id
            WHERE j.id = :job_id
            """
        )
        with self._session_factory() as session:
            row = session.execute(sql, {"job_id": job_id}).mappings().first()
        if row is None:
            raise NotFoundError("流水线任务不存在")
        return self._pipeline_job_summary(dict(row))

    def list_pipeline_jobs(self, offset: int = 0, limit: int = 50, status: str | None = None) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        where = ""
        params: dict[str, Any] = {}
        if status:
            where = "WHERE j.status = :status"
            params["status"] = status
        with self._session_factory() as session:
            total = session.execute(
                text(f"SELECT COUNT(*) AS c FROM pipeline_jobs j {where}"),
                params,
            ).scalar_one()
            rows = session.execute(
                text(
                    f"""
                    SELECT j.*, c.title, c.description, c.creator_id, c.status AS content_status,
                           c.final_decision,
                           e.id AS evidence_package_id,
                           m.id AS machine_review_id, m.recommendation, m.confidence, m.rationale,
                           t.id AS task_id, t.status AS task_status
                    FROM pipeline_jobs j
                    JOIN content_items c ON c.id = j.content_id
                    LEFT JOIN evidence_packages e ON e.content_id = c.id
                    LEFT JOIN machine_reviews m ON m.content_id = c.id
                    LEFT JOIN human_review_tasks t ON t.content_id = c.id
                    {where}
                    ORDER BY j.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**params, "limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._pipeline_job_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def process_next_pipeline_job(self) -> bool:
        # PostgreSQL 下用 FOR UPDATE SKIP LOCKED 让多 worker 并发领取不打架；SQLite 无此语义。
        lock_clause = " FOR UPDATE SKIP LOCKED" if is_postgres_enabled() else ""
        with self._session_factory.begin() as session:
            row = session.execute(
                text(
                    f"""
                    SELECT j.*, c.title, c.description, c.creator_id, c.poi, c.video_url
                    FROM pipeline_jobs j
                    JOIN content_items c ON c.id = j.content_id
                    WHERE j.status = :status AND j.attempts < j.max_attempts
                    ORDER BY j.created_at ASC
                    LIMIT 1
                    {lock_clause}
                    """
                ),
                {"status": JOB_QUEUED},
            ).mappings().first()
            if row is None:
                return False
            job = dict(row)
            timestamp = now_iso()

            pipeline_job = session.get(PipelineJob, job["id"])
            pipeline_job.status = JOB_PROCESSING
            pipeline_job.stage = "evidence_extraction"
            pipeline_job.attempts = pipeline_job.attempts + 1
            pipeline_job.started_at = pipeline_job.started_at or timestamp
            pipeline_job.updated_at = timestamp
            pipeline_job.error = None

            content = session.get(ContentItem, job["content_id"])
            content.status = "machine_processing"
            content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=job["content_id"],
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_started",
                detail={"job_id": job["id"]},
            )

        try:
            self._run_pipeline_job(job)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self._mark_pipeline_failed(job["id"], job["content_id"], exc)
        return True

    def drain_pipeline(self, limit: int | None = None) -> int:
        processed = 0
        while limit is None or processed < limit:
            if not self.process_next_pipeline_job():
                break
            processed += 1
        return processed

    def _run_pipeline_job(self, job: dict[str, Any]) -> None:
        """线程/drain 路径：调用方已领取任务，这里顺序执行两个阶段。

        阶段方法是幂等的，与 Celery chain 复用同一套逻辑（见 app/tasks.py）。
        """
        self.extract_evidence_stage(job["id"])
        self.run_machine_review_stage(job["id"])

    def claim_pipeline_job(self, job_id: str) -> None:
        """把指定 job 从 queued 领取为 processing（幂等：非 queued 直接跳过）。

        线程路径在 process_next_pipeline_job 里用 SKIP LOCKED 原子领取；Celery 路径
        每个 job 只派发一次，这里按 id 领取即可。
        """
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            if job.status != JOB_QUEUED:
                return
            job.status = JOB_PROCESSING
            job.stage = "evidence_extraction"
            job.attempts = job.attempts + 1
            job.started_at = job.started_at or timestamp
            job.updated_at = timestamp
            job.error = None
            content = session.get(ContentItem, job.content_id)
            content.status = "machine_processing"
            content.updated_at = timestamp
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_started",
                detail={"job_id": job_id},
            )

    def extract_evidence_stage(self, job_id: str) -> None:
        """阶段1：抽证据。幂等 —— 证据包已存在则直接返回，重试不会重复生成。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            content = session.get(ContentItem, job.content_id)
            existing = session.execute(
                select(EvidencePackage.id).where(EvidencePackage.content_id == job.content_id)
            ).scalar()
            if existing is not None:
                return
            evidence_id = new_id("ep")
            text_blob = f"{content.title} {content.description}".lower()
            evidence = self._build_evidence_package(
                evidence_id=evidence_id,
                content_id=job.content_id,
                title=content.title,
                description=content.description,
                creator_id=content.creator_id,
                poi=str(content.poi or "global"),
                video_url=str(content.video_url or ""),
                text=text_blob,
            )
            job.stage = "machine_review"
            job.updated_at = timestamp
            session.add(
                EvidencePackage(
                    id=evidence_id,
                    content_id=job.content_id,
                    package_json=dumps(evidence),
                    created_at=timestamp,
                )
            )
            self._persist_media_asset(session, evidence["media_asset"], timestamp)
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="evidence_extracted",
                detail={
                    "job_id": job_id,
                    "evidence_package_id": evidence_id,
                    "media_asset_id": evidence["media_asset"]["asset_id"],
                    "media_asset_status": evidence["media_asset"]["status"],
                },
            )

    def run_machine_review_stage(self, job_id: str) -> None:
        """阶段2：机审 + 入人审队列。幂等 —— 机审记录已存在则直接返回。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            content = session.get(ContentItem, job.content_id)
            existing_review = session.execute(
                select(MachineReview.id).where(MachineReview.content_id == job.content_id)
            ).scalar()
            if existing_review is not None:
                return
            evidence_row = session.execute(
                select(EvidencePackage).where(EvidencePackage.content_id == job.content_id)
            ).scalar_one()
            evidence = loads(evidence_row.package_json)
            text_blob = f"{content.title} {content.description}".lower()
            machine_review_id = new_id("mr")
            task_id = new_id("task")
            machine = self._run_machine_review(machine_review_id, job.content_id, evidence, text_blob)
            # _run_machine_review 会往 evidence 里补 llm_verdicts / machine_review_source，回写证据包。
            evidence_row.package_json = dumps(evidence)

            session.add(
                MachineReview(
                    id=machine["id"],
                    content_id=job.content_id,
                    recommendation=machine["recommendation"],
                    confidence=machine["confidence"],
                    rationale=machine["rationale"],
                    verdicts_json=dumps(machine["verdicts"]),
                    created_at=timestamp,
                )
            )
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="machine_review_completed",
                detail={
                    "job_id": job_id,
                    "machine_review_id": machine["id"],
                    "recommendation": machine["recommendation"],
                },
            )

            session.add(
                HumanReviewTask(
                    id=task_id,
                    content_id=job.content_id,
                    evidence_package_id=evidence_row.id,
                    status=PENDING,
                    assigned_to=None,
                    decision=None,
                    reason=None,
                    decided_at=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            job.status = JOB_COMPLETED
            job.stage = "human_review_queued"
            job.updated_at = timestamp
            job.finished_at = timestamp
            content.status = "human_review"
            content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=task_id,
                actor="pipeline_worker",
                action="human_review_task_created",
                detail={"job_id": job_id, "task_id": task_id},
            )

    def _mark_pipeline_failed(self, job_id: str, content_id: str, exc: Exception) -> None:
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            pipeline_job = session.get(PipelineJob, job_id)
            if pipeline_job is not None:
                pipeline_job.status = JOB_FAILED
                pipeline_job.stage = "failed"
                pipeline_job.error = str(exc)
                pipeline_job.updated_at = timestamp
                pipeline_job.finished_at = timestamp

            content = session.get(ContentItem, content_id)
            if content is not None:
                content.status = "machine_failed"
                content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=content_id,
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_failed",
                detail={"job_id": job_id, "error": str(exc)},
            )

            # 线程路径失败即终态（不重试），记入死信队列供运维排查/重放。
            session.add(
                DeadLetterTask(
                    task_name="pipeline",
                    celery_task_id=None,
                    job_id=job_id,
                    content_id=content_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback="",
                    retry_count=pipeline_job.attempts if pipeline_job is not None else 0,
                    status="pending",
                    created_at=timestamp,
                )
            )

    def list_queue(self, offset: int = 0, limit: int = 20, status: str = PENDING) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(
                select(func.count())
                .select_from(HumanReviewTask)
                .where(HumanReviewTask.status == status)
            ).scalar_one()
            rows = session.execute(
                text(
                    """
                    SELECT t.*, c.title, c.description, c.creator_id, c.poi, c.video_url,
                           m.recommendation, m.confidence, m.rationale
                    FROM human_review_tasks t
                    JOIN content_items c ON c.id = t.content_id
                    JOIN machine_reviews m ON m.content_id = c.id
                    WHERE t.status = :status
                    ORDER BY t.created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"status": status, "limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._task_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def list_machine_reviews(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(select(func.count()).select_from(MachineReview)).scalar_one()
            rows = session.execute(
                text(
                    """
                    SELECT m.*, c.title, c.description, c.creator_id, c.status, c.final_decision,
                           e.id AS evidence_package_id, t.id AS task_id, t.status AS task_status
                    FROM machine_reviews m
                    JOIN content_items c ON c.id = m.content_id
                    JOIN evidence_packages e ON e.content_id = c.id
                    JOIN human_review_tasks t ON t.content_id = c.id
                    ORDER BY m.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._machine_review_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def get_machine_review(self, content_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT m.*, c.title, c.description, c.creator_id, c.status, c.final_decision,
                           e.id AS evidence_package_id, e.package_json,
                           t.id AS task_id, t.status AS task_status
                    FROM machine_reviews m
                    JOIN content_items c ON c.id = m.content_id
                    JOIN evidence_packages e ON e.content_id = c.id
                    JOIN human_review_tasks t ON t.content_id = c.id
                    WHERE m.content_id = :content_id
                    """
                ),
                {"content_id": content_id},
            ).mappings().first()
        if row is None:
            raise NotFoundError("机审记录不存在")
        data = dict(row)
        summary = self._machine_review_summary(data)
        return {**summary, "evidence": loads(data["package_json"])}

    def get_case(self, task_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT t.*, c.title, c.description, c.creator_id, c.poi, c.video_url,
                           c.tenant_id, c.jurisdiction, c.final_decision,
                           e.package_json,
                           m.recommendation, m.confidence, m.rationale, m.verdicts_json
                    FROM human_review_tasks t
                    JOIN content_items c ON c.id = t.content_id
                    JOIN evidence_packages e ON e.id = t.evidence_package_id
                    JOIN machine_reviews m ON m.content_id = c.id
                    WHERE t.id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).mappings().first()
        if row is None:
            raise NotFoundError("任务不存在")
        data = dict(row)
        return {
            "task": self._task_summary(data),
            "content": {
                "id": data["content_id"],
                "title": data["title"],
                "description": data["description"],
                "creator_id": data["creator_id"],
                "poi": data["poi"],
                "video_url": data["video_url"],
                "tenant_id": data["tenant_id"],
                "jurisdiction": data["jurisdiction"],
                "final_decision": data["final_decision"],
            },
            "evidence": loads(data["package_json"]),
            "machine_review": {
                "recommendation": data["recommendation"],
                "confidence": data["confidence"],
                "rationale": data["rationale"],
                "verdicts": loads(data["verdicts_json"]),
            },
        }

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            package = session.get(EvidencePackage, evidence_id)
        if package is None:
            raise NotFoundError("证据包不存在")
        return loads(package.package_json)

    def claim_task(self, task_id: str, reviewer_id: str) -> dict[str, Any]:
        reviewer_id = reviewer_id.strip() or "reviewer_demo"
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status != PENDING:
                raise ConflictError("只有待审任务可以领取")
            task.assigned_to = reviewer_id
            task.updated_at = timestamp
            self._append_audit(
                session,
                content_id=task.content_id,
                task_id=task_id,
                actor=reviewer_id,
                action="task_claimed",
                detail={"reviewer_id": reviewer_id},
            )
        return self.get_case(task_id)

    def decide_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        decision = str(payload.get("decision", "")).lower()
        if decision not in {PASS, BLOCK}:
            raise ValidationError("裁定只能是 pass 或 block")
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise ValidationError("裁定理由不能为空")
        reviewer_id = str(payload.get("reviewer_id", "reviewer_demo")).strip() or "reviewer_demo"
        timestamp = now_iso()

        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("任务已经完成裁定")

            task.status = DECIDED
            task.assigned_to = task.assigned_to or reviewer_id
            task.decision = decision
            task.reason = reason
            task.decided_at = timestamp
            task.updated_at = timestamp

            content = session.get(ContentItem, task.content_id)
            content.status = f"final_{decision}"
            content.final_decision = decision
            content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=task.content_id,
                task_id=task_id,
                actor=reviewer_id,
                action="human_decision_submitted",
                detail={"decision": decision, "reason": reason},
            )
        return {"task_id": task_id, "status": DECIDED, "decision": decision}

    def record_dead_letter(
        self,
        task_name: str,
        celery_task_id: str | None,
        job_id: str | None,
        exc: Exception,
        traceback_str: str = "",
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """记录一条死信（Celery 任务重试耗尽后调用）。"""
        timestamp = now_iso()
        content_id: str | None = None
        with self._session_factory.begin() as session:
            if job_id:
                job = session.get(PipelineJob, job_id)
                content_id = job.content_id if job is not None else None
            session.add(
                DeadLetterTask(
                    task_name=task_name,
                    celery_task_id=celery_task_id,
                    job_id=job_id,
                    content_id=content_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback=traceback_str,
                    retry_count=retry_count,
                    status="pending",
                    created_at=timestamp,
                )
            )
        return {"status": "recorded"}

    def list_dead_letters(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(select(func.count()).select_from(DeadLetterTask)).scalar_one()
            rows = session.execute(
                select(DeadLetterTask).order_by(DeadLetterTask.id.desc()).limit(limit).offset(offset)
            ).scalars().all()
        items = [self._dead_letter_summary(row) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def _dead_letter_summary(self, row: DeadLetterTask) -> dict[str, Any]:
        return {
            "id": row.id,
            "task_name": row.task_name,
            "celery_task_id": row.celery_task_id,
            "job_id": row.job_id,
            "content_id": row.content_id,
            "exception_type": row.exception_type,
            "exception_message": row.exception_message,
            "retry_count": row.retry_count,
            "status": row.status,
            "created_at": row.created_at,
        }

    def get_audit(self, content_id: str | None = None) -> dict[str, Any]:
        with self._session_factory() as session:
            stmt = select(AuditLog).order_by(AuditLog.id.asc())
            if content_id:
                stmt = stmt.where(AuditLog.content_id == content_id)
            else:
                stmt = stmt.limit(100)
            rows = session.execute(stmt).scalars().all()
        return {"items": [self._audit_row(self._audit_orm_to_row(row)) for row in rows]}

    def summary(self) -> dict[str, Any]:
        with self._session_factory() as session:
            counts = {
                status: count
                for status, count in session.execute(
                    select(HumanReviewTask.status, func.count()).group_by(HumanReviewTask.status)
                ).all()
            }
            decisions = {
                (final_decision or "none"): count
                for final_decision, count in session.execute(
                    select(ContentItem.final_decision, func.count()).group_by(ContentItem.final_decision)
                ).all()
            }
            total = session.execute(select(func.count()).select_from(ContentItem)).scalar_one()
            pipeline = {
                status: count
                for status, count in session.execute(
                    select(PipelineJob.status, func.count()).group_by(PipelineJob.status)
                ).all()
            }
        return {
            "tenant_id": settings.tenant_id,
            "jurisdiction": settings.jurisdiction,
            "total_content": total,
            "queue": {"pending": counts.get(PENDING, 0), "decided": counts.get(DECIDED, 0)},
            "pipeline": {
                "queued": pipeline.get(JOB_QUEUED, 0),
                "processing": pipeline.get(JOB_PROCESSING, 0),
                "completed": pipeline.get(JOB_COMPLETED, 0),
                "failed": pipeline.get(JOB_FAILED, 0),
            },
            "decisions": {"pass": decisions.get(PASS, 0), "block": decisions.get(BLOCK, 0)},
            "feature_flags": feature_flags(),
        }

    def _build_evidence_package(
        self,
        evidence_id: str,
        content_id: str,
        title: str,
        description: str,
        creator_id: str,
        poi: str,
        video_url: str,
        text: str,
    ) -> dict[str, Any]:
        risky_terms = ["gambling", "bet", "bonus", "qr", "scan", "violence", "weapon", "hate"]
        matched = [term for term in risky_terms if term in text]
        extracted = EvidenceExtractor().extract(
            video_url=video_url,
            content_id=content_id,
            title=title,
            description=description,
        )
        return {
            "ep_id": evidence_id,
            "schema_version": "mvp-1.0",
            "content_id": content_id,
            "tenant_id": settings.tenant_id,
            "jurisdiction": settings.jurisdiction,
            "media_asset": extracted["media_asset"],
            "video_meta": extracted["video_meta"],
            "frames": extracted["frames"] or [
                {"frame_id": "frame_001", "timestamp_ms": 0, "thumbnail": "", "caption": title},
                {"frame_id": "frame_002", "timestamp_ms": 45000, "thumbnail": "", "caption": description[:80]},
            ],
            "asr_transcript": extracted["asr_transcript"],
            "ocr_results": extracted["ocr_results"],
            "object_detections": extracted["object_detections"],
            "scene_tags": extracted["scene_tags"],
            "metadata": {"title": title, "description": description, "creator_id": creator_id, "poi": poi},
            "pre_filter_results": {
                "rule_hits": [{"rule_id": f"keyword:{term}", "term": term} for term in matched],
                "cloud_api_hits": [],
                "dedup_reuse": None,
                "skip_llm_review": False,
                "skip_reason": None,
            },
            "llm_verdicts": [],
            "modality_model_invocations": extracted["modality_model_invocations"],
            "modality_availability": extracted["modality_availability"],
            "extraction_notes": extracted["extraction_notes"],
            "truncated_modalities": [],
            "access_policy": {"readable_roles": ["reviewer", "admin"], "retention_days": 90},
            "token_budget_used": len(text.split()),
            "token_budget_limit": 8000,
        }

    def _run_machine_review(
        self,
        review_id: str,
        content_id: str,
        evidence: dict[str, Any],
        text: str,
    ) -> dict[str, Any]:
        llm_result = review_with_configured_llm(evidence)
        if llm_result is not None:
            dimension_decision = llm_result["decision"]
            if dimension_decision == "VIOLATION":
                recommendation = BLOCK
            elif dimension_decision == "NO_VIOLATION":
                recommendation = PASS
            else:
                recommendation = None
            verdicts = [
                {
                    "dimension_id": "mvp_general_policy",
                    "decision": dimension_decision,
                    "confidence": llm_result["confidence"],
                    "evidence_refs": llm_result["evidence_refs"],
                    "source": "llm",
                    "model": llm_result["model"],
                }
            ]
            evidence["llm_verdicts"] = verdicts
            evidence["machine_review_source"] = "llm"
            return {
                "id": review_id,
                "content_id": content_id,
                "recommendation": recommendation,
                "confidence": llm_result["confidence"],
                "rationale": llm_result["reason"],
                "verdicts": verdicts,
            }

        block_terms = {"gambling", "bet", "bonus", "weapon", "hate"}
        pass_terms = {"cooking", "recipe", "education", "travel", "music"}
        block_score = sum(1 for term in block_terms if term in text)
        pass_score = sum(1 for term in pass_terms if term in text)
        if block_score > pass_score:
            recommendation = BLOCK
            confidence = min(0.55 + block_score * 0.12, 0.92)
            rationale = "关键词和元数据证据显示内容可能存在策略风险。"
            dimension_decision = "VIOLATION"
        elif pass_score > 0 and block_score == 0:
            recommendation = PASS
            confidence = min(0.62 + pass_score * 0.08, 0.86)
            rationale = "证据整体风险较低，但最终裁定仍由人审完成。"
            dimension_decision = "NO_VIOLATION"
        else:
            recommendation = None
            confidence = 0.5
            rationale = "机审没有形成强建议，需要人工判断。"
            dimension_decision = "UNCERTAIN"
        verdicts = [
            {
                "dimension_id": "mvp_general_policy",
                "decision": dimension_decision,
                "confidence": confidence,
                "evidence_refs": ["metadata.title", "asr_transcript[0].text", "ocr_results[0].text"],
                "source": "local_rules",
                "model": "keyword_rules_v1",
            }
        ]
        evidence["llm_verdicts"] = verdicts
        evidence["machine_review_source"] = "local_rules"
        return {
            "id": review_id,
            "content_id": content_id,
            "recommendation": recommendation,
            "confidence": confidence,
            "rationale": rationale,
            "verdicts": verdicts,
        }

    def _append_audit(
        self,
        session: Session,
        content_id: str | None,
        task_id: str | None,
        actor: str,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        # autoflush 会在这条 SELECT 前把同一事务里已 add 的前序审计行刷入，
        # 因此拿到的始终是最新一条 —— 哈希链在事务内也能正确串联。
        prev_hash = session.execute(
            select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
        ).scalar()
        prev_hash = prev_hash if prev_hash else "GENESIS"
        timestamp = now_iso()
        payload = dumps(
            {
                "content_id": content_id,
                "task_id": task_id,
                "actor": actor,
                "action": action,
                "detail": detail,
                "prev_hash": prev_hash,
                "created_at": timestamp,
            }
        )
        entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        session.add(
            AuditLog(
                content_id=content_id,
                task_id=task_id,
                actor=actor,
                action=action,
                detail_json=dumps(detail),
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=timestamp,
            )
        )

    def _persist_media_asset(self, session: Session, asset: dict[str, Any], timestamp: str) -> None:
        session.add(
            MediaAsset(
                id=asset["asset_id"],
                content_id=asset["content_id"],
                source=asset.get("source"),
                source_type=asset["source_type"],
                status=asset["status"],
                storage_backend=asset["storage_backend"],
                storage_uri=asset.get("storage_uri"),
                local_path=asset.get("local_path"),
                sha256=asset.get("sha256"),
                file_size_bytes=asset.get("file_size_bytes"),
                mime_type=asset.get("mime_type"),
                extension=asset.get("extension"),
                error=asset.get("error"),
                asset_json=dumps(asset),
                created_at=timestamp,
            )
        )

    def _task_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": row["id"],
            "content_id": row["content_id"],
            "evidence_package_id": row["evidence_package_id"],
            "status": row["status"],
            "assigned_to": row["assigned_to"],
            "decision": row["decision"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "title": row.get("title"),
            "creator_id": row.get("creator_id"),
            "machine_recommendation": row.get("recommendation"),
            "machine_confidence": row.get("confidence"),
            "machine_rationale": row.get("rationale"),
        }

    def _machine_review_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "review_id": row["id"],
            "content_id": row["content_id"],
            "task_id": row["task_id"],
            "evidence_package_id": row["evidence_package_id"],
            "title": row["title"],
            "description": row["description"],
            "creator_id": row["creator_id"],
            "content_status": row["status"],
            "task_status": row["task_status"],
            "final_decision": row["final_decision"],
            "recommendation": row["recommendation"],
            "confidence": row["confidence"],
            "rationale": row["rationale"],
            "verdicts": loads(row["verdicts_json"]),
            "created_at": row["created_at"],
        }

    def _pipeline_job_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": row["id"],
            "content_id": row["content_id"],
            "title": row["title"],
            "description": row["description"],
            "creator_id": row["creator_id"],
            "content_status": row["content_status"],
            "status": row["status"],
            "stage": row["stage"],
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "evidence_package_id": row.get("evidence_package_id"),
            "machine_review_id": row.get("machine_review_id"),
            "recommendation": row.get("recommendation"),
            "confidence": row.get("confidence"),
            "rationale": row.get("rationale"),
            "task_id": row.get("task_id"),
            "task_status": row.get("task_status"),
            "final_decision": row.get("final_decision"),
        }

    def _audit_orm_to_row(self, row: AuditLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "content_id": row.content_id,
            "task_id": row.task_id,
            "actor": row.actor,
            "action": row.action,
            "detail_json": row.detail_json,
            "prev_hash": row.prev_hash,
            "entry_hash": row.entry_hash,
            "created_at": row.created_at,
        }

    def _audit_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["detail"] = loads(row.pop("detail_json"))
        return row


def feature_flags() -> dict[str, bool]:
    return {
        "enable_csam_detection": False,
        "enable_critical_detection": False,
        "enable_full_disposition_matrix": False,
        "enable_need_more_context": False,
        "single_tenant": True,
        "global_jurisdiction": True,
    }


def config_payload() -> dict[str, Any]:
    return {
        "tenant_id": settings.tenant_id,
        "jurisdiction": settings.jurisdiction,
        "database_backend": "postgresql" if is_postgres_enabled() else "sqlite",
        "machine_review": {
            "llm_configured": is_llm_configured(),
            "fallback": "local_rules",
        },
        "media_ingestion": {
            "storage_backend": "local_fs",
            "max_media_bytes": settings.max_media_bytes,
            "copy_local_media": settings.copy_local_media,
            "remote_download_enabled": settings.enable_remote_download,
            "max_batch_ingest_items": settings.max_batch_ingest_items,
        },
        "modality_models": {
            "asr_configured": bool(settings.asr_model_url),
            "ocr_configured": bool(settings.ocr_model_url),
            "vision_configured": bool(settings.vision_model_url),
            "timeout_seconds": settings.model_timeout_seconds,
        },
        "allowed_human_decisions": [PASS, BLOCK],
        "feature_flags": feature_flags(),
    }
