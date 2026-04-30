"""BabySentinel BLE 服务 — 独立进程

负责 Sense-U BLE 连接、传感器解析，将状态变更通过 HTTP 推送给 server.py。

启动:
    python ble_service.py
"""

import asyncio
import json
import urllib.request
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

import app.state as state
import app.ble as ble
from app.config import CFG, log

BLE_PORT = CFG.get("ble_port", 8082)
WEB_PORT = CFG.get("web_port", 8080)

# ── 广播替代：HTTP 推送到 server.py ───────────────────────────────────

async def _push_to_server(data: dict) -> None:
    """将传感器 / 告警事件推送给 server.py 的内部接口。"""
    try:
        payload = json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{WEB_PORT}/api/internal/sensor",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=2)
        )
    except Exception:
        pass  # server.py 未启动或暂时不可达，静默忽略


# 本进程内无 WebSocket 客户端，把所有 broadcast 改为 HTTP 推送给 server.py
state.set_broadcast(_push_to_server)

# ── FastAPI ───────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(_: FastAPI):
    asyncio.create_task(ble.loop())
    yield


app = FastAPI(title="BabySentinel BLE Service", lifespan=_lifespan)


@app.get("/api/sensor")
async def get_sensor():
    """返回本进程维护的传感器状态快照（供调试 / recorder 使用）。"""
    return JSONResponse(state.sensor_state)


@app.post("/api/sensor/refresh")
async def refresh_sensor():
    """向 Sense-U 发送 0xBA get_baby_data 命令，触发全量数据推送。"""
    ok = await ble.request_refresh()
    return JSONResponse({"ok": ok, "ble_connected": state.sensor_state.get("ble_ok", False)})


# ── 入口 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info(f"[BLE Service] 启动  http://localhost:{BLE_PORT}")
    uvicorn.run(
        "ble_service:app",
        host="0.0.0.0",
        port=BLE_PORT,
        log_level="warning",
        reload=False,
    )
