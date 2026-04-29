"""BabySentinel 服务管理器

独立进程，负责启动/停止/重启各子服务并提供 Web 管理界面。

启动:
    python manager.py

管理界面:
    http://localhost:9091
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# ── 配置 ──────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

with open(CONFIG_FILE, encoding="utf-8") as _f:
    CFG = json.load(_f)

MANAGER_PORT = CFG.get("manager_port", 9091)
_GO2RTC_EXE  = "go2rtc.exe" if sys.platform == "win32" else "go2rtc"
GO2RTC_BIN   = os.path.join(BASE_DIR, "bin", _GO2RTC_EXE)


def _gen_go2rtc_yaml():
    url  = CFG.get("tapo_rtsp", "")
    port = CFG.get("go2rtc_port", 1984)
    path = os.path.join(BASE_DIR, "go2rtc.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"streams:\n  baby: {url}\n\napi:\n  listen: :{port}\n  origin: '*'\n")


# ── 服务定义 ──────────────────────────────────────────────────────────

SERVICES: dict[str, dict] = {
    "go2rtc": {
        "name":       "go2rtc",
        "icon":       "📹",
        "desc":       f"摄像头 RTSP → WebRTC   :{CFG.get('go2rtc_port', 1984)}",
        "cmd":        [GO2RTC_BIN, "-config", "go2rtc.yaml"],
        "pre_start":  _gen_go2rtc_yaml,
        "port":       CFG.get("go2rtc_port", 1984),
    },
    "ble": {
        "name":       "BLE Sensor",
        "icon":       "📡",
        "desc":       f"Sense-U 蓝牙传感器   :{CFG.get('ble_port', 8082)}",
        "cmd":        [sys.executable, "-u", "ble_service.py"],
        "port":       CFG.get("ble_port", 8082),
    },
    "server": {
        "name":       "BabySentinel Server",
        "icon":       "🍼",
        "desc":       f"Web · 摄像头 · 提醒 · Discord   :{CFG.get('web_port', 8080)}",
        "cmd":        [sys.executable, "-u", "server.py"],
        "port":       CFG.get("web_port", 8080),
    },
    "recorder": {
        "name":       "Recorder",
        "icon":       "⏺",
        "desc":       "视频录制 · 传感器时序存档",
        "cmd":        [sys.executable, "-u", "recorder_service.py"],
        "port":       None,
    },
}

# ── 运行时状态 ────────────────────────────────────────────────────────

_procs:   dict[str, asyncio.subprocess.Process | None] = {k: None for k in SERVICES}
_logs:    dict[str, deque]                             = {k: deque(maxlen=400) for k in SERVICES}
_starts:  dict[str, float | None]                     = {k: None for k in SERVICES}


def _append_log(svc: str, line: str):
    ts = datetime.now().strftime("%H:%M:%S")
    _logs[svc].append(f"{ts}  {line}")


def _svc_status(svc: str) -> dict:
    proc = _procs[svc]
    if proc is None:
        st = "stopped"
    elif proc.returncode is None:
        st = "running"
    else:
        st = f"crashed"
    t = _starts[svc]
    return {
        "status":     st,
        "returncode": proc.returncode if proc else None,
        "pid":        proc.pid if proc and proc.returncode is None else None,
        "started_at": datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else None,
    }


async def _drain(svc: str, pipe):
    try:
        async for raw in pipe:
            line = raw.decode(errors="replace").rstrip()
            if line:
                _append_log(svc, line)
    except Exception:
        pass


async def _do_start(svc: str):
    await _do_stop(svc)

    # ── 端口自检 ──────────────────────────────────────────────────
    port = SERVICES[svc].get("port")
    if port:
        pid = _get_port_pid(port)
        if pid is not None:
            if _pid_is_ours(pid):
                _append_log(svc, f"[自检] 端口 {port} 被本软件残留进程占用 (PID {pid})，正在清理...")
                _kill_tree(pid)
                await asyncio.sleep(1.5)
                if _get_port_pid(port) is not None:
                    _append_log(svc, f"[错误] 清理后端口 {port} 仍被占用，启动中止")
                    return
                _append_log(svc, "[自检] 端口已释放，继续启动")
            else:
                cmdline = _get_proc_cmdline(pid) or "未知程序"
                _append_log(svc, f"[错误] 端口 {port} 被第三方程序占用")
                _append_log(svc, f"       PID {pid}: {cmdline[:80]}")
                _append_log(svc, f"       请手动关闭该程序后重试")
                return

    defn = SERVICES[svc]
    pre  = defn.get("pre_start")
    if pre:
        try:
            pre()
        except Exception as e:
            _append_log(svc, f"[pre_start] {e}")

    cmd = defn["cmd"]
    if not os.path.exists(cmd[0]) and cmd[0] != sys.executable:
        _append_log(svc, f"[错误] 找不到可执行文件: {cmd[0]}")
        return

    _append_log(svc, f"{'─'*40}")
    _append_log(svc, f"启动: {' '.join(os.path.basename(c) for c in cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=BASE_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,   # 新进程组，killpg 可以整树杀死
        )
        _procs[svc]  = proc
        _starts[svc] = time.time()
        asyncio.create_task(_drain(svc, proc.stdout))
    except Exception as e:
        _append_log(svc, f"[启动失败] {e}")


def _get_port_pid(port: int) -> int | None:
    """返回正在监听指定 TCP 端口的进程 PID，找不到则返回 None。"""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["netstat", "-ano"], text=True,
                stderr=subprocess.DEVNULL, timeout=5,
            )
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 5 and parts[3] == "LISTENING":
                    if parts[1].rsplit(":", 1)[-1] == str(port):
                        return int(parts[4])
        else:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}"],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            )
            pids = [p for p in out.strip().split() if p.isdigit()]
            if pids:
                return int(pids[0])
    except Exception:
        pass
    return None


def _get_proc_cmdline(pid: int) -> str:
    """返回进程命令行字符串，失败时返回空串。"""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["wmic", "process", "where", f"ProcessId={pid}",
                 "get", "CommandLine", "/value"],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            )
            for line in out.splitlines():
                if line.startswith("CommandLine="):
                    return line[12:].strip()
        else:
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            )
            return out.strip()
    except Exception:
        pass
    return ""


def _pid_is_ours(pid: int) -> bool:
    """判断 PID 是否属于本软件（已追踪进程，或命令行包含项目目录）。"""
    for proc in _procs.values():
        if proc and proc.pid == pid:
            return True
    cmdline = _get_proc_cmdline(pid).replace("\\", "/").lower()
    base    = BASE_DIR.replace("\\", "/").lower()
    return bool(cmdline) and base in cmdline


def _kill_tree(pid: int):
    """杀掉整个进程树（含 ffmpeg 等子进程），跨平台。"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        pass


