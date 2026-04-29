import asyncio
import json
import os
import sys
import urllib.request

import app.state as state
from app.config import BASE_DIR, CFG, log
from app.alerts import trigger_alert

# ── go2rtc 配置生成 ───────────────────────────────────────────────────

def _write_go2rtc_yaml(rtsp_url: str, port: int) -> str:
    path = os.path.join(BASE_DIR, "go2rtc.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"streams:\n  baby: {rtsp_url}\n\n"
            f"api:\n  listen: :{port}\n  origin: '*'\n"
        )
    return path


async def _check_go2rtc(port: int) -> bool:
    loop = asyncio.get_event_loop()
    def _req():
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/streams", timeout=2)
        return True
    try:
        return await loop.run_in_executor(None, _req)
    except Exception:
        return False

# ── go2rtc 进程循环 ───────────────────────────────────────────────────

async def rtsp_loop() -> None:
    url  = CFG["tapo_rtsp"]
    port = CFG["go2rtc_port"]
    if "YOUR_PASSWORD" in url:
        log.warning("[go2rtc] config.json 中 tapo_rtsp 未配置，跳过视频流")
        return

    _exe = "go2rtc.exe" if sys.platform == "win32" else "go2rtc"
    go2rtc_bin = os.path.join(BASE_DIR, "bin", _exe)
    if not os.path.exists(go2rtc_bin):
        log.error(f"[go2rtc] 未找到 bin/{_exe}")
        return

    cfg_path = _write_go2rtc_yaml(url, port)

    while True:
        already_running = await _check_go2rtc(port)
        if already_running:
            log.info("[go2rtc] 已由外部启动，仅监控状态")
        elif os.path.exists(go2rtc_bin):
            log.info("[go2rtc] 启动...")
            state.sensor_state["cam_ok"] = False
            await state.broadcast({"type": "sensor", **state.sensor_state})
            try:
                state.rtsp_proc = await asyncio.create_subprocess_exec(
                    go2rtc_bin, "-config", cfg_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.sleep(2)
            except Exception as e:
                log.warning(f"[go2rtc] 启动失败: {e}")
                await asyncio.sleep(3)
                continue
        else:
            log.error(f"[go2rtc] 未找到 bin/{_exe}")
            await asyncio.sleep(10)
            continue

        # 健康监控循环（无论是自启还是外部启动）
        while True:
            if state.rtsp_proc and state.rtsp_proc.returncode is not None:
                break  # 自启进程已退出
            ok = await _check_go2rtc(port)
            if ok and not state.sensor_state["cam_ok"]:
                state.sensor_state["cam_ok"] = True
                await state.broadcast({"type": "sensor", **state.sensor_state})
                log.info(f"[go2rtc] 就绪  WebRTC → http://localhost:{port}")
            elif not ok and state.sensor_state["cam_ok"]:
                state.sensor_state["cam_ok"] = False
                await state.broadcast({"type": "sensor", **state.sensor_state})
                if already_running:
                    break  # 外部进程消失，退出监控等待重新出现
            await asyncio.sleep(3)

        state.sensor_state["cam_ok"] = False
        await state.broadcast({"type": "sensor", **state.sensor_state})
        state.rtsp_proc = None
        log.debug("[go2rtc] 3 秒后重试...")
        await asyncio.sleep(3)

# ── 哭声检测子进程循环 ────────────────────────────────────────────────

async def cry_loop() -> None:
    if "YOUR_PASSWORD" in CFG["tapo_rtsp"]:
        return

    url      = "rtsp://127.0.0.1:8554/baby"
    cry_dir  = os.path.join(BASE_DIR, "cry_detector")
    detector = os.path.join(cry_dir, "cry_detector.py")
    if not os.path.exists(detector):
        log.error("[Cry] 未找到 cry_detector/cry_detector.py")
        return

    venv_py = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
    python  = venv_py if os.path.exists(venv_py) else sys.executable
    ffmpeg  = CFG.get("ffmpeg_path", "")

    while True:
        log.info(f"[Cry] 启动检测器: {python}")
        try:
            proc = await asyncio.create_subprocess_exec(
                python, detector, url, CFG.get("log_level", "INFO"), ffmpeg,
                stdout=asyncio.subprocess.PIPE,
                stderr=None,
            )
            while proc.returncode is None:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode())
                    if msg.get("type") == "cry":
                        conf = msg.get("confidence", 0)
                        await trigger_alert(
                            f"👶 检测到婴儿哭声！(置信度 {conf:.0%})", "danger"
                        )
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[Cry] 错误: {e}")

        log.debug("[Cry] 5 秒后重启...")
        await asyncio.sleep(5)
