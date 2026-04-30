"""BabySentinel — 启动入口"""
import asyncio
import json
import time
import urllib.request
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, CFG, REC_DIR, log
from app.state import active_ws, sensor_state
import app.state as state
import app.camera as camera
import app.baby_log as baby_log
from app.alerts import trigger_alert
from notify.discord_bot import GatewayClient

# BLE 字段由 ble_service.py 进程管理，通过 /api/internal/sensor 推送过来
_BLE_FIELDS = frozenset((
    "breath_rate", "temperature", "posture",
    "battery", "ble_ok", "last_update",
))

_FEED_REPEAT    = CFG.get("feed_repeat_s", 1800)

_reminder_feed_ts:   float = 0   # 正在追踪的那次喂奶的 ts
_last_reminder_time: float = 0   # 上次发出提醒的时刻


async def _feed_reminder_loop():
    global _reminder_feed_ts, _last_reminder_time
    while True:
        await asyncio.sleep(60)
        try:
            interval_min   = int(CFG.get("baby", {}).get("feed_interval_min", 150))
            feed_threshold = interval_min * 60

            entries  = baby_log.get_today()
            feeds    = [e for e in entries if e.get("type") in baby_log.FEED_TYPES]
            if not feeds:
                _reminder_feed_ts = _last_reminder_time = 0
                continue

            last_ts   = feeds[-1]["ts"]
            now       = time.time()
            elapsed_s = now - last_ts

            # 新的喂奶记录 → 重置状态
            if last_ts != _reminder_feed_ts and elapsed_s < feed_threshold:
                _reminder_feed_ts = _last_reminder_time = 0
                continue

            if elapsed_s < feed_threshold:
                continue

            # 判断是否该发提醒
            if _reminder_feed_ts != last_ts:
                # 首次提醒（刚到间隔时间）
                _reminder_feed_ts   = last_ts
                _last_reminder_time = now
            elif now - _last_reminder_time >= _FEED_REPEAT:
                # 每 30 分钟重复
                _last_reminder_time = now
            else:
                continue

            h = int(elapsed_s // 3600)
            m = int((elapsed_s % 3600) // 60)
            elapsed_str = f"{h}時間{m}分" if h else f"{m}分"
            msg = f"🍼 授乳の時間です\n最後の授乳から {elapsed_str} が経過しています。\n結葵ちゃんの授乳をお忘れなく 💕"

            await trigger_alert(msg, "warning")
            await state.broadcast({"type": "baby_stats", **baby_log.get_stats()})
        except Exception as e:
            log.debug(f"[FeedReminder] {e}")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # BLE 已分离为独立进程 ble_service.py，此处不再启动
    asyncio.create_task(camera.rtsp_loop())
    asyncio.create_task(_feed_reminder_loop())
    # 录像由独立进程 recorder_service.py 负责，此处不再启动

    token = CFG.get("discord_token", "")
    if token:
        gw = GatewayClient(token, lambda: sensor_state)
        asyncio.create_task(gw.run())

    yield

    if state.rtsp_proc and state.rtsp_proc.returncode is None:
        state.rtsp_proc.terminate()


import os as _os
import csv as _csv
_os.makedirs(REC_DIR, exist_ok=True)

app = FastAPI(lifespan=_lifespan, title="BabySentinel")
app.mount("/static",      StaticFiles(directory=_os.path.join(BASE_DIR, "static")), name="static")
app.mount("/recordings",  StaticFiles(directory=REC_DIR),                           name="recordings")


@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    active_ws.add(websocket)
    await websocket.send_text(json.dumps(
        {
            "type":        "state",
            "sensor":      sensor_state,
            "baby_stats":  baby_log.get_stats(),
            "birth_date":  CFG.get("baby", {}).get("birth_date", ""),
        },
        ensure_ascii=False,
    ))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_ws.discard(websocket)


@app.get("/")
async def root():
    with open(_os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        html = f.read().replace("__MANAGER_PORT__", str(CFG.get("manager_port", 9091)))
    return HTMLResponse(html)


@app.post("/api/log")
async def post_log(request: Request):
    body = await request.json()
    entry = baby_log.add_entry(body)
    stats = baby_log.get_stats()
    await state.broadcast({"type": "baby_stats", **stats})
    return JSONResponse({"ok": True, "entry": entry, "stats": stats})


@app.delete("/api/log/entry/{ts}")
async def delete_log_entry(ts: int):
    ok = baby_log.delete_entry(ts)
    if not ok:
        return JSONResponse({"ok": False}, status_code=404)
    stats = baby_log.get_stats()
    await state.broadcast({"type": "baby_stats", **stats})
    return JSONResponse({"ok": True, "stats": stats})


@app.put("/api/log/entry/{ts}")
async def update_log_entry(ts: int, request: Request):
    body = await request.json()
    entry = baby_log.update_entry(ts, body)
    if entry is None:
        return JSONResponse({"ok": False}, status_code=404)
    stats = baby_log.get_stats()
    await state.broadcast({"type": "baby_stats", **stats})
    return JSONResponse({"ok": True, "entry": entry, "stats": stats})


@app.get("/api/log/today")
async def get_log_today():
    return JSONResponse(baby_log.get_today())


@app.get("/api/log/stats")
async def get_log_stats():
    return JSONResponse(baby_log.get_stats())


@app.get("/api/log/dates")
async def get_log_dates():
    return JSONResponse(baby_log.list_dates())


@app.get("/api/log/date/{date_str}")
async def get_log_date(date_str: str):
    return JSONResponse(baby_log.get_date_entries(date_str))


@app.get("/api/sensor")
async def get_sensor():
    """返回当前传感器状态快照（不依赖 WebSocket）。"""
    return JSONResponse(sensor_state)


@app.post("/api/internal/sensor")
async def internal_sensor_push(request: Request):
    """接收来自 ble_service.py 的传感器 / 告警推送。"""
    data = await request.json()
    if data.get("type") == "sensor":
        for k, v in data.items():
            if k in _BLE_FIELDS:
                sensor_state[k] = v
        await state.broadcast({"type": "sensor", **sensor_state})
    else:
        await state.broadcast(data)
    return JSONResponse({"ok": True})


@app.post("/api/sensor/refresh")
async def post_sensor_refresh():
    """代理到 ble_service.py，触发设备重新推送所有传感器数据。"""
    ble_port = CFG.get("ble_port", 8082)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{ble_port}/api/sensor/refresh",
            data=b"", method="POST",
        )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=3).read()
        )
        return JSONResponse(json.loads(result))
    except Exception:
        return JSONResponse({"ok": False, "ble_connected": False})


