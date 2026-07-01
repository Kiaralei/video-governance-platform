"""FastAPI 应用层。

替代 server.py 手写的 http.server 路由。这一层只做“把请求接进来、把响应发出去”，
所有业务逻辑仍然委托给 GovernanceService（绞杀者迁移：先换框架，不动内核）。

路由按设计文档 2.2 的领域模块边界拆成多个 APIRouter，仅用于分组与 /docs 标签，
后续 SQLAlchemy 阶段可平滑拆成 ingestion/ evidence/ ... 独立 package。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .schemas import (
    BatchIngestRequest,
    ClaimRequest,
    ContentUploadRequest,
    DecideRequest,
    DrainRequest,
)
from .services import (
    ConflictError,
    GovernanceService,
    NotFoundError,
    ValidationError,
    config_payload,
)
from .worker import PipelineWorker


def _service(request: Request) -> GovernanceService:
    return request.app.state.service


# --- 领域模块路由（对齐设计 2.2 的边界） --------------------------------------

system_router = APIRouter(prefix="/api/v1", tags=["system"])
ingestion_router = APIRouter(prefix="/api/v1", tags=["ingestion"])
machine_router = APIRouter(prefix="/api/v1", tags=["machine"])
evidence_router = APIRouter(prefix="/api/v1", tags=["evidence"])
human_router = APIRouter(prefix="/api/v1/review/human", tags=["human_review"])
dev_router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


# --- system ------------------------------------------------------------------

@system_router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": settings.app_name}


@system_router.get("/config")
def config() -> dict[str, Any]:
    return config_payload()


@system_router.get("/dashboard/summary")
def dashboard_summary(request: Request) -> dict[str, Any]:
    return _service(request).summary()


@system_router.get("/audit")
def audit(request: Request, content_id: Optional[str] = None) -> dict[str, Any]:
    return _service(request).get_audit(content_id=content_id)


@system_router.get("/system/dead-letters")
def dead_letters(request: Request, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    return _service(request).list_dead_letters(offset=offset, limit=limit)


# --- ingestion / pipeline ----------------------------------------------------

@ingestion_router.post("/content/upload")
def upload_content(request: Request, payload: ContentUploadRequest) -> dict[str, Any]:
    return _service(request).ingest_content(payload.model_dump())


@ingestion_router.post("/content/batch")
def batch_content(request: Request, payload: BatchIngestRequest) -> dict[str, Any]:
    return _service(request).ingest_batch(payload.model_dump())


@ingestion_router.get("/pipeline/jobs")
def pipeline_jobs(
    request: Request, offset: int = 0, limit: int = 50, status: Optional[str] = None
) -> dict[str, Any]:
    return _service(request).list_pipeline_jobs(offset=offset, limit=limit, status=status)


@ingestion_router.post("/pipeline/drain")
def pipeline_drain(request: Request, payload: Optional[DrainRequest] = None) -> dict[str, Any]:
    limit = payload.limit if payload else None
    return {"processed": _service(request).drain_pipeline(limit=limit)}


# --- machine review ----------------------------------------------------------

@machine_router.get("/machine/reviews")
def machine_reviews(request: Request, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    return _service(request).list_machine_reviews(offset=offset, limit=limit)


@machine_router.get("/machine/reviews/{content_id}")
def machine_review_detail(request: Request, content_id: str) -> dict[str, Any]:
    return _service(request).get_machine_review(content_id)


# --- evidence ----------------------------------------------------------------

@evidence_router.get("/evidence/{evidence_id}")
def evidence(request: Request, evidence_id: str) -> dict[str, Any]:
    return _service(request).get_evidence(evidence_id)


# --- human review (注意：静态路径 /queue 必须声明在 /{task_id} 之前) ----------

@human_router.get("/queue")
def review_queue(
    request: Request, offset: int = 0, limit: int = 20, status: str = "pending"
) -> dict[str, Any]:
    return _service(request).list_queue(offset=offset, limit=limit, status=status)


@human_router.get("/{task_id}")
def review_case(request: Request, task_id: str) -> dict[str, Any]:
    return _service(request).get_case(task_id)


@human_router.post("/{task_id}/claim")
def claim_task(request: Request, task_id: str, payload: Optional[ClaimRequest] = None) -> dict[str, Any]:
    reviewer_id = payload.reviewer_id if payload else "reviewer_demo"
    return _service(request).claim_task(task_id, reviewer_id)


@human_router.post("/{task_id}/decide")
def decide_task(request: Request, task_id: str, payload: DecideRequest) -> dict[str, Any]:
    return _service(request).decide_task(task_id, payload.model_dump())


# --- dev ---------------------------------------------------------------------

@dev_router.post("/reset")
def dev_reset(request: Request) -> dict[str, Any]:
    return _service(request).reset()


@dev_router.post("/seed")
def dev_seed(request: Request) -> dict[str, Any]:
    return _service(request).seed()


_ROUTERS = (
    system_router,
    ingestion_router,
    machine_router,
    evidence_router,
    human_router,
    dev_router,
)


def create_app(db_path: Path | None = None) -> FastAPI:
    """构建 FastAPI 应用。db_path 仅供测试注入 sqlite；生产走 PostgreSQL。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = GovernanceService(db_path=db_path)
        worker = PipelineWorker(service)
        app.state.service = service
        app.state.worker = worker
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 把服务层的领域异常映射到与旧 server.py 一致的状态码与 JSON 结构。
    @app.exception_handler(ValidationError)
    async def _on_validation(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(NotFoundError)
    async def _on_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=404)

    @app.exception_handler(ConflictError)
    async def _on_conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=409)

    for router in _ROUTERS:
        app.include_router(router)

    # 静态前端挂在根路径，作为兜底；API 路由已先注册，优先匹配。
    frontend_dir = settings.frontend_dir
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
