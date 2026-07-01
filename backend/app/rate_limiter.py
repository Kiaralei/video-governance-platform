"""令牌桶/固定窗口限流器（Redis 后端）。对齐设计 §12.2。

实现用固定窗口计数（INCR + EXPIRE），跨实例共享计数靠 Redis。
Redis 不可用时优雅降级为放行（不因限流基础设施故障阻断业务）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int
    window_seconds: int


# 关键写入端点的默认限额（对齐设计 §12.2）。
RATE_LIMITS: dict[str, RateLimitRule] = {
    "content.upload": RateLimitRule(max_requests=10, window_seconds=60),
    "content.batch": RateLimitRule(max_requests=5, window_seconds=60),
    "review.human.decide": RateLimitRule(max_requests=60, window_seconds=60),
    "auth.login": RateLimitRule(max_requests=10, window_seconds=60),
    "auth.ws_token": RateLimitRule(max_requests=10, window_seconds=60),
}


class RateLimiter:
    def __init__(self, redis_client: Optional[Any] = None):
        self._redis = redis_client

    def check(self, name: str, identity: str, rule: RateLimitRule) -> bool:
        """True=放行，False=超限。Redis 缺失或异常时放行（优雅降级）。"""
        client = self._redis
        if client is None:
            return True
        window = int(time.time()) // rule.window_seconds
        key = f"ratelimit:{name}:{identity}:{window}"
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, rule.window_seconds)
        except Exception:  # noqa: BLE001 - 限流故障不应拖垮请求
            return True
        return count <= rule.max_requests
