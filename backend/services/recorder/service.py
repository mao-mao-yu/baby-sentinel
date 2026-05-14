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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import os
import shutil
import time
from datetime import date

import httpx

from shared import sensors_db
from shared.config import BASE_DIR, ROOT_CFG, REC_DIR, log
from shared.video_util import is_complete_mp4
from services.recorder.config import (
    SEGMENT_S, BLE_POLL_INTERVAL_S as BLE_POLL_S,
    FFMPEG_PATH, TAPO_RTSP, WEB_PORT,
)
# 残缺 mp4 清理：每 10 分钟扫一遍；mtime 早于这个阈值且无 moov 的视为崩溃残留
CLEANUP_INTERVAL_S      = 600
CLEANUP_AGE_THRESHOLD_S = max(SEGMENT_S * 2, 300)

# ── 工具函数 ──────────────────────────────────────────────────────────

# 持久 HTTP client（连接池 + keep-alive）。
# recorder 每 BLE_POLL_S 秒（默认 2s）GET 一次 /api/sensor；用 urllib.urlopen
# 每次开新 TCP 不 keep-alive → 留下 TIME_WAIT 累积，几小时内能耗光 macOS
# 16k 个 ephemeral port，整个 localhost loopback 通信瘫痪。httpx.Client 自动
# 复用连接，每个 (host, port) 只占一个 TCP，TIME_WAIT 消失。
_http = httpx.Client(timeout=3.0, limits=httpx.Limits(max_keepalive_connections=4))


def _http_get(url: str) -> dict | None:
    try:
        r = _http.get(url)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def _day_dir(d: date | None = None) -> str:
    day  = (d or date.today()).isoformat()
    path = os.path.join(REC_DIR, day)
    os.makedirs(os.path.join(path, "video"), exist_ok=True)
    return path


def _ffmpeg_bin() -> str | None:
    p = (FFMPEG_PATH or "").strip()
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







def _go2rtc_ready() -> bool:
    port = ROOT_CFG.get("go2rtc_port", 1984)
    return _http_get(f"http://127.0.0.1:{port}/api/streams") is not None


async def _terminate_proc(proc: asyncio.subprocess.Process, name: str = "proc",
                          term_timeout: float = 5, kill_timeout: float = 3) -> None:
    """安全终止子进程：先 SIGTERM 等 term_timeout 秒，超时则 SIGKILL。
    确保不会卡死调用方（如跨日切换时 ffmpeg 因 RTSP 阻塞收不到信号）。"""
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=term_timeout)
        return
    except asyncio.TimeoutError:
        log.warning(f"[{name}] {term_timeout}s 内未退出，强制 kill")
    proc.kill()
    try:
        await asyncio.wait_for(proc.wait(), timeout=kill_timeout)
    except asyncio.TimeoutError:
        log.warning(f"[{name}] SIGKILL 后仍未退出（已交由 OS 回收）")


# ── 传感器记录 ────────────────────────────────────────────────────────

async def sensor_record_loop() -> None:
    port = WEB_PORT
    url  = f"http://127.0.0.1:{port}/api/sensor"
    log.info(f"[Sensor] 传感器记录启动 (interval={BLE_POLL_S}s, db=logs/sensors.db)")

    while True:
        await asyncio.sleep(BLE_POLL_S)
        s = _http_get(url)
        if not s or not s.get("ble_ok"):
            continue
        try:
            sensors_db.add_reading(
                breath_rate=s.get("breath_rate"),
                temperature=s.get("temperature"),
                posture=s.get("posture"),
                battery=s.get("battery"),
            )
        except Exception as e:
            log.debug(f"[Sensor] 写入错误: {e}")


# ── 残缺 mp4 清理 ─────────────────────────────────────────────────────

def _cleanup_broken_mp4_once() -> int:
    """扫描 REC_DIR 下所有 YYYY-MM-DD/video/*.mp4，删除"已老 + 缺 moov"的残段。
    "已老" 用 mtime 判断，避开正在录制的当前段。返回删除文件数。"""
    if not os.path.isdir(REC_DIR):
        return 0
    now = time.time()
    deleted = 0
    for d in os.listdir(REC_DIR):
        if len(d) != 10:
            continue
        sub = os.path.join(REC_DIR, d, "video")
        if not os.path.isdir(sub):
            continue
        for f in os.listdir(sub):
            if not f.endswith(".mp4"):
                continue
            path = os.path.join(sub, f)
            try:
                mtime = os.path.getmtime(path)
                if (now - mtime) < CLEANUP_AGE_THRESHOLD_S:
                    continue   # 还很新，可能是当前正在写的段
                if is_complete_mp4(path):
                    continue
                os.remove(path)
                deleted += 1
                log.info(f"[Cleanup] 删除残缺 mp4: {d}/{f}")
            except OSError as e:
                log.debug(f"[Cleanup] {d}/{f} 处理失败: {e}")
    return deleted


