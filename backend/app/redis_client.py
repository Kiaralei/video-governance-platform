"""全局 Redis 客户端访问。

配置了 REDIS_URL 时返回一个共享客户端；否则返回 None —— 上层据此优雅降级
（限流放行、熔断器视为闭合）。这样本地/测试无 Redis 也能跑。
"""

from __future__ import annotations

from typing import Any, Optional

from .config import settings

_client: Optional[Any] = None
_initialized = False


def get_redis() -> Optional[Any]:
    global _client, _initialized
    if not _initialized:
        _initialized = True
        if settings.redis_url:
            import redis

            _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def reset_redis_cache() -> None:
    """测试辅助：清掉缓存的客户端与初始化标记。"""
    global _client, _initialized
    _client = None
    _initialized = False
