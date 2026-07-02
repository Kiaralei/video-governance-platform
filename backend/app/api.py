"""FastAPI 应用层。

替代 server.py 手写的 http.server 路由。这一层只做“把请求接进来、把响应发出去”，
所有业务逻辑仍然委托给 GovernanceService（绞杀者迁移：先换框架，不动内核）。

路由按设计文档 2.2 的领域模块边界拆成多个 APIRouter，仅用于分组与 /docs 标签，
后续 SQLAlchemy 阶段可平滑拆成 ingestion/ evidence/ ... 独立 package。
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import (
    Principal,
    create_access_token,
    create_refresh_token,
    create_ws_token,
    decode_token,
    get_current_user,
    principal_from_ws_token,
    require_permission,
)
from .config import settings
from .observability import render_prometheus
from .rate_limiter import RATE_LIMITS, RateLimiter
from .realtime import hub, make_envelope
from .redis_client import get_redis
from .schemas import (
    BatchIngestRequest,
    ContentUploadRequest,
    CreateDimensionRequest,
    CreatePolicyVersionRequest,
    DecideRequest,
    DecideAppealRequest,
    DrainRequest,
    LoginRequest,
    NextTaskRequest,
    RefreshRequest,
    SubmitAppealRequest,
    TransitionRequest,
    UpdateDimensionRequest,
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


class SPAStaticFiles(StaticFiles):
    """SPA 静态托管：命中文件正常返回；未命中（前端路由 /workbench 等）回退 index.html，
    交给 BrowserRouter 处理，保证深链/刷新不 404。"""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def rate_limit(name: str):
    """按端点构造限流依赖。身份取 X-User 头（若有），否则取客户端 IP。"""
    rule = RATE_LIMITS[name]

    def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        identity = request.headers.get("x-user") or (
            request.client.host if request.client else "anonymous"
        )
        if not limiter.check(name, identity, rule):
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    return dependency


# --- 领域模块路由（对齐设计 2.2 的边界） --------------------------------------

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
system_router = APIRouter(prefix="/api/v1", tags=["system"])
ingestion_router = APIRouter(prefix="/api/v1", tags=["ingestion"])
machine_router = APIRouter(prefix="/api/v1", tags=["machine"])
evidence_router = APIRouter(prefix="/api/v1", tags=["evidence"])
human_router = APIRouter(prefix="/api/v1/review/human", tags=["human_review"])
reviewers_router = APIRouter(prefix="/api/v1/reviewers", tags=["reviewers"])
appeal_router = APIRouter(prefix="/api/v1/appeal", tags=["appeal"])
quality_router = APIRouter(prefix="/api/v1/quality", tags=["quality"])
policy_router = APIRouter(prefix="/api/v1/policy", tags=["policy"])
dev_router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


# --- auth --------------------------------------------------------------------

@auth_router.post("/login", dependencies=[Depends(rate_limit("auth.login"))])
def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
    principal = _service(request).authenticate(payload.username, payload.password)
    if principal is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {
        "access_token": create_access_token(principal["user_id"], principal["roles"]),
        "refresh_token": create_refresh_token(principal["user_id"]),
        "token_type": "bearer",
        "roles": principal["roles"],
    }


@auth_router.post("/refresh")
def refresh(request: Request, payload: RefreshRequest) -> dict[str, Any]:
    try:
        data = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="refresh 令牌无效或已过期")
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="需要 refresh 令牌")
    user = _service(request).get_user(str(data.get("sub", "")))
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return {
        "access_token": create_access_token(user["user_id"], user["roles"]),
        "token_type": "bearer",
    }


@auth_router.get("/me")
def me(user: Principal = Depends(get_current_user)) -> dict[str, Any]:
    return {"user_id": user.user_id, "roles": user.roles}


@auth_router.post("/ws-token", dependencies=[Depends(rate_limit("auth.ws_token"))])
def ws_token(user: Principal = Depends(get_current_user)) -> dict[str, Any]:
    """签发 WS 握手专用短期令牌（type='ws'，30 分钟）。"""
    return create_ws_token(user.user_id, user.roles)


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


@system_router.get(
    "/system/dead-letters", dependencies=[Depends(require_permission("system.dead_letters"))]
)
def dead_letters(request: Request, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    return _service(request).list_dead_letters(offset=offset, limit=limit)


@system_router.get("/system/health")
def system_health(request: Request) -> dict[str, Any]:
    """健康探针：DB 后端 + Redis + 熔断/限流可用性。"""
    redis_ok = get_redis() is not None
    return {
        "status": "ok",
        "app": settings.app_name,
        "components": {
            "database": "postgresql" if settings.database_url else "sqlite",
            "redis": "up" if redis_ok else "absent",
            "realtime_connections": hub.connection_count(),
        },
    }


@system_router.get("/system/ready")
def system_ready(request: Request) -> dict[str, Any]:
    # 服务已在 lifespan 建好即视为就绪。
    return {"ready": True}


@system_router.post(
    "/audit/integrity/verify", dependencies=[Depends(require_permission("audit.read"))]
)
def audit_integrity_verify(request: Request) -> dict[str, Any]:
    """链式完整性校验：重算审计哈希链，检测篡改/断链。"""
    return _service(request).verify_audit_integrity()


@system_router.get("/content/{content_id}/sor")
def content_sor(
    request: Request, content_id: str, user: Principal = Depends(get_current_user)
) -> dict[str, Any]:
    """获取内容的对外理由（SoR）。与内部审核笔记物理分离。"""
    return _service(request).generate_sor(content_id)


# --- ingestion / pipeline ----------------------------------------------------

@ingestion_router.post("/content/upload", dependencies=[Depends(rate_limit("content.upload"))])
def upload_content(request: Request, payload: ContentUploadRequest) -> dict[str, Any]:
    return _service(request).ingest_content(payload.model_dump())


@ingestion_router.post("/content/batch", dependencies=[Depends(rate_limit("content.batch"))])
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


@evidence_router.get("/evidence/{evidence_id}/media")
def evidence_media(request: Request, evidence_id: str) -> FileResponse:
    media = _service(request).get_evidence_media(evidence_id)
    return FileResponse(media["path"], media_type=media["media_type"])


@evidence_router.get("/evidence/{evidence_id}/frames/{frame_id}")
def evidence_frame(request: Request, evidence_id: str, frame_id: str) -> FileResponse:
    frame = _service(request).get_evidence_frame(evidence_id, frame_id)
    return FileResponse(frame["path"], media_type=frame["media_type"])


# --- human review (注意：静态路径 /queue 必须声明在 /{task_id} 之前) ----------

@human_router.get("/queue", dependencies=[Depends(require_permission("review.human.queue"))])
def review_queue(
    request: Request, offset: int = 0, limit: int = 20, status: str = "pending"
) -> dict[str, Any]:
    return _service(request).list_queue(offset=offset, limit=limit, status=status)


@human_router.post("/next")
def next_task(
    request: Request,
    payload: Optional[NextTaskRequest] = None,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    """按优先级原子领取下一个待审案件（含独立性 + 反疲劳约束）。"""
    jurisdiction = payload.jurisdiction if payload else None
    return _service(request).fetch_next(user.user_id, jurisdiction=jurisdiction)


@human_router.get("/current")
def current_task(
    request: Request,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    return _service(request).current_case(user.user_id)


@human_router.get("/{task_id}", dependencies=[Depends(require_permission("review.human.queue"))])
def review_case(request: Request, task_id: str) -> dict[str, Any]:
    return _service(request).get_case(task_id)


@human_router.post("/{task_id}/claim")
def claim_task(
    request: Request,
    task_id: str,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    # 审核员身份取自令牌，不再由客户端裸传。
    return _service(request).claim_task(task_id, user.user_id)


@human_router.post(
    "/{task_id}/decide", dependencies=[Depends(rate_limit("review.human.decide"))]
)
def decide_task(
    request: Request,
    task_id: str,
    payload: DecideRequest,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    body = payload.model_dump()
    body["reviewer_id"] = user.user_id  # 令牌身份覆盖请求体
    return _service(request).decide_task(task_id, body)


@human_router.post("/{task_id}/heartbeat")
def heartbeat_task(
    request: Request,
    task_id: str,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    return _service(request).heartbeat_task(task_id, user.user_id)


@human_router.post("/{task_id}/release")
def release_task(
    request: Request,
    task_id: str,
    user: Principal = Depends(require_permission("review.human.decide")),
) -> dict[str, Any]:
    return _service(request).release_task(task_id, user.user_id)


# --- reviewers（Stage 6） -----------------------------------------------------

@reviewers_router.get("/{reviewer_id}/stats")
def reviewer_stats(
    request: Request,
    reviewer_id: str,
    user: Principal = Depends(require_permission("review.human.queue")),
) -> dict[str, Any]:
    return _service(request).reviewer_stats(reviewer_id)


# --- appeal / 申诉闭环（Stage 7） --------------------------------------------

@appeal_router.post("/submit")
def submit_appeal(
    request: Request,
    payload: SubmitAppealRequest,
    user: Principal = Depends(get_current_user),
) -> dict[str, Any]:
    # 申诉人身份取自令牌。
    return _service(request).submit_appeal(payload.content_id, user.user_id, payload.reason)


@appeal_router.get("", dependencies=[Depends(require_permission("appeal.read"))])
def list_appeals(request: Request, status: Optional[str] = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    return _service(request).list_appeals(status=status, offset=offset, limit=limit)


@appeal_router.get("/{appeal_id}", dependencies=[Depends(require_permission("appeal.read"))])
def get_appeal(request: Request, appeal_id: str) -> dict[str, Any]:
    return _service(request).get_appeal(appeal_id)


@appeal_router.post("/{appeal_id}/claim")
def claim_appeal(
    request: Request,
    appeal_id: str,
    user: Principal = Depends(require_permission("appeal.decide")),
) -> dict[str, Any]:
    return _service(request).assign_appeal(appeal_id, user.user_id)


@appeal_router.post("/{appeal_id}/decide")
def decide_appeal(
    request: Request,
    appeal_id: str,
    payload: DecideAppealRequest,
    user: Principal = Depends(require_permission("appeal.decide")),
) -> dict[str, Any]:
    return _service(request).decide_appeal(appeal_id, user.user_id, payload.outcome, payload.reason)


# --- quality / 质检 + 数据回流（Stage 8） ------------------------------------

@quality_router.get("/summary", dependencies=[Depends(require_permission("quality.read"))])
def quality_summary(request: Request) -> dict[str, Any]:
    return _service(request).quality_summary()


@quality_router.get("/irr", dependencies=[Depends(require_permission("quality.read"))])
def quality_irr(request: Request) -> dict[str, Any]:
    return _service(request).compute_irr()


@quality_router.get("/flywheel", dependencies=[Depends(require_permission("quality.read"))])
def list_flywheel(
    request: Request, source_type: Optional[str] = None, only_passed: bool = False,
    offset: int = 0, limit: int = 50,
) -> dict[str, Any]:
    return _service(request).list_flywheel_samples(
        source_type=source_type, only_passed=only_passed, offset=offset, limit=limit
    )


@quality_router.get(
    "/flywheel/export", dependencies=[Depends(require_permission("quality.read"))]
)
def export_flywheel(request: Request, only_passed: bool = True) -> PlainTextResponse:
    body = _service(request).export_flywheel_jsonl(only_passed=only_passed)
    return PlainTextResponse(content=body, media_type="application/x-ndjson")


@quality_router.post("/golden/{task_id}")
def mark_golden(
    request: Request,
    task_id: str,
    expected_decision: str,
    user: Principal = Depends(require_permission("quality.write")),
) -> dict[str, Any]:
    return _service(request).mark_golden(task_id, expected_decision)


# --- policy / 策略维度管理（Stage 4） ----------------------------------------

@policy_router.get("/dimensions", dependencies=[Depends(require_permission("policy.read"))])
def list_dimensions(request: Request) -> dict[str, Any]:
    return _service(request).list_dimensions()


@policy_router.post("/dimensions")
def create_dimension(
    request: Request,
    payload: CreateDimensionRequest,
    user: Principal = Depends(require_permission("policy.write")),
) -> dict[str, Any]:
    return _service(request).create_dimension(payload.model_dump(), user.user_id)


@policy_router.patch("/dimensions/{dimension_id}")
def update_dimension(
    request: Request,
    dimension_id: str,
    payload: UpdateDimensionRequest,
    user: Principal = Depends(require_permission("policy.write")),
) -> dict[str, Any]:
    return _service(request).update_dimension(dimension_id, payload.model_dump(exclude_none=True), user.user_id)


@policy_router.post("/dimensions/{dimension_id}/approve")
def approve_dimension(
    request: Request,
    dimension_id: str,
    user: Principal = Depends(require_permission("policy.approve")),
) -> dict[str, Any]:
    return _service(request).approve_dimension(dimension_id, user.user_id)


@policy_router.post("/dimensions/{dimension_id}/transition")
def transition_dimension(
    request: Request,
    dimension_id: str,
    payload: TransitionRequest,
    user: Principal = Depends(require_permission("policy.transition")),
) -> dict[str, Any]:
    return _service(request).transition_dimension(dimension_id, payload.target_status, user.user_id)


@policy_router.post("/reload", dependencies=[Depends(require_permission("policy.transition"))])
def reload_strategies(request: Request) -> dict[str, Any]:
    return _service(request).reload_strategies()


@policy_router.get("/versions", dependencies=[Depends(require_permission("policy.read"))])
def list_policy_versions(request: Request) -> dict[str, Any]:
    return _service(request).list_policy_versions()


@policy_router.post("/versions")
def create_policy_version(
    request: Request,
    payload: CreatePolicyVersionRequest,
    user: Principal = Depends(require_permission("policy.write")),
) -> dict[str, Any]:
    return _service(request).create_policy_version(payload.model_dump(), user.user_id)


@policy_router.post("/versions/{version_id}/activate")
def activate_policy_version(
    request: Request,
    version_id: str,
    user: Principal = Depends(require_permission("policy.transition")),
) -> dict[str, Any]:
    return _service(request).activate_policy_version(version_id, user.user_id)


# --- WebSocket 实时推送（Stage 5） -------------------------------------------

def _ws_message_type(raw: str) -> str:
    """兼容纯文本（HEARTBEAT/PING）与 JSON 信封（{"type": ...}）。"""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return str(json.loads(raw).get("type", "")).upper()
        except (ValueError, TypeError):
            return ""
    return raw.upper()


async def review_websocket(websocket: WebSocket) -> None:
    """ws://host/ws/review?token=<ws_token|login_jwt>。双模式认证 + 心跳双协议。"""
    token = websocket.query_params.get("token", "")
    try:
        principal = principal_from_ws_token(token)
    except Exception:
        await websocket.close(code=4401)  # 认证失败
        return
    if not principal.user_id:
        await websocket.close(code=4401)
        return

    await hub.connect(websocket, principal.user_id, principal.roles)
    try:
        await websocket.send_json(make_envelope("connected", {"user_id": principal.user_id}))
        while True:
            raw = await websocket.receive_text()
            msg_type = _ws_message_type(raw)
            if msg_type == "HEARTBEAT":
                await websocket.send_json(make_envelope("HEARTBEAT_ACK", {}))
            elif msg_type == "PING":
                await websocket.send_json(make_envelope("PONG", {}))
            # 其余客户端消息（如 RECONNECT_SYNC）MVP 暂忽略。
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket, principal.user_id)


