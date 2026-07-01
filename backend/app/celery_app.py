"""Celery 应用。

配置了 broker（Redis）时正常异步分发；未配置时 task_always_eager=True，
任务在进程内同步执行 —— 让本地/测试无需 Redis 也能跑通 chain 逻辑。
"""

from __future__ import annotations

from celery import Celery

from .config import settings


def make_celery() -> Celery:
    broker = settings.celery_broker_url or None
    backend = settings.celery_result_backend or None
    app = Celery("vgp", broker=broker, backend=backend)
    app.conf.update(
        task_always_eager=not bool(settings.celery_broker_url),
        task_eager_propagates=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_default_queue="pipeline",
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = make_celery()
