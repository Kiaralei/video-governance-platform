"""Stage 5：WebSocket 实时推送枢纽。

跨实例广播用 Redis Pub/Sub：本实例把事件 publish 到频道，各实例的后台订阅协程收到后
转发给本地连接。未配置 Redis 时退化为纯进程内广播（单实例/测试可用）。

难点：全链路是同步的（服务层在线程/Celery 里跑），而 WebSocket 是 asyncio。因此
publish_* 提供线程安全入口：持有事件循环引用，用 run_coroutine_threadsafe 把发送调度回
loop。若尚无 loop（未连过 WS），静默丢弃 —— 实时推送是尽力而为，不影响主流程。
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

REDIS_CHANNEL = "vgp:ws:events"


def make_envelope(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": uuid4().hex,
    }


class RealtimeHub:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # user_id -> set[WebSocket]；role -> set[WebSocket]
        self._by_user: dict[str, set] = defaultdict(set)
        self._roles: dict[Any, set[str]] = {}
        self._redis = None
        self._redis_thread: Optional[threading.Thread] = None
        self._redis_stop = threading.Event()

    # --- 生命周期 -----------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def attach_redis(self, redis) -> None:
        """配置 Redis 时启动后台订阅【线程】（跨实例广播）。

        注意：get_redis() 返回的是同步 redis 客户端，pubsub.get_message 是阻塞 socket 读。
        绝不能在事件循环的协程里直接调用它（会卡死整个 loop，拖垮所有 WS 与 HTTP）。因此
        订阅放在独立守护线程里跑，收到消息再用 run_coroutine_threadsafe 调度回 loop 转发。
        """
        self._redis = redis
        if redis is not None and self._loop is not None and self._redis_thread is None:
            self._redis_stop.clear()
            self._redis_thread = threading.Thread(target=self._subscribe_redis_blocking, daemon=True)
            self._redis_thread.start()

    async def shutdown(self) -> None:
        self._redis_stop.set()  # 通知订阅线程退出（守护线程，无需 join）
        self._redis_thread = None
        # 清除 loop 引用：应用关闭后不再向已死的循环调度（否则跨测试/重启会泄漏协程）。
        self._loop = None
        self._redis = None

    # --- 连接管理（在 WS 协程内调用） ---------------------------------------

    async def connect(self, websocket, user_id: str, roles: list[str]) -> None:
        await websocket.accept()
        self._by_user[user_id].add(websocket)
        self._roles[websocket] = set(roles)

    def disconnect(self, websocket, user_id: str) -> None:
        self._by_user.get(user_id, set()).discard(websocket)
        self._roles.pop(websocket, None)

    def connection_count(self) -> int:
        return sum(len(s) for s in self._by_user.values())

    # --- 本地发送（协程内） --------------------------------------------------

    async def _send_to_user(self, user_id: str, envelope: dict[str, Any]) -> None:
        dead = []
        for ws in list(self._by_user.get(user_id, set())):
            try:
                await ws.send_json(envelope)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)

    async def _send_to_role(self, role: str, envelope: dict[str, Any]) -> None:
        for user_id, sockets in list(self._by_user.items()):
            for ws in list(sockets):
                if role in self._roles.get(ws, set()):
                    try:
                        await ws.send_json(envelope)
                    except Exception:
                        self.disconnect(ws, user_id)

    async def _dispatch_local(self, target: dict[str, Any], envelope: dict[str, Any]) -> None:
        if target.get("user_id"):
            await self._send_to_user(target["user_id"], envelope)
        elif target.get("role"):
            await self._send_to_role(target["role"], envelope)

    # --- 线程安全发布入口（服务层/任意线程调用） -----------------------------

    def publish_to_user(self, user_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self._publish({"user_id": user_id}, make_envelope(event_type, payload))

    def publish_to_role(self, role: str, event_type: str, payload: dict[str, Any]) -> None:
        self._publish({"role": role}, make_envelope(event_type, payload))

    def _publish(self, target: dict[str, Any], envelope: dict[str, Any]) -> None:
        # 1) 跨实例：发到 Redis，让所有实例（含自己）在订阅协程里统一转发。
        if self._redis is not None:
            try:
                self._redis.publish(REDIS_CHANNEL, json.dumps({"target": target, "envelope": envelope}))
                return
            except Exception:
                pass  # Redis 故障降级为仅本地
        # 2) 无 Redis：仅本地转发。
        self._schedule_local(target, envelope)

    def _schedule_local(self, target: dict[str, Any], envelope: dict[str, Any]) -> None:
        coro = self._dispatch_local(target, envelope)
        loop = self._loop
        # loop 缺失/已关闭：显式 close 协程，避免 "coroutine was never awaited" 泄漏。
        if loop is None or loop.is_closed():
            coro.close()
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            coro.close()

    def _subscribe_redis_blocking(self) -> None:  # pragma: no cover - 需真实 Redis
        """在守护线程里跑：阻塞读 Redis，收到消息调度回事件循环转发给本地连接。"""
        try:
            pubsub = self._redis.pubsub()
            pubsub.subscribe(REDIS_CHANNEL)
        except Exception:
            return
        try:
            while not self._redis_stop.is_set():
                try:
                    message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                except Exception:
                    break
                if not message or message.get("type") != "message":
                    continue
                loop = self._loop
                if loop is None or loop.is_closed():
                    break
                try:
                    data = json.loads(message["data"])
                    asyncio.run_coroutine_threadsafe(
                        self._dispatch_local(data["target"], data["envelope"]), loop
                    )
                except Exception:
                    continue
        finally:
            try:
                pubsub.close()
            except Exception:
                pass


# 进程级单例：服务层与 WS 端点共用。
hub = RealtimeHub()
