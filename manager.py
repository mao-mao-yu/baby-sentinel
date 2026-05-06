"""BabySentinel 服务管理器

独立进程，负责启动/停止/重启各子服务并提供 Web 管理界面。

启动:
    python manager.py

管理界面:
    http://localhost:9091
"""

import asyncio
import atexit
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
from fastapi.staticfiles import StaticFiles

# ── 配置 ──────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

with open(CONFIG_FILE, encoding="utf-8") as _f:
    CFG = json.load(_f)

MANAGER_PORT = CFG.get("manager_port", 9091)
_GO2RTC_EXE  = "go2rtc.exe" if sys.platform == "win32" else "go2rtc"

# Pi remote agent config (optional — leave empty to skip Pi托管)
_PI_HOST = CFG.get("pi_host", "")
_PI_USER = CFG.get("pi_user", "pi")
_PI_KEY  = os.path.expanduser(CFG.get("pi_ssh_key", "~/.ssh/pi_key"))

import shutil as _shutil
_SSH_BIN = _shutil.which("ssh") or "ssh"

# 子进程组隔离：Unix 用 setsid（new session），Windows 用 CREATE_NEW_PROCESS_GROUP，
# 让 _kill_tree 能干净地把整棵子进程树带走，且 manager 收到 Ctrl+C 不会直接传给子进程
_PROC_GROUP_KW: dict = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if sys.platform == "win32"
    else {"start_new_session": True}
)
_go2rtc_p    = CFG.get("go2rtc_path", "").strip()
if _go2rtc_p:
    GO2RTC_BIN = _go2rtc_p if os.path.isabs(_go2rtc_p) else os.path.join(BASE_DIR, _go2rtc_p)
else:
    GO2RTC_BIN = os.path.join(BASE_DIR, "bin", _GO2RTC_EXE)


def _gen_go2rtc_yaml():
    tapo_url  = CFG.get("tapo_rtsp", "")
    audio_url = CFG.get("pi_audio_rtsp", "").strip()  # rtsp://pi_ip:8554/respeaker
    port      = CFG.get("go2rtc_port", 1984)
    path      = os.path.join(BASE_DIR, "go2rtc.yaml")

    if audio_url:
        # ReSpeaker available: merge TAPO video + Pi audio (video path unchanged, no latency hit)
        stream_entry = (
            f"ffmpeg:-rtsp_transport tcp -i {tapo_url} "
            f"-rtsp_transport tcp -i {audio_url} "
            f"-map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -f rtsp pipe:1"
        )
    else:
        # No Pi audio configured: use TAPO stream as-is (video + TAPO built-in audio)
        stream_entry = tapo_url

    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"streams:\n  baby: {stream_entry}\n\n"
            f"api:\n  listen: :{port}\n  origin: '*'\n"
        )


# ── 服务定义 ──────────────────────────────────────────────────────────

