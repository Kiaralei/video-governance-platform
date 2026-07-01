"""机审流水线的 Celery 任务。

把原来单体的 _run_pipeline_job 拆成一条独立可重试的 chain：
    extract_evidence -> run_machine_review
每个阶段方法在 GovernanceService 里是幂等的，重试不会重复产出。
任务重试耗尽后写入死信队列（dead_letter_tasks）。

worker 进程通过 get_service() 惰性构建一个 GovernanceService（从 DATABASE_URL）。
测试用 set_service() 注入指向临时 sqlite 的实例，从而在 eager 模式下验证整条 chain。
"""

from __future__ import annotations

import traceback as _traceback
from typing import Optional

from celery import chain

from .celery_app import celery_app
from .services import GovernanceService

_service: Optional[GovernanceService] = None


def get_service() -> GovernanceService:
    global _service
    if _service is None:
        _service = GovernanceService()
    return _service


def set_service(service: Optional[GovernanceService]) -> None:
    """供 worker 启动钩子 / 测试注入服务实例。"""
    global _service
    _service = service


def _retry_or_deadletter(task, name: str, job_id: str, exc: Exception) -> None:
    service = get_service()
    try:
        task.retry(exc=exc)
    except task.MaxRetriesExceededError:
        service.record_dead_letter(
            task_name=name,
            celery_task_id=task.request.id,
            job_id=job_id,
            exc=exc,
            traceback_str=_traceback.format_exc(),
            retry_count=task.request.retries,
        )
        content_id = _content_of(service, job_id)
        service._mark_pipeline_failed(job_id, content_id, exc)
        raise


def _content_of(service: GovernanceService, job_id: str) -> str:
    from sqlalchemy import select

    from .models import PipelineJob

    with service._session_factory() as session:
        job = session.get(PipelineJob, job_id)
        return job.content_id if job is not None else ""


@celery_app.task(bind=True, name="pipeline.extract_evidence", max_retries=3, default_retry_delay=30)
def extract_evidence(self, job_id: str) -> str:
    try:
        service = get_service()
        service.claim_pipeline_job(job_id)
        service.extract_evidence_stage(job_id)
    except Exception as exc:  # noqa: BLE001 - 边界统一走重试/死信
        _retry_or_deadletter(self, "pipeline.extract_evidence", job_id, exc)
    return job_id


@celery_app.task(bind=True, name="pipeline.run_machine_review", max_retries=2, default_retry_delay=15)
def run_machine_review(self, job_id: str) -> str:
    try:
        get_service().run_machine_review_stage(job_id)
    except Exception as exc:  # noqa: BLE001 - 边界统一走重试/死信
        _retry_or_deadletter(self, "pipeline.run_machine_review", job_id, exc)
    return job_id


@celery_app.task(bind=True, name="pipeline.on_failure")
def on_pipeline_failure(self, request, exc, traceback, job_id: str | None = None) -> None:
    """chain 的 link_error 兜底回调：把永久失败写入死信队列。"""
    get_service().record_dead_letter(
        task_name=getattr(request, "task", "pipeline"),
        celery_task_id=getattr(request, "id", None),
        job_id=job_id,
        exc=exc if isinstance(exc, Exception) else RuntimeError(str(exc)),
        traceback_str=str(traceback),
        retry_count=getattr(request, "retries", 0),
    )


def dispatch_pipeline(job_id: str):
    """派发一条机审流水线 chain。broker 配置存在时异步执行，否则 eager 同步执行。"""
    workflow = chain(extract_evidence.s(job_id), run_machine_review.s())
    return workflow.apply_async(link_error=on_pipeline_failure.s(job_id=job_id))