async def video_cleanup_loop() -> None:
    log.info(f"[Cleanup] 残缺 mp4 清理循环启动 (每 {CLEANUP_INTERVAL_S}s, age>{CLEANUP_AGE_THRESHOLD_S}s)")
    # 启动后等一小段时间再做第一次扫描，给 ffmpeg 留出从崩溃中恢复的窗口
    await asyncio.sleep(60)
    while True:
        try:
            n = _cleanup_broken_mp4_once()
            if n:
                log.info(f"[Cleanup] 本轮共删 {n} 个残缺片段")
        except Exception as e:
            log.warning(f"[Cleanup] 异常: {type(e).__name__}: {e}")
        await asyncio.sleep(CLEANUP_INTERVAL_S)


# ── 摄像头录像 ────────────────────────────────────────────────────────

# 跨日切换时让新老 ffmpeg 重叠的秒数：新进程拉 RTSP + 写首帧大概 1-2s，
# 给点冗余 3s。重叠期两个进程都在录，零间隔；代价是新一天前几秒帧
# 同时落在前一天最后一段 + 新一天第一段 mp4，可接受。
_DAY_ROLLOVER_OVERLAP_S = 3


async def _spawn_ffmpeg(ffmpeg: str, src: str, day: date,
                        ) -> tuple[asyncio.subprocess.Process, asyncio.Task]:
    """启动一个 ffmpeg 子进程：连续分段写到 `day` 对应的目录 + 该天的 index.csv。
    返回 (proc, drain_task)。drain_task 持续把 stderr 转成 log.warning。"""
    day_dir  = _day_dir(day)
    out_pat  = os.path.join(day_dir, "video", "%H-%M-%S.mp4")
    idx_path = os.path.join(day_dir, "video", "index.csv")
    log.info(f"[Camera] 连续分段录制 → {day_dir}/video/")

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
        "-reset_timestamps", "1",   # 每段 PTS 从 0 开始，避免播放器把累积 PTS 当时长
        "-strftime", "1",
        out_pat,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _drain():
        assert proc.stderr is not None
        async for raw in proc.stderr:
            txt = raw.decode(errors="replace").strip()
            if txt:
                log.warning(f"[Camera] ffmpeg: {txt}")

    drain_task = asyncio.create_task(_drain())
    return proc, drain_task


async def camera_record_loop() -> None:
    rtsp = TAPO_RTSP
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

    proc:       asyncio.subprocess.Process | None = None
    drain_task: asyncio.Task | None                = None
    today:      date | None                        = None

    while True:
        try:
            # 第一次启动 / 上一轮崩溃后重新拉起
            if proc is None:
                today = date.today()
                proc, drain_task = await _spawn_ffmpeg(ffmpeg, src, today)

            # 1s 轮询；尽快发现跨日 + 进程崩溃
            await asyncio.sleep(1)

            # 进程崩溃 → 等 go2rtc 恢复再起一个新的
            if proc.returncode is not None:
                if proc.returncode not in (0, -15):
                    log.warning(f"[Camera] ffmpeg 退出 code={proc.returncode}")
                if drain_task: drain_task.cancel()
                proc = None
                drain_task = None
                await _wait_go2rtc()
                continue

            # 跨日：先 spawn 新进程 → 等 N 秒拿到首帧 → SIGTERM 老进程
            # 重叠期间两个 ffmpeg 同时拉 go2rtc（go2rtc 支持多 consumer），无间隔。
            cur_today = date.today()
            if today is not None and cur_today != today:
                log.info(f"[Camera] 日期变更 {today} → {cur_today}，无缝切换（overlap {_DAY_ROLLOVER_OVERLAP_S}s）")
                new_proc, new_drain = await _spawn_ffmpeg(ffmpeg, src, cur_today)
                # 让新进程把第一段 mp4 写出 moov 的概率更高；老进程此时仍在录今天最后一段
                await asyncio.sleep(_DAY_ROLLOVER_OVERLAP_S)
                old_proc, old_drain = proc, drain_task
                proc, drain_task, today = new_proc, new_drain, cur_today
                # 老进程优雅终止：SIGTERM 让 ffmpeg 写完当前段的 moov atom
                await _terminate_proc(old_proc, name="Camera-prev")
                if old_drain: old_drain.cancel()

        except Exception as e:
            log.warning(f"[Camera] 异常: {type(e).__name__}: {e}")
            if proc:
                await _terminate_proc(proc, name="Camera")
                if drain_task: drain_task.cancel()
                proc = None
                drain_task = None
            await asyncio.sleep(2)


# ── 入口 ─────────────────────────────────────────────────────────────

async def main():
    await asyncio.gather(
        camera_record_loop(),
        sensor_record_loop(),
        video_cleanup_loop(),
    )

if __name__ == "__main__":
    log.info("BabySentinel Recorder Service 启动")
    asyncio.run(main())
