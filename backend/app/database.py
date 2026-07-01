"""数据库引擎与会话工厂。

原来这里手工维护两份 DDL 字符串 + 一个把 ``?`` 正则替换成 ``%s`` 的适配器 +
一个自写的 psycopg 连接包装。现在统一交给 SQLAlchemy：

- 结构来自 models.py（单一事实源，见 :mod:`app.models`）
- 方言差异（SQLite / PostgreSQL）由 SQLAlchemy 处理
- 生产环境结构变更走 Alembic 迁移；测试/本地用 create_all 直接建表
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings
from .models import Base


def is_postgres_enabled() -> bool:
    return settings.database_url.startswith(("postgresql://", "postgres://"))


def normalize_database_url(url: str) -> str:
    """强制使用 psycopg(v3) 驱动，避免裸 ``postgresql://`` 落到默认的 psycopg2。"""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _resolve_url(db_path: Path | None) -> str:
    if is_postgres_enabled():
        return normalize_database_url(settings.database_url)
    if db_path is None:
        raise RuntimeError(
            "PostgreSQL DATABASE_URL is required for runtime. "
            "SQLite is only available for tests that pass an explicit db_path."
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def create_db_engine(db_path: Path | None = None) -> Engine:
    """根据配置构建引擎：有 PostgreSQL DATABASE_URL 走 PG，否则用测试注入的 sqlite 文件。"""
    url = _resolve_url(db_path)
    if url.startswith("sqlite"):
        # NullPool：不缓存连接，每次用完即关。既贴近原来“每调用一次开一次连接”的语义，
        # 也避免 Windows 上因连接常驻而无法删除临时 sqlite 文件（测试 teardown）。
        engine = create_engine(
            url,
            future=True,
            poolclass=NullPool,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        _install_sqlite_pragmas(engine)
        return engine
    return create_engine(url, future=True, pool_pre_ping=True)


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def init_db(engine: Engine) -> None:
    """从 ORM 元数据建表。真实数据库的结构演进走 Alembic；这里让本地/测试一步到位。"""
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, class_=Session)
