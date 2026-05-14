import json
from typing import Awaitable, Callable, Optional, Set

from fastapi import WebSocket

sensor_state: dict = {
    "breath_rate": None,
    "temperature": None,
    "posture":     None,
    "battery":     None,
    "wearing":     None,   # bool：True=已佩戴 / False=未佩戴 / None=未知
    "charge":      None,   # 0=未充电 / 1=充电中 / 2=已充满
    "activity":    None,   # 0–255 活动量（暂未在前端展示）
    "ble_ok":      False,
    "cam_ok":      False,
    "last_update": None,
}

active_ws: Set[WebSocket] = set()
alert_log: list           = []

# BLE 失联时需要清空的字段（保留 ble_ok / cam_ok 由调用方单独管理）
_BLE_DATA_FIELDS = (
    "breath_rate", "temperature", "posture", "battery",
    "wearing", "charge", "activity", "last_update",
)


def clear_ble_data() -> None:
    """BLE 失联（心跳超时 / 找不到设备 / 连接断开）时调用，清空传感器读数避免 UI 显示过期值。"""
    for k in _BLE_DATA_FIELDS:
        sensor_state[k] = None

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
    msg = json.dumps(data, ensure_ascii=False)

    # 并行 + 单连接 2s 超时：之前是串行 await，任一客户端的 TCP buffer 满
    # （手机锁屏 / 网络慢 / 已断但 socket 未识别）就让整个 broadcast 卡死，
    # 连带 POST /api/log 等调用 broadcast 的 handler 也 hang 直到 TCP keepalive
    # 超时。改并行后慢客户端单独超时被踢，不影响其他端。
    import asyncio
    async def _send_one(ws: WebSocket) -> WebSocket | None:
        try:
            await asyncio.wait_for(ws.send_text(msg), timeout=2.0)
            return None
        except Exception:
            return ws

    results = await asyncio.gather(
        *(_send_one(ws) for ws in list(active_ws)),
        return_exceptions=False,
    )
    for dead_ws in results:
        if dead_ws is not None:
            active_ws.discard(dead_ws)
