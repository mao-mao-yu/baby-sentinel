"""BabySentinel 录像独立服务

与主服务 (server.py) 完全解耦，分别启动/重启互不影响。

依赖关系:
  - 视频: ffmpeg → go2rtc RTSP (rtsp://127.0.0.1:8554/baby)
  - 传感器: HTTP 轮询主服务 GET /api/sensor

启动方式:
  python recorder_service.py

主服务重启时:
  - 视频录制: go2rtc 随主服务重启会有短暂中断，ffmpeg 自动重连恢复
  - 传感器记录: 轮询失败时跳过该轮，主服务恢复后自动继续
"""

import asyncio
import json
import os
import shutil
import time
import urllib.request
from datetime import date, datetime

from app.config import BASE_DIR, CFG, REC_DIR, log

# ── 配置 ──────────────────────────────────────────────────────────────

SEGMENT_S      = CFG.get("segment_s", 180)
SENSOR_INTVL_S = CFG.get("sensor_interval_s", 5)

# ── 工具函数 ──────────────────────────────────────────────────────────

def _day_dir(d: date | None = None) -> str:
    day  = (d or date.today()).isoformat()
    path = os.path.join(REC_DIR, day)
    os.makedirs(os.path.join(path, "video"), exist_ok=True)
    return path


def _ffmpeg_bin() -> str | None:
    p = CFG.get("ffmpeg_path", "").strip()
    if p:
        full = p if os.path.isabs(p) else os.path.join(BASE_DIR, p)
        if os.path.exists(full):
            return full
    # auto-detect in project bin/
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = os.path.join(BASE_DIR, "bin", name)
        if os.path.exists(candidate):
            return candidate
    return shutil.which("ffmpeg")


def _http_get(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _go2rtc_ready() -> bool:
    port = CFG.get("go2rtc_port", 1984)
    return _http_get(f"http://127.0.0.1:{port}/api/streams") is not None


# ── 传感器记录 ────────────────────────────────────────────────────────

async def sensor_record_loop() -> None:
    port = CFG.get("web_port", 8080)
    url  = f"http://127.0.0.1:{port}/api/sensor"
    log.info("[Sensor] 传感器记录启动")

    while True:
        await asyncio.sleep(SENSOR_INTVL_S)
        s = _http_get(url)
        if not s or not s.get("ble_ok"):
            continue
        try:
            path = os.path.join(_day_dir(), "sensors.jsonl")
            entry = {
                "ts":          int(time.time()),
                "time":        datetime.now().strftime("%H:%M:%S"),
                "breath_rate": s.get("breath_rate"),
                "temperature": s.get("temperature"),
                "humidity":    s.get("humidity"),
                "posture":     s.get("posture"),
                "battery":     s.get("battery"),
                "is_wearing":  s.get("is_wearing"),
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            log.debug(f"[Sensor] 写入错误: {e}")


# ── 摄像头录像 ────────────────────────────────────────────────────────

async def camera_record_loop() -> None:
    rtsp = CFG.get("tapo_rtsp", "")
    if "YOUR_PASSWORD" in rtsp:
        log.warning("[Camera] tapo_rtsp 未配置，跳过录像")
        return

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        log.warning("[Camera] 未找到 ffmpeg，跳过录像")
        return

    log.info(f"[Camera] ffmpeg: {ffmpeg}")
    src = "rtsp://127.0.0.1:8554/baby"

    async def _wait_go2rtc():
        log.info("[Camera] 等待 go2rtc 就绪...")
        while not _go2rtc_ready():
            await asyncio.sleep(3)
        log.info("[Camera] go2rtc 就绪")

    await _wait_go2rtc()

    while True:
        today   = date.today()
        day_dir = _day_dir(today)
        out_pat  = os.path.join(day_dir, "video", "%H-%M-%S.mp4")
        idx_path = os.path.join(day_dir, "video", "index.csv")
        log.info(f"[Camera] 连续分段录制 → {day_dir}/video/")

        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-loglevel", "error",
                "-fflags", "+genpts",
                "-rtsp_transport", "tcp",
                "-i", src,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "32k",
                "-f", "segment",
                "-segment_time", str(SEGMENT_S),
                "-segment_format", "mp4",
                "-segment_list", idx_path,
                "-segment_list_type", "csv",
                "-segment_list_flags", "+cache",
                "-strftime", "1",
                out_pat,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _drain():
                async for raw in proc.stderr:
                    txt = raw.decode(errors="replace").strip()
                    if txt:
                        log.warning(f"[Camera] ffmpeg: {txt}")

            drain_task = asyncio.create_task(_drain())

            while proc.returncode is None:
                await asyncio.sleep(10)
                if date.today() != today:
                    log.info("[Camera] 日期变更，重启录像至新目录")
                    proc.terminate()
                    await proc.wait()
                    break

            drain_task.cancel()

            if proc.returncode not in (0, None, -15):
                log.warning(f"[Camera] ffmpeg 退出 code={proc.returncode}")

        except Exception as e:
            log.warning(f"[Camera] 异常: {type(e).__name__}: {e}")

        # go2rtc 可能随主服务重启了，等它恢复
        await _wait_go2rtc()
        await asyncio.sleep(1)


# ── 入口 ─────────────────────────────────────────────────────────────

async def main():
    await asyncio.gather(
        camera_record_loop(),
        sensor_record_loop(),
    )

if __name__ == "__main__":
    log.info("BabySentinel Recorder Service 启动")
    asyncio.run(main())