@app.get("/playback")
async def playback_page():
    with open(_os.path.join(BASE_DIR, "static", "playback.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/recordings")
async def get_recording_dates():
    """返回有录像的日期列表（降序）。"""
    if not _os.path.isdir(REC_DIR):
        return JSONResponse([])
    dates = [
        d for d in _os.listdir(REC_DIR)
        if _os.path.isdir(_os.path.join(REC_DIR, d)) and len(d) == 10
    ]
    return JSONResponse(sorted(dates, reverse=True))


@app.get("/api/recordings/{date}/segments")
async def get_recording_segments(date: str):
    """返回指定日期的视频片段列表（含开始时间戳）。"""
    vid_dir = _os.path.join(REC_DIR, date, "video")
    if not _os.path.isdir(vid_dir):
        return JSONResponse([])
    from datetime import datetime as _dt

    # Load PTS-based timestamps from index.csv if available (written by ffmpeg -segment_list).
    # CSV format: filename,start_pts_time,end_pts_time  — values are Unix timestamps from TAPO camera.
    pts_map: dict[str, float] = {}
    idx_path = _os.path.join(vid_dir, "index.csv")
    _EPOCH_2001 = 978307200  # sanity floor: any ts > this is a real Unix timestamp
    if _os.path.exists(idx_path):
        try:
            with open(idx_path, newline="", encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if len(row) >= 2:
                        fname = _os.path.basename(row[0])
                        try:
                            pts = float(row[1])
                            if pts > _EPOCH_2001:
                                pts_map[fname] = pts
                        except ValueError:
                            pass
        except Exception:
            pass

    segments = []
    for f in sorted(_os.listdir(vid_dir)):
        if not f.endswith(".mp4"):
            continue
        if f in pts_map:
            ts = int(pts_map[f])
        else:
            try:
                t = _dt.strptime(f"{date} {f[:-4]}", "%Y-%m-%d %H-%M-%S")
                ts = int(t.timestamp())
            except ValueError:
                continue
        segments.append({"file": f, "ts": ts, "url": f"/recordings/{date}/video/{f}"})
    return JSONResponse(segments)


@app.get("/api/recordings/{date}/sensors")
async def get_recording_sensors(date: str):
    """返回指定日期的传感器时序数据（JSON 数组）。"""
    path = _os.path.join(REC_DIR, date, "sensors.jsonl")
    if not _os.path.exists(path):
        return JSONResponse([])
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return JSONResponse(rows)


if __name__ == "__main__":
    log.info(f"[SERVER] 启动 BabySentinel  http://{CFG['web_host']}:{CFG['web_port']}")
    log.info(f"[SERVER] 本机访问: http://localhost:{CFG['web_port']}")
    uvicorn.run(
        "server:app",
        host=CFG["web_host"],
        port=CFG["web_port"],
        log_level="warning",
        reload=False,
    )