# --- dev ---------------------------------------------------------------------

@dev_router.post("/reset")
def dev_reset(request: Request) -> dict[str, Any]:
    return _service(request).reset()


@dev_router.post("/seed")
def dev_seed(request: Request) -> dict[str, Any]:
    return _service(request).seed()


@dev_router.post("/seed-users")
def dev_seed_users(request: Request) -> dict[str, Any]:
    return _service(request).seed_users()


@dev_router.post("/demo-cases")
def dev_demo_cases(request: Request) -> dict[str, Any]:
    return _service(request).seed_demo_cases()


_ROUTERS = (
    auth_router,
    system_router,
    ingestion_router,
    machine_router,
    evidence_router,
    human_router,
    reviewers_router,
    appeal_router,
    quality_router,
    policy_router,
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
        app.state.rate_limiter = RateLimiter(get_redis())
        worker.start()

        # Stage 5：把实时枢纽绑定到当前事件循环 + 接入 Redis 跨实例广播。
        loop = asyncio.get_running_loop()
        hub.bind_loop(loop)
        hub.attach_redis(get_redis())

        async def _sweeper() -> None:
            while True:
                await asyncio.sleep(settings.realtime_sweep_seconds)
                try:
                    await loop.run_in_executor(None, service.sweep_locks_and_sla)
                except Exception:  # noqa: BLE001 - sweep 故障不应中断服务
                    pass

        sweeper_task = loop.create_task(_sweeper())
        try:
            yield
        finally:
            sweeper_task.cancel()
            await hub.shutdown()
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

    # Stage 5：WebSocket 实时推送端点。
    app.add_api_websocket_route("/ws/review", review_websocket)

    # Stage 9：Prometheus 指标端点（标准 /metrics，文本 exposition）。
    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> PlainTextResponse:
        snapshot = request.app.state.service.metrics_snapshot()
        return PlainTextResponse(content=render_prometheus(snapshot), media_type="text/plain; version=0.0.4")

    # 静态前端（React 构建产物）挂在根路径，作为兜底；API 路由已先注册，优先匹配。
    frontend_dir = settings.frontend_dir
    if frontend_dir.exists():
        app.mount("/", SPAStaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_app()