async def _do_stop(svc: str):
    proc = _procs[svc]
    if proc and proc.returncode is None:
        _append_log(svc, "停止中...")
        _kill_tree(proc.pid)
        try:
            await asyncio.wait_for(proc.wait(), timeout=6)
        except asyncio.TimeoutError:
            proc.kill()
        _append_log(svc, f"已停止 (code={proc.returncode})")
    _procs[svc]  = None
    _starts[svc] = None


# ── FastAPI ───────────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(_: FastAPI):
    for svc in ("go2rtc", "ble", "server", "recorder"):
        await asyncio.sleep(0.3)
        await _do_start(svc)
    yield


app = FastAPI(title="BabySentinel Manager", lifespan=_lifespan)


@app.get("/")
async def index():
    with open(os.path.join(BASE_DIR, "static", "manager.html"), encoding="utf-8") as f:
        html = f.read().replace("__WEB_PORT__", str(CFG.get("web_port", 8080)))
    return HTMLResponse(html)


@app.get("/api/manager/status")
async def get_status():
    return JSONResponse({
        svc: {
            **_svc_status(svc),
            "logs": list(_logs[svc])[-80:],
            "name": SERVICES[svc]["name"],
            "icon": SERVICES[svc]["icon"],
            "desc": SERVICES[svc]["desc"],
        }
        for svc in SERVICES
    })


@app.post("/api/manager/{svc}/start")
async def start_svc(svc: str):
    if svc not in SERVICES:
        return JSONResponse({"ok": False, "error": "unknown service"}, status_code=404)
    asyncio.create_task(_do_start(svc))
    return JSONResponse({"ok": True})


@app.post("/api/manager/{svc}/stop")
async def stop_svc(svc: str):
    if svc not in SERVICES:
        return JSONResponse({"ok": False, "error": "unknown service"}, status_code=404)
    asyncio.create_task(_do_stop(svc))
    return JSONResponse({"ok": True})


@app.post("/api/manager/{svc}/restart")
async def restart_svc(svc: str):
    if svc not in SERVICES:
        return JSONResponse({"ok": False, "error": "unknown service"}, status_code=404)
    asyncio.create_task(_do_start(svc))
    return JSONResponse({"ok": True})



# ── 入口 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"BabySentinel Manager  →  http://localhost:{MANAGER_PORT}")
    uvicorn.run(
        "manager:app",
        host="0.0.0.0",
        port=MANAGER_PORT,
        log_level="warning",
        reload=False,
    )
