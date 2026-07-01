from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Video Governance Platform MVP"
    tenant_id: str = "default"
    jurisdiction: str = "global"
    host: str = "127.0.0.1"
    port: int = int(os.environ.get("VGP_PORT", "8000"))
    database_url: str = os.environ.get("DATABASE_URL", os.environ.get("VGP_DATABASE_URL", ""))
    evidence_dir: Path = Path(os.environ.get("VGP_EVIDENCE_DIR", ROOT_DIR / "data" / "evidence"))
    media_dir: Path = Path(os.environ.get("VGP_MEDIA_DIR", ROOT_DIR / "data" / "media_assets"))
    max_media_bytes: int = int(os.environ.get("VGP_MAX_MEDIA_BYTES", str(500 * 1024 * 1024)))
    copy_local_media: bool = os.environ.get("VGP_COPY_LOCAL_MEDIA", "true").lower() in {"1", "true", "yes", "on"}
    enable_remote_download: bool = os.environ.get("VGP_ENABLE_REMOTE_DOWNLOAD", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    remote_download_timeout_seconds: float = float(os.environ.get("VGP_REMOTE_DOWNLOAD_TIMEOUT_SECONDS", "30"))
    ffmpeg_path: str = os.environ.get("VGP_FFMPEG_PATH", "")
    ffprobe_path: str = os.environ.get("VGP_FFPROBE_PATH", "")
    asr_model_url: str = os.environ.get("VGP_ASR_MODEL_URL", "")
    ocr_model_url: str = os.environ.get("VGP_OCR_MODEL_URL", "")
    vision_model_url: str = os.environ.get("VGP_VISION_MODEL_URL", "")
    model_api_key: str = os.environ.get("VGP_MODEL_API_KEY", "")
    model_timeout_seconds: float = float(os.environ.get("VGP_MODEL_TIMEOUT_SECONDS", "30"))
    # React 前端构建产物（Vite `npm run build` -> frontend/dist）。未构建时后端跳过挂载。
    frontend_dir: Path = ROOT_DIR / "frontend" / "dist"
    pipeline_poll_seconds: float = float(os.environ.get("VGP_PIPELINE_POLL_SECONDS", "0.5"))
    max_pipeline_backlog: int = int(os.environ.get("VGP_MAX_PIPELINE_BACKLOG", "1000"))
    max_batch_ingest_items: int = int(os.environ.get("VGP_MAX_BATCH_INGEST_ITEMS", "100"))
    # Celery / Redis：配置 broker 则机审流水线走异步 chain；留空则退化为 drain / 线程 worker。
    redis_url: str = os.environ.get("REDIS_URL", "")
    celery_broker_url: str = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", ""))
    celery_result_backend: str = os.environ.get(
        "CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "")
    )
    # JWT 认证。生产必须通过环境变量覆盖 JWT_SECRET。
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = int(os.environ.get("VGP_ACCESS_TOKEN_TTL", str(60 * 60)))
    refresh_token_ttl_seconds: int = int(os.environ.get("VGP_REFRESH_TOKEN_TTL", str(14 * 24 * 3600)))
    # Stage 5：WebSocket 短期令牌 + 案件锁 + SLA。
    ws_token_ttl_seconds: int = int(os.environ.get("VGP_WS_TOKEN_TTL", str(30 * 60)))
    case_lock_ttl_seconds: int = int(os.environ.get("VGP_CASE_LOCK_TTL", str(30 * 60)))
    sla_default_seconds: int = int(os.environ.get("VGP_SLA_DEFAULT_SECONDS", str(4 * 3600)))
    sla_warning_seconds: int = int(os.environ.get("VGP_SLA_WARNING_SECONDS", str(30 * 60)))
    realtime_sweep_seconds: float = float(os.environ.get("VGP_REALTIME_SWEEP_SECONDS", "15"))
    # Stage 6：反疲劳 —— CSAM/敏感内容曝光上限 + 强制休息。
    csam_per_shift_limit: int = int(os.environ.get("VGP_CSAM_PER_SHIFT_LIMIT", "10"))
    csam_per_week_limit: int = int(os.environ.get("VGP_CSAM_PER_WEEK_LIMIT", "30"))
    shift_window_seconds: int = int(os.environ.get("VGP_SHIFT_WINDOW_SECONDS", str(8 * 3600)))
    week_window_seconds: int = int(os.environ.get("VGP_WEEK_WINDOW_SECONDS", str(7 * 24 * 3600)))
    forced_break_after: int = int(os.environ.get("VGP_FORCED_BREAK_AFTER", "50"))
    forced_break_window_seconds: int = int(os.environ.get("VGP_FORCED_BREAK_WINDOW_SECONDS", "3600"))


settings = Settings()
