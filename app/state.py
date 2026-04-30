import asyncio
import json
from typing import Awaitable, Callable, Optional, Set

from fastapi import WebSocket

sensor_state: dict = {
    "breath_rate": None,
    "temperature": None,
    "posture":     None,
    "battery":     None,
    "ble_ok":      False,
    "cam_ok":      False,
    "last_update": None,
}

active_ws: Set[WebSocket]                       = set()
alert_log: list                                 = []
rtsp_proc: Optional[asyncio.subprocess.Process] = None

# 默认 broadcast 走 WebSocket；其它进程（如 ble_service.py）可通过 set_broadcast 注入自己的实现。
_broadcast_hook: Optional[Callable[[dict], Awaitable[None]]] = None


def set_broadcast(fn: Optional[Callable[[dict], Awaitable[None]]]) -> None:
    """注入自定义 broadcast 实现。传 None 恢复默认 WebSocket 行为。"""
    global _broadcast_hook
    _broadcast_hook = fn


async def broadcast(data: dict) -> None:
    if _broadcast_hook is not None:
        await _broadcast_hook(data)
        return
    if not active_ws:
        return
    msg  = json.dumps(data, ensure_ascii=False)
    dead: Set[WebSocket] = set()
    for ws in list(active_ws):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        active_ws.discard(ws)
