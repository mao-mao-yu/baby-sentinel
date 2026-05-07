"""BabySentinel — 启动入口"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import time
import urllib.request
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shared.config import BASE_DIR, REC_DIR, log
from shared.state import active_ws, sensor_state
import shared.state as state
import shared.camera as camera
import services.web.baby_log as baby_log
import shared.sensors_db as sensors_db
from shared.video_util import is_complete_mp4
from shared.alerts import trigger_alert
from shared.i18n import t
from shared.notify.discord_bot import GatewayClient
from services.web.config import (
    WEB_HOST, WEB_PORT, MANAGER_PORT,
    FEED_REPEAT_S, BLE_HEALTH_TIMEOUT_S, BLE_POLL_INTERVAL_S,
    SEGMENT_S, BABY, DISCORD_TOKEN,
)
from shared.config import ROOT_CFG

# BLE 字段由远端 sense-u-ble (Pi) 服务通过 /api/internal/sensor 推送过来
_BLE_FIELDS = frozenset((
    "breath_rate", "temperature", "posture",
    "battery", "wearing", "charge", "activity",
    "ble_ok", "last_update",
))

_FEED_REPEAT        = FEED_REPEAT_S
_BLE_HEALTH_TIMEOUT = BLE_HEALTH_TIMEOUT_S

_reminder_feed_ts:   float = 0   # 正在追踪的那次喂奶的 ts
_last_reminder_time: float = 0   # 上次发出提醒的时刻
_last_ble_push_at:   float = 0   # 最近一次 ble_service.py 推送时刻（心跳）

# 当前未关闭的告警弹窗（所有 web client 共享一份；用户在任意一台点关闭 → 全部关）
# - _alert_event 在用户点关闭或被新告警顶替时被 set，让正在等响应的 Pi 请求继续返回
# - _alert_data 缓存 payload，新连入的 WS client 在握手帧里能拿到当前告警
# - Pi 已删掉 HTTP 2s timeout（用户改的），所以这里默认无限等。_ACK_WAIT_TIMEOUT 只是
#   一个 sanity 上限：万一前端关闭逻辑出 bug 卡住，至少 1 小时后强制放过让设备 LED 能停。
_alert_lock:           asyncio.Lock        = asyncio.Lock()
_alert_event:  asyncio.Event | None = None
_alert_data:           dict | None = None
_ACK_WAIT_TIMEOUT: float = 3600.0   # 1h sanity fallback，正常路径靠用户点关闭


async def _ble_health_loop():
    """ble_service.py 心跳监测：长时间无推送 → 标 ble_ok=false 广播。"""
    while True:
        await asyncio.sleep(_BLE_HEALTH_TIMEOUT / 2)
        if _last_ble_push_at == 0:
            continue  # 还从未收到过推送
        elapsed = time.time() - _last_ble_push_at
        if elapsed > _BLE_HEALTH_TIMEOUT and sensor_state.get("ble_ok"):
            sensor_state["ble_ok"] = False
            state.clear_ble_data()
            log.warning(f"[Server] BLE 心跳超时 ({elapsed:.0f}s)，标记未连接 + 清空传感器字段")
            await state.broadcast({"type": "sensor", **sensor_state})


async def _feed_reminder_loop():
    global _reminder_feed_ts, _last_reminder_time
    while True:
        await asyncio.sleep(60)
        try:
            interval_min   = int(BABY.get("feed_interval_min", 150))
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
            duration = t("duration_h_m", h=h, m=m) if h else t("duration_m", m=m)
            name     = BABY.get("name", "")
            msg      = t("alert_feed", duration=duration, name=name)

            await trigger_alert(msg, "warning")
            await state.broadcast({"type": "baby_stats", **baby_log.get_stats()})
        except Exception as e:
            log.debug(f"[FeedReminder] {e}")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # BLE 已分离为独立进程 ble_service.py，此处不再启动
    asyncio.create_task(camera.rtsp_loop())
    asyncio.create_task(_feed_reminder_loop())
    asyncio.create_task(_ble_health_loop())
    # 录像由独立进程 recorder_service.py 负责，此处不再启动

    token = DISCORD_TOKEN
    if token:
        async def _bot_add_entry(entry: dict) -> dict:
            e = baby_log.add_entry(entry)
            await state.broadcast({"type": "baby_stats", **baby_log.get_stats()})
            return e

        async def _bot_delete_entry(ts: int) -> bool:
            ok = baby_log.delete_entry(ts)
            if ok:
                await state.broadcast({"type": "baby_stats", **baby_log.get_stats()})
            return ok

        gw = GatewayClient(
            token,
            lambda: sensor_state,
            lambda: (baby_log.get_today(), baby_log.get_stats()),
            add_entry=_bot_add_entry,
            delete_entry=_bot_delete_entry,
        )
        asyncio.create_task(gw.run())

    yield
    # go2rtc 子进程由 manager 拥有；此处无需清理。


import os as _os
import csv as _csv
_os.makedirs(REC_DIR, exist_ok=True)

_STATIC_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static")

app = FastAPI(lifespan=_lifespan, title="BabySentinel")
app.mount("/static",      StaticFiles(directory=_STATIC_DIR), name="static")
app.mount("/recordings",  StaticFiles(directory=REC_DIR),                           name="recordings")

# 静态资源版本号——server 启动时一次确定，强制浏览器跳过旧 cache
_CFG_VER = str(int(time.time()))


@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    active_ws.add(websocket)
    # 握手帧：当前传感器快照 + 育儿统计；如果有未关闭的告警弹窗也一并带上，
    # 让刚连入的 client 也能立即弹出（多设备同步）。
    handshake = {
        "type":        "state",
        "sensor":      sensor_state,
        "baby_stats":  baby_log.get_stats(),
        "birth_date":  BABY.get("birth_date", ""),
    }
    if _alert_data is not None:
        handshake["alert_active"] = _alert_data
    await websocket.send_text(json.dumps(handshake, ensure_ascii=False))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_ws.discard(websocket)


@app.get("/")
async def root():
    with open(_os.path.join(_STATIC_DIR, "index.html"), encoding="utf-8") as f:
        html = (f.read()
                .replace("__MANAGER_PORT__", str(MANAGER_PORT))
                .replace("__CFG_VER__", _CFG_VER))
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
    global _last_ble_push_at
    data = await request.json()
    if data.get("type") == "sensor":
        _last_ble_push_at = time.time()  # 心跳：每次推送即视为 ble_service 还活着
        for k, v in data.items():
            if k in _BLE_FIELDS:
                sensor_state[k] = v
        # 打印到 server 进程的 stdout，方便在 manager UI 的日志面板里直观看到 Pi 推过来的值。
        # sense-u-ble 不管 BLE 连没连上都会按 ble_poll_interval_s 持续推送（心跳式），
        # 全 null 的纯心跳没价值——降到 DEBUG，只有任一字段有值时才打 INFO 避免 log spam。
        _has_data = any(data.get(k) is not None for k in
                        ("breath_rate", "temperature", "posture", "battery",
                         "wearing", "charge", "activity"))
        (log.info if _has_data else log.debug)(
            "[SensorPush] breath=%s temp=%s posture=%s batt=%s wearing=%s charge=%s activity=%s ble_ok=%s",
            data.get("breath_rate"), data.get("temperature"),
            data.get("posture"),     data.get("battery"),
            data.get("wearing"),     data.get("charge"),
            data.get("activity"),    data.get("ble_ok"),
        )
        await state.broadcast({"type": "sensor", **sensor_state})
    elif data.get("type") == "alert":
        # Pi 端 sense-u-ble 不接通知渠道，由本服务端统一收口
        global _alert_event, _alert_data
        msg   = data.get("message", "")
        level = data.get("level", "warning")
        mode  = data.get("mode")          # 设备原始 alertMode（int），sense-u-ble v2 起带这个字段
        ts    = data.get("timestamp")
        if ROOT_CFG.get("alert_notify_enabled", True):
            log.info("[AlertPush] dispatch mode=%s level=%s msg=%s", mode, level, msg)
            await trigger_alert(msg, level)
        else:
            log.warning("[AlertPush] notify DISABLED → mode=%s level=%s msg=%s", mode, level, msg)

        # 每个告警发一个唯一 id，前端 dismiss 时把 id 带回 → 防止"旧 dismiss + 新 alert"
        # 顺序乱掉时把刚弹出的新弹窗误关。
        alert_id = uuid.uuid4().hex[:8]
        payload  = {
            "type":      "alert_active",
            "alert_id":  alert_id,
            "level":     level,
            "mode":      mode,
            "message":   msg,
            "timestamp": ts,
        }
        async with _alert_lock:
            # 已有 pending alert 还没被 dismiss → 把旧的"顶替"掉（旧的 HTTP 请求会立即返回 ack=true）
            if _alert_event is not None and not _alert_event.is_set():
                _alert_event.set()
            ev = asyncio.Event()
            _alert_event = ev
            _alert_data  = payload

        await state.broadcast(payload)

        # 等用户在任意一台 web 上点关闭按钮（POST /api/alert/dismiss）。
        # _ACK_WAIT_TIMEOUT 是 sanity 上限——Pi 端已无超时，正常路径靠用户。
        try:
            await asyncio.wait_for(ev.wait(), timeout=_ACK_WAIT_TIMEOUT)
            log.info("[AlertPush] id=%s mode=%s acknowledged → ack=true", alert_id, mode)
        except asyncio.TimeoutError:
            log.warning("[AlertPush] id=%s mode=%s wait timeout (%.0fs) → ack=true (sanity fallback)",
                        alert_id, mode, _ACK_WAIT_TIMEOUT)
            async with _alert_lock:
                if _alert_data is payload:
                    _alert_data = None
            await state.broadcast({"type": "alert_dismissed", "alert_id": alert_id})

        return JSONResponse({"ok": True, "ack": True})
    else:
        await state.broadcast(data)
    return JSONResponse({"ok": True})


@app.post("/api/alert/dismiss")
async def alert_dismiss(request: Request):
    """关闭当前 pending 告警：通知 Pi（让 ack 返回）+ 广播让所有弹窗一起关。

    body 里的 `alert_id`（前端弹窗时记下的）必须匹配当前 pending 告警的 id，
    否则视为"过期 dismiss"——避免旧 dismiss 误关刚换上的新告警。
    body 不带 alert_id（兼容老前端）则按当前 pending 告警关闭。
    """
    global _alert_event, _alert_data
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_id = (body or {}).get("alert_id")

    dismissed_id: str | None = None
    async with _alert_lock:
        cur_id = (_alert_data or {}).get("alert_id")
        if target_id is not None and cur_id is not None and target_id != cur_id:
            # 前端看的还是旧告警，但服务端 pending 的已经是新的 → 拒绝，让 UI 收到新告警再关
            return JSONResponse(
                {"ok": False, "error": "stale_alert_id", "current_id": cur_id},
                status_code=409,
            )
        dismissed_id = cur_id  # 可能为 None（没有 pending）
        _alert_data  = None
        if _alert_event is not None and not _alert_event.is_set():
            _alert_event.set()      # 唤醒还在等的 /api/internal/sensor 协程，让它返回 ack=true

    # 广播带上被关掉的那个 id，前端只关 id 匹配的弹窗
    await state.broadcast({"type": "alert_dismissed", "alert_id": dismissed_id})
    return JSONResponse({"ok": True, "alert_id": dismissed_id})


@app.post("/api/sensor/refresh")
async def post_sensor_refresh():
    """代理到 Pi 上的 sense-u-ble 服务，触发设备立即推送一份完整传感器快照。

    sense-u-ble 跑在 Pi 上的 systemd --user 单元里，监听 :8082。这里通过 pi_host
    转发，让 web UI 的"立即刷新"按钮仍然可用。pi_host 未配置时直接返回 503。
    """
    pi_host = ROOT_CFG.get("pi_host", "").strip()
    if not pi_host:
        return JSONResponse(
            {"ok": False, "error": "pi_host not configured", "ble_connected": False},
            status_code=503,
        )
    pi_port = int(ROOT_CFG.get("ble_port", 8082))
    try:
        req = urllib.request.Request(
            f"http://{pi_host}:{pi_port}/api/sensor/refresh",
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
    with open(_os.path.join(_STATIC_DIR, "playback.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read().replace("__CFG_VER__", _CFG_VER))


@app.get("/api/config/public")
async def get_public_config():
    """暴露给前端的少量只读配置项（避免泄漏密码 / RTSP URL 等敏感字段）。"""
    return JSONResponse({
        "ble_poll_interval_s":   BLE_POLL_INTERVAL_S,
    })


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

    # 跳过正在录制的最新片段：当天 + 最新一个 mp4 + mtime 还在最近 segment_s 内
    # （ffmpeg 还没 close mp4 → 缺 trailer/moov atom，点开会播放失败）
    mp4_files = sorted(f for f in _os.listdir(vid_dir) if f.endswith(".mp4"))
    today_str = _dt.now().strftime("%Y-%m-%d")
    in_progress: set[str] = set()
    if mp4_files and date == today_str:
        last = mp4_files[-1]
        try:
            mtime = _os.path.getmtime(_os.path.join(vid_dir, last))
            if (time.time() - mtime) < SEGMENT_S:
                in_progress.add(last)
        except OSError:
            in_progress.add(last)

    segments = []
    for f in mp4_files:
        if f in in_progress:
            continue
        full = _os.path.join(vid_dir, f)
        # 残缺/截断的 mp4（缺 moov atom）不展示在 timeline，浏览器点了也播不了
        if not is_complete_mp4(full):
            continue
        if f in pts_map:
            # 保留浮点 sub-second 精度：ffmpeg 写的 start_pts_time 通常带几位小数，
            # 截成 int 会让回放时间轴比 Tapo OSD 慢/快 0–999ms。
            ts = float(pts_map[f])
        else:
            try:
                t = _dt.strptime(f"{date} {f[:-4]}", "%Y-%m-%d %H-%M-%S")
                ts = float(t.timestamp())
            except ValueError:
                continue
        segments.append({"file": f, "ts": ts, "url": f"/recordings/{date}/video/{f}"})
    return JSONResponse(segments)


@app.get("/api/recordings/{date}/sensors")
async def get_recording_sensors(date: str):
    """返回指定日期的传感器时序数据（JSON 数组）。"""
    return JSONResponse(sensors_db.get_by_date(date))


if __name__ == "__main__":
    log.info(f"[SERVER] 启动 BabySentinel  http://{WEB_HOST}:{WEB_PORT}")
    log.info(f"[SERVER] 本机访问: http://localhost:{WEB_PORT}")
    uvicorn.run(
        "services.web.server:app",
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="warning",
        reload=False,
    )
