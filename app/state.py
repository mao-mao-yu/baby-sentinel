import asyncio
import json
from typing import Optional, Set

from fastapi import WebSocket

sensor_state: dict = {
    "breath_rate": None,
    "temperature": None,
    "humidity":    None,
    "posture":     None,
    "battery":     None,
    "is_wearing":  None,
    "ble_ok":      False,
    "cam_ok":      False,
    "last_update": None,
}

active_ws: Set[WebSocket]                        = set()
alert_log: list                                  = []
rtsp_proc: Optional[asyncio.subprocess.Process] = None


async def broadcast(data: dict) -> None:
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
