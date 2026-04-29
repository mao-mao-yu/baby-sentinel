"""
Baby Cry Detector — 独立进程，通过 stdout 输出 JSON 告警
需要 Python 3.11 + tensorflow + tensorflow-hub + numpy

启动方式（由 server.py 自动调用，也可单独测试）:
  Windows: venv\Scripts\python.exe cry_detector.py <rtsp_url> [INFO|DEBUG] [ffmpeg_path]
  macOS:   ./venv/bin/python cry_detector.py <rtsp_url> [INFO|DEBUG] [ffmpeg_path]

stdout: 每行一个 JSON  {"type": "cry", "confidence": 0.87}
stderr: 日志输出
"""

import json
import logging
import os
import sys
import time
import subprocess
import numpy as np

# ── 屏蔽 TensorFlow / oneDNN 噪音 ────────────────────────────────────
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")      # 屏蔽 C++ INFO/WARNING
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")     # 关闭 oneDNN 提示
os.environ.setdefault("ABSL_MIN_LOG_LEVEL", "2")         # 屏蔽 absl INFO

# ── 日志初始化 ────────────────────────────────────────────────────────
_level_arg = sys.argv[2].upper() if len(sys.argv) > 2 else "INFO"
logging.basicConfig(
    level=getattr(logging, _level_arg, logging.INFO),
    format="%(asctime)s [%(levelname)-5s] [CryDet] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("cry_detector")

# 屏蔽 tensorflow / tensorflow_hub Python WARNING（deprecation 等）
logging.getLogger("tensorflow").setLevel(logging.ERROR)
logging.getLogger("tensorflow_hub").setLevel(logging.ERROR)
logging.getLogger("absl").setLevel(logging.ERROR)

# ── 参数 ──────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000
YAMNET_WINDOW  = 0.96
CHUNK_SEC      = 0.10
CHUNK_SAMPLES  = int(SAMPLE_RATE * YAMNET_WINDOW)
STEP_SAMPLES   = int(SAMPLE_RATE * CHUNK_SEC)
CRY_CLASS      = 40            # AudioSet class 40 = "Baby cry, infant cry"
CRY_THRESHOLD  = 0.30
CONFIRM_CHUNKS = 3
COOLDOWN_SEC   = 60
SILENCE_RMS    = 0.005
STATUS_INTERVAL = 30           # 每 30 秒打印一次心跳（INFO 级别）

# ── 加载 YAMNet ───────────────────────────────────────────────────────
def load_yamnet():
    import tensorflow_hub as hub
    log.info("加载 YAMNet 模型...")
    model = hub.load("https://tfhub.dev/google/yamnet/1")
    log.info("模型加载完成")
    return model

# ── 音频读取（ffmpeg pipe）────────────────────────────────────────────
def _find_ffmpeg() -> str:
    import shutil
    if len(sys.argv) > 3 and sys.argv[3]:
        return sys.argv[3]
    return shutil.which("ffmpeg") or "ffmpeg"

def open_audio_pipe(rtsp_url: str):
    ffmpeg = _find_ffmpeg()
    log.debug(f"ffmpeg: {ffmpeg}")
    cmd = [
        ffmpeg, "-y",
        "-i", rtsp_url,
        "-vn",
        "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "pipe:1",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

# ── 主检测循环 ────────────────────────────────────────────────────────
def run(rtsp_url: str):
    model = load_yamnet()
    step_bytes = STEP_SAMPLES * 2   # int16 = 2 bytes

    confirm_count = 0
    last_alert    = 0.0
    ring_buf      = np.zeros(CHUNK_SAMPLES, dtype=np.float32)

    while True:
        log.info("连接 RTSP...")
        proc = None
        try:
            proc = open_audio_pipe(rtsp_url)
            log.info("音频流就绪，开始检测")

            chunk_count  = 0
            last_status  = time.time()
            last_rms     = 0.0
            last_score   = 0.0

            while True:
                raw = proc.stdout.read(step_bytes)
                if not raw or len(raw) < step_bytes:
                    break

                step = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                ring_buf = np.roll(ring_buf, -STEP_SAMPLES)
                ring_buf[-STEP_SAMPLES:] = step

                rms = float(np.sqrt(np.mean(ring_buf ** 2)))
                last_rms = rms

                if rms < SILENCE_RMS:
                    confirm_count = max(0, confirm_count - 1)
                    log.debug(f"静音跳过 rms={rms:.4f}")
                else:
                    _t0 = time.perf_counter()
                    scores, _, _ = model(ring_buf)
                    _infer_ms = (time.perf_counter() - _t0) * 1000
                    cry_score = float(scores.numpy().mean(axis=0)[CRY_CLASS])
                    last_score = cry_score
                    chunk_count += 1
                    # 前 5 次推理打印耗时，之后只在 DEBUG 下输出
                    if chunk_count <= 5:
                        log.info(f"推理耗时 {_infer_ms:.1f}ms  cry_score={cry_score:.3f}")
                    else:
                        log.debug(f"推理耗时 {_infer_ms:.1f}ms")

                    if cry_score >= CRY_THRESHOLD:
                        confirm_count += 1
                    else:
                        confirm_count = max(0, confirm_count - 1)

                    log.debug(
                        f"rms={rms:.4f}  cry_score={cry_score:.3f}"
                        f"  confirm={confirm_count}/{CONFIRM_CHUNKS}"
                    )

                    if confirm_count >= CONFIRM_CHUNKS:
                        now = time.time()
                        if now - last_alert >= COOLDOWN_SEC:
                            last_alert    = now
                            confirm_count = 0
                            log.info(f"检测到哭声！置信度={cry_score:.0%}")
                            print(
                                json.dumps({"type": "cry", "confidence": round(cry_score, 3)}),
                                flush=True,
                            )

                # 心跳状态：每 STATUS_INTERVAL 秒打印一次
                now = time.time()
                if now - last_status >= STATUS_INTERVAL:
                    log.info(
                        f"检测中... chunks={chunk_count}"
                        f"  rms={last_rms:.4f}  cry_score={last_score:.3f}"
                    )
                    last_status = now

        except Exception as e:
            log.error(f"错误: {e}")
        finally:
            if proc:
                proc.terminate()

        confirm_count = 0
        log.debug("3 秒后重连...")
        time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        log.error("用法: cry_detector.py <rtsp_url> [INFO|DEBUG] [ffmpeg_path]")
        sys.exit(1)
    run(sys.argv[1])
