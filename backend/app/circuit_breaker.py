"""滑动窗口分布式熔断器（Redis 后端）。对齐设计 §10.1。

在时间窗口内记录调用成功/失败（Redis 有序集合按时间打分），失败率超阈值则打开。
成功不会清零失败记录，而是作为正常样本参与失败率计算（修复 reset-on-any-success 缺陷）。
Redis 不可用时视为恒闭合（放行），不因熔断基础设施故障阻断业务。

状态机：CLOSED --失败率超阈值--> OPEN --recovery_timeout--> HALF_OPEN
        HALF_OPEN --试探成功--> CLOSED / --试探失败--> OPEN
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar
from uuid import uuid4

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """熔断器打开时拒绝调用。"""


class CircuitBreaker:
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        name: str = "default",
        failure_rate_threshold: float = 0.5,
        minimum_calls: int = 5,
        window_seconds: int = 60,
        recovery_timeout: int = 60,
        time_fn: Callable[[], float] = time.time,
    ):
        self._redis = redis_client
        self.name = name
        self.failure_rate_threshold = failure_rate_threshold
        self.minimum_calls = minimum_calls
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self._now = time_fn

    # --- keys ---
    @property
    def _fail_key(self) -> str:
        return f"circuit:{self.name}:failures"

    @property
    def _succ_key(self) -> str:
        return f"circuit:{self.name}:successes"

    @property
    def _state_key(self) -> str:
        return f"circuit:{self.name}:state"

    @property
    def _opened_key(self) -> str:
        return f"circuit:{self.name}:opened_at"

    # --- public API ---
    def allow(self) -> bool:
        """是否放行本次调用。OPEN 且未到恢复期返回 False；到期后进入 HALF_OPEN 放行一次试探。"""
        if self._redis is None:
            return True
        if self._get_state() != CircuitState.OPEN.value:
            return True
        opened_at = float(self._redis.get(self._opened_key) or 0.0)
        if self._now() - opened_at >= self.recovery_timeout:
            self._redis.set(self._state_key, CircuitState.HALF_OPEN.value)
            return True
        return False

    def record_success(self) -> None:
        if self._redis is None:
            return
        if self._get_state() == CircuitState.HALF_OPEN.value:
            self._close()
            return
        self._add(self._succ_key)

    def record_failure(self) -> None:
        if self._redis is None:
            return
        if self._get_state() == CircuitState.HALF_OPEN.value:
            self._open()
            return
        self._add(self._fail_key)
        if self._failure_rate_exceeded():
            self._open()

    def call(self, fn: Callable[[], T]) -> T:
        """包裹一次调用：OPEN 抛 CircuitOpenError；否则执行并记录成败。"""
        if not self.allow():
            raise CircuitOpenError(self.name)
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def state(self) -> str:
        return self._get_state()

    # --- internals ---
    def _get_state(self) -> str:
        return self._redis.get(self._state_key) or CircuitState.CLOSED.value

    def _add(self, key: str) -> None:
        now = self._now()
        cutoff = now - self.window_seconds
        self._redis.zremrangebyscore(self._fail_key, 0, cutoff)
        self._redis.zremrangebyscore(self._succ_key, 0, cutoff)
        self._redis.zadd(key, {uuid4().hex: now})

    def _failure_rate_exceeded(self) -> bool:
        failures = self._redis.zcard(self._fail_key)
        successes = self._redis.zcard(self._succ_key)
        total = failures + successes
        if total < self.minimum_calls:
            return False
        return (failures / total) >= self.failure_rate_threshold

    def _open(self) -> None:
        self._redis.set(self._state_key, CircuitState.OPEN.value)
        self._redis.set(self._opened_key, self._now())

    def _close(self) -> None:
        self._redis.set(self._state_key, CircuitState.CLOSED.value)
        self._redis.delete(self._fail_key, self._succ_key, self._opened_key)
