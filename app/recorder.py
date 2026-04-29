"""BabySentinel 录像与传感器记录模块

文件布局（面向未来回放）:
  recordings/
    YYYY-MM-DD/
      video/
        HH-MM-SS.mp4          视频分段，文件名即开始时间
        index.jsonl           每段索引: {ts, end_ts, file, duration}
      sensors.jsonl           传感器时序: {ts, time, ...fields}

回放时:
  1. 按 index.jsonl 定位视频段
  2. 按 ts 在 sensors.jsonl 中二分查找对应传感器快照
  3. 两者均以 Unix 时间戳对齐，无需额外映射
"""

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, date

from app.config import AUDIO_BITRATE, CFG, REC_DIR, log
from app.state import sensor_state

SEGMENT_S      = CFG.get("segment_s", 180)
SENSOR_INTVL_S = CFG.get("sensor_interval_s", 5)


def _day_dir(d: date | None = None) -> str:
    day  = (d or date.today()).isoformat()
    path = os.path.join(REC_DIR, day)
    os.makedirs(os.path.join(path, "video"), exist_ok=True)
    return path


def _ffmpeg() -> str | None:
    p = CFG.get("ffmpeg_path", "").strip()
    if p and os.path.exists(p):
        return p
    return shutil.which("ffmpeg")


async def camera_record_loop() -> None:
    """持续录制摄像头，每 SEGMENT_S 秒切一个 MP4 文件。"""
    rtsp = CFG.get("tapo_rtsp", "")
    if "YOUR_PASSWORD" in rtsp:
        log.warning("[Recorder] tapo_rtsp 未配置，跳过摄像头录像")
        return

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        log.warning("[Recorder] 未找到 ffmpeg，跳过摄像头录像")
        return

    log.info(f"[Recorder] ffmpeg: {ffmpeg}")

    # 等待 go2rtc 就绪（cam_ok 由 camera.py 设置）
    from app.state import sensor_state as _ss
    log.info("[Recorder] 等待摄像头就绪...")
    while not _ss.get("cam_ok"):
        await asyncio.sleep(2)
    log.info("[Recorder] 摄像头就绪，开始录像")

    # 使用 go2rtc 本地 RTSP 中转，避免与 WebRTC 推流竞争摄像头连接
    src = "rtsp://127.0.0.1:8554/baby"

    while True:
        today   = date.today()
        day_dir = _day_dir(today)
        # %H-%M-%S 由 ffmpeg strftime 填充，ffmpeg 内部无缝切片，无重连间隔
        out_pat = os.path.join(day_dir, "video", "%H-%M-%S.mp4")
        log.info(f"[Recorder] 连续分段录制 → {day_dir}/video/")

        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-loglevel", "warning",
                "-rtsp_transport", "tcp",
                "-i", src,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-f", "segment",
                "-segment_time", str(SEGMENT_S),
                "-segment_format", "mp4",
                "-reset_timestamps", "1",
                "-strftime", "1",
                out_pat,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _log_stderr():
                async for raw in proc.stderr:
                    txt = raw.decode(errors="replace").strip()
                    if txt:
                        log.warning(f"[Recorder] ffmpeg: {txt}")

            stderr_task = asyncio.create_task(_log_stderr())

            # 每 10 秒检查一次：日期变更则重启（切换到新日期目录）
            while proc.returncode is None:
                await asyncio.sleep(10)
                if date.today() != today:
                    log.info("[Recorder] 日期变更，重启录像至新日期目录")
                    proc.terminate()
                    await proc.wait()
                    break

            stderr_task.cancel()

            if proc.returncode not in (0, None, -15):
                log.warning(f"[Recorder] ffmpeg 退出 returncode={proc.returncode}")

        except Exception as e:
            log.warning(f"[Recorder] 录像异常: {type(e).__name__}: {e}")

        # 摄像头离线则等待恢复
        if not _ss.get("cam_ok"):
            log.info("[Recorder] 摄像头离线，等待恢复...")
            while not _ss.get("cam_ok"):
                await asyncio.sleep(2)
            log.info("[Recorder] 摄像头恢复，重启录像")
        else:
            await asyncio.sleep(1)


async def sensor_record_loop() -> None:
    """BLE 在线时每 SENSOR_INTVL_S 秒将传感器快照追加到当日 sensors.jsonl。"""
    log.info("[Recorder] 传感器记录循环启动")

    while True:
        await asyncio.sleep(SENSOR_INTVL_S)

        if not sensor_state.get("ble_ok"):
            continue

        try:
            day_dir = _day_dir()
            path    = os.path.join(day_dir, "sensors.jsonl")
            entry   = {
                "ts":          int(time.time()),
                "time":        datetime.now().strftime("%H:%M:%S"),
                "breath_rate": sensor_state.get("breath_rate"),
                "temperature": sensor_state.get("temperature"),
                "humidity":    sensor_state.get("humidity"),
                "posture":     sensor_state.get("posture"),
                "battery":     sensor_state.get("battery"),
                "is_wearing":  sensor_state.get("is_wearing"),
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            log.debug(f"[Recorder] 传感器记录错误: {e}")