SERVICES: dict[str, dict] = {
    "go2rtc": {
        "name":       "go2rtc",
        "icon":       "📹",
        "desc":       f"摄像头 RTSP → WebRTC   :{CFG.get('go2rtc_port', 1984)}",
        "cmd":        [GO2RTC_BIN, "-config", "go2rtc.yaml"],
        "pre_start":  _gen_go2rtc_yaml,
        "port":       CFG.get("go2rtc_port", 1984),
        # adoptable: manager 重启时不杀 → recorder 的 ffmpeg 不会因 RTSP 断流退出
        "adoptable":  True,
        "script":     "bin/go2rtc",
    },
    "ble": {
        "name":       "BLE Sensor",
        "icon":       "📡",
        "desc":       f"Sense-U 蓝牙传感器   :{CFG.get('ble_port', 8082)}",
        "cmd":        [sys.executable, "-u", "services/ble/service.py"],
        "port":       CFG.get("ble_port", 8082),
    },
    "server": {
        "name":       "BabySentinel Server",
        "icon":       "🍼",
        "desc":       f"Web · 摄像头 · 提醒 · Discord   :{CFG.get('web_port', 8080)}",
        "cmd":        [sys.executable, "-u", "services/web/server.py"],
        "port":       CFG.get("web_port", 8080),
    },
    "recorder": {
        "name":       "Recorder",
        "icon":       "⏺",
        "desc":       "视频录制 · 传感器时序存档",
        "cmd":        [sys.executable, "-u", "services/recorder/service.py"],
        "port":       None,
        # adoptable: manager 启动时若已有同名进程在跑就直接接管而不杀，避免录像中断
        "adoptable":  True,
        "script":     "services/recorder/service.py",
    },
    "voice": {
        "name":       "Voice Service",
        "icon":       "🎙",
        "desc":       f"Whisper STT · MiniMax LLM · TTS   :{CFG.get('voice_service_port', 8001)}",
        "cmd":        [sys.executable, "-u", "services/voice/voice_service.py"],
        "port":       CFG.get("voice_service_port", 8001),
    },
    "voice_agent": {
        "name":       "Voice Agent (Pi)",
        "icon":       "🎤",
        "desc":       f"唤醒词 · 录音 · TTS播放   Pi: {_PI_HOST or '(未配置 pi_host)'}",
        # SSH into Pi if pi_host is set; otherwise fall back to local run
        "cmd":        (
            [_SSH_BIN, "-t", "-i", _PI_KEY,
             "-o", "StrictHostKeyChecking=no",
             "-o", "BatchMode=yes",
             f"{_PI_USER}@{_PI_HOST}",
             "cd ~/BabySentinel && ./venv/bin/python -u agent/voice_agent.py"]
            if _PI_HOST else
            [sys.executable, "-u", "agent/voice_agent.py"]
        ),
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


class _AdoptedProc:
    """被 manager 接管的孤儿进程（不是我们 spawn 的，但仍能 kill / wait）。
    stdout 不可用——孤儿的输出我们读不到，UI 上看不到接管期间的日志。"""

    def __init__(self, pid: int):
        self.pid = pid
        self.returncode: int | None = None
        self.stdout = None  # 让 _drain 路径跳过

    async def wait(self):
        while self.returncode is None:
            try:
                os.kill(self.pid, 0)   # 探活
            except ProcessLookupError:
                self.returncode = 0
                break
            await asyncio.sleep(1)
        return self.returncode

    def kill(self):
        try:
            import signal as _sig
            os.kill(self.pid, _sig.SIGKILL)
        except ProcessLookupError:
            pass
        self.returncode = -9

    def terminate(self):
        try:
            import signal as _sig
            os.kill(self.pid, _sig.SIGTERM)
        except ProcessLookupError:
            pass


def _find_external_proc(svc: str) -> int | None:
    """寻找 cwd 在项目目录、cmdline 含 SERVICES[svc]['script'] 的 PPID=1 进程。
    跳过 manager 自己的子进程；返回 PID 或 None。Windows 暂不支持。"""
    if sys.platform == "win32":
        return None
    script = SERVICES[svc].get("script")
    if not script:
        return None
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", script],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
    except Exception:
        return None
    me = os.getpid()
    base = BASE_DIR.replace("\\", "/").lower()
    managed_pids = {p.pid for p in _procs.values() if p}
    for pid_str in out.split():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == me or pid in managed_pids:
            continue
        if _get_proc_cwd(pid).replace("\\", "/").lower() != base:
            continue
        return pid
    return None


async def _do_start(svc: str):
    # adoptable 服务：启动前先看是否有外部同名进程能接管，避免重启杀掉正在工作的进程
    if SERVICES[svc].get("adoptable") and _procs[svc] is None:
        existing = _find_external_proc(svc)
        if existing is not None:
            _procs[svc]  = _AdoptedProc(existing)
            _starts[svc] = time.time()
            _append_log(svc, f"{'─'*40}")
            _append_log(svc, f"接管已运行的进程 PID {existing}（避免中断）")
            return

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
            **_PROC_GROUP_KW,
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
    """判断 PID 是否属于本软件（已追踪进程、命令行含项目目录、或 cwd 为项目目录）。"""
    for proc in _procs.values():
        if proc and proc.pid == pid:
            return True
    base    = BASE_DIR.replace("\\", "/").lower()
    cmdline = _get_proc_cmdline(pid).replace("\\", "/").lower()
    if cmdline and base in cmdline:
        return True
    return _get_proc_cwd(pid).replace("\\", "/").lower() == base


def _get_proc_cwd(pid: int) -> str:
    """返回进程的当前工作目录，失败时返回空串。"""
    try:
        if sys.platform == "win32":
            # Windows 没有便捷 API；用 wmic 取 ExecutablePath 同目录作近似
            return ""
        out = subprocess.check_output(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        for line in out.splitlines():
            if line.startswith("n"):
                return line[1:].strip()
    except Exception:
        pass
    return ""


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

def _scan_and_kill_orphans() -> None:
    """启动前扫描同项目残留的孤儿子进程并整组干掉（PPID=1, cwd 在项目目录下）。
    adoptable 的服务（如 recorder/service.py）跳过——它们的孤儿留给 _do_start 接管，
    避免杀掉正在录像的进程导致 mp4 文件损坏。"""
    if sys.platform == "win32":
        return

    # 收集 adoptable 服务对应的脚本名，扫描时跳过
    adoptable_scripts = {
        defn.get("script") for defn in SERVICES.values()
        if defn.get("adoptable") and defn.get("script")
    }

    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "services/ble/service.py|services/recorder/service.py|services/web/server.py"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
    except Exception:
        return
    me = os.getpid()
    base = BASE_DIR.replace("\\", "/").lower()
    for pid_str in out.split():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == me:
            continue
        try:
            ppid = int(subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "ppid="],
                text=True, stderr=subprocess.DEVNULL, timeout=3,
            ).strip())
        except Exception:
            continue
        if ppid != 1:
            continue
        if _get_proc_cwd(pid).replace("\\", "/").lower() != base:
            continue
        cmdline = _get_proc_cmdline(pid)
        # adoptable 进程：留给 _do_start 接管
        if any(s in cmdline for s in adoptable_scripts):
            print(f"[manager] 跳过 adoptable 进程 PID {pid}: {cmdline[:80]}（将被接管）")
            continue
        print(f"[manager] 清理孤儿 PID {pid}: {cmdline[:100]}")
        try:
            _kill_tree(pid)
        except Exception:
            pass


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _scan_and_kill_orphans()
    for svc in ("go2rtc", "ble", "server", "recorder"):
        await asyncio.sleep(0.3)
        await _do_start(svc)
    try:
        yield
    finally:
        # adoptable 服务（如 recorder）保留运行——下次 manager 启动时接管，避免录像中断
        for svc in ("recorder", "server", "ble", "go2rtc"):
            if SERVICES[svc].get("adoptable"):
                proc = _procs.get(svc)
                if proc and proc.returncode is None:
                    _append_log(svc, "manager 退出（保留进程供下次接管，录像不中断）")
                continue
            try:
                await _do_stop(svc)
            except Exception as e:
                _append_log(svc, f"[shutdown] {e}")


def _cleanup_at_exit():
    """兜底：lifespan 未执行（异常退出 / debugger 强停）时同步清理子进程组。
    adoptable 服务跳过——让录像 ffmpeg 留下，下次 manager 启动接管。"""
    for svc, proc in _procs.items():
        if SERVICES[svc].get("adoptable"):
            continue
        if proc and proc.returncode is None:
            try:
                _kill_tree(proc.pid)
            except Exception:
                pass


atexit.register(_cleanup_at_exit)


app = FastAPI(title="BabySentinel Manager", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "services", "web", "static")), name="static")

# 静态资源版本号——manager 启动时一次确定，强制浏览器跳过旧 cache
_CFG_VER = str(int(time.time()))


@app.get("/")
async def index():
    with open(os.path.join(BASE_DIR, "services", "web", "static", "manager.html"), encoding="utf-8") as f:
        html = (f.read()
                .replace("__WEB_PORT__", str(CFG.get("web_port", 8080)))
                .replace("__CFG_VER__", _CFG_VER))
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
