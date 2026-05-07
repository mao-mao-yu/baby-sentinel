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
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── 配置 ──────────────────────────────────────────────────────────────

from shared.config import ROOT_CFG, BASE_DIR

MANAGER_PORT = ROOT_CFG.get("manager_port", 9091)
_GO2RTC_EXE  = "go2rtc.exe" if sys.platform == "win32" else "go2rtc"

# Pi remote (BLE 现在跑在 Pi 上的 sense-u-ble 服务里)
_PI_HOST = ROOT_CFG.get("pi_host", "")
_PI_USER = ROOT_CFG.get("pi_ssh_user", "pi")
_PI_KEY  = os.path.expanduser(ROOT_CFG.get("pi_ssh_key", "~/.ssh/id_rsa"))

import shutil as _shutil
_SSH_BIN = _shutil.which("ssh") or "ssh"

# 子进程组隔离：Unix 用 setsid（new session），Windows 用 CREATE_NEW_PROCESS_GROUP，
# 让 _kill_tree 能干净地把整棵子进程树带走，且 manager 收到 Ctrl+C 不会直接传给子进程
_PROC_GROUP_KW: dict = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if sys.platform == "win32"
    else {"start_new_session": True}
)
_go2rtc_p    = ROOT_CFG.get("go2rtc_path", "").strip()
if _go2rtc_p:
    GO2RTC_BIN = _go2rtc_p if os.path.isabs(_go2rtc_p) else os.path.join(BASE_DIR, _go2rtc_p)
else:
    GO2RTC_BIN = os.path.join(BASE_DIR, "bin", _GO2RTC_EXE)


# ── 远端 SSH 帮手（用于 BLE 跑在 Pi 上） ──────────────────────────────

def _ssh_args(remote: dict) -> list[str]:
    """构造 ssh 通用参数：BatchMode + StrictHostKey accept-new + 短超时。"""
    return [
        _SSH_BIN, "-i", remote["key"],
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=20",
        "-o", "ServerAliveCountMax=3",
        f"{remote['user']}@{remote['host']}",
    ]


async def _ssh_run(remote: dict, cmd: str, timeout: float = 15) -> tuple[int, str]:
    """ssh + 执行命令 → (exit_code, stdout+stderr)。失败/超时不抛异常。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *_ssh_args(remote), cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as e:
        return -1, f"[ssh spawn fail] {e}"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "[ssh timeout]"
    return proc.returncode or 0, out.decode(errors="replace")


def _gen_go2rtc_yaml():
    # 每次重新读 config.json，让 pi_audio_rtsp 等运行时改动无需 restart manager。
    # ROOT_CFG 是 import 期 cache 的，pre_start 这里走 disk 读最新值。
    cfg_path = os.path.join(BASE_DIR, "config.json")
    try:
        import json as _json
        with open(cfg_path, encoding="utf-8") as f:
            cfg = _json.load(f)
    except Exception:
        cfg = ROOT_CFG  # 兜底：disk 读失败回退到 cache

    tapo_url  = cfg.get("tapo_rtsp", "")
    audio_url = cfg.get("pi_audio_rtsp", "").strip()  # rtsp://pi_host:8554/respeaker
    port      = cfg.get("go2rtc_port", 1984)
    path      = os.path.join(BASE_DIR, "go2rtc.yaml")

    if audio_url:
        # 多源轨道路由：go2rtc 把两个 RTSP 源直接合成一条流，不经 ffmpeg 转码 ——
        # 比之前 `ffmpeg -map ... -f rtsp pipe:1` 的方案少一个 ffmpeg 进程 +
        # 少一次 pipe 缓冲，能省 ~50-150ms。
        # #media=video / #media=audio 在源头丢掉不需要的轨道。
        body = (
            "streams:\n"
            "  baby:\n"
            f"    - {tapo_url}#media=video\n"
            f"    - {audio_url}#media=audio\n"
        )
    else:
        # 未配置 Pi 音频：直接用 Tapo（视频 + Tapo 自带麦克风音频）
        body = f"streams:\n  baby: {tapo_url}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{body}\napi:\n  listen: :{port}\n  origin: '*'\n")


# ── 服务定义 ──────────────────────────────────────────────────────────

SERVICES: dict[str, dict] = {
    "go2rtc": {
        "name":       "go2rtc",
        "icon":       "📹",
        "desc":       f"摄像头 RTSP → WebRTC   :{ROOT_CFG.get('go2rtc_port', 1984)}",
        "cmd":        [GO2RTC_BIN, "-config", "go2rtc.yaml"],
        "pre_start":  _gen_go2rtc_yaml,
        "port":       ROOT_CFG.get("go2rtc_port", 1984),
        # adoptable: manager 重启时不杀 → recorder 的 ffmpeg 不会因 RTSP 断流退出
        "adoptable":  True,
        "script":     "bin/go2rtc",
    },
    "ble": {
        "name":       "BLE Sensor (Pi)",
        "icon":       "📡",
        "desc":       (
            f"sense-u-ble → Pi: {_PI_HOST}" if _PI_HOST
            else "BLE: 未配置 pi_host (config.json)"
        ),
        # remote 模式：服务跑在 Pi 上的 systemd --user 单元里。
        # start/stop/restart 都通过 ssh 走，本地只跑一个 journalctl tail 给 UI 抓日志。
        "remote": {
            "host":     _PI_HOST,
            "user":     _PI_USER,
            "key":      _PI_KEY,
            "unit":     "sense-u-ble.service",
            "git_path": "/home/maomaoyu/sense-u-ble",
        },
        # adoptable: manager 退出时**不要** ssh 给 Pi 发 systemctl stop，让 Pi 上的
        # BLE 服务保持运行；下次 manager 启动会走 adopt 路径只起 tail。
        "adoptable":  True,
        "pairable":   True,    # UI 渲染"配对"按钮 → POST /api/manager/ble/pair
        "port":       None,
    },
    "server": {
        "name":       "BabySentinel Server",
        "icon":       "🍼",
        "desc":       f"Web · 摄像头 · 提醒 · Discord   :{ROOT_CFG.get('web_port', 8080)}",
        "cmd":        [sys.executable, "-u", "services/web/server.py"],
        "port":       ROOT_CFG.get("web_port", 8080),
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
        "desc":       f"Whisper STT · LLM · TTS   :{ROOT_CFG.get('voice_service_port', 8001)}",
        "cmd":        [sys.executable, "-u", "services/voice/voice_service.py"],
        "port":       ROOT_CFG.get("voice_service_port", 8001),
        # adoptable: manager 重启时不杀 → 避免 Whisper 模型重新加载（large-v3 加载耗时 30s+）
        "adoptable":  True,
        "script":     "services/voice/voice_service.py",
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


async def _do_start_remote(svc: str):
    """远端 systemd --user 服务启动 + 本地起一个 journalctl tail 把日志吐回 UI。

    Adopt 语义：如果 _procs[svc] 还没 tail（manager 刚启动或 tail 死了）且远端 unit
    已经 active，跳过 stop+start，只 spawn tail。这样 manager 重启不会打断 Pi 上
    正在跑的 BLE 服务（保持与本地 adoptable 同样的"零打扰"心智）。
    """
    defn   = SERVICES[svc]
    remote = defn["remote"]
    unit   = remote["unit"]
    if not remote.get("host"):
        _append_log(svc, "[错误] pi_host 未配置")
        return

    # Adopt path：本地无 tail + 远端 unit 已 active → 直接搭 tail
    have_tail = (_procs[svc] is not None and _procs[svc].returncode is None)
    if not have_tail:
        code, _ = await _ssh_run(remote, f"systemctl --user is-active {unit}", timeout=5)
        if code == 0:
            _append_log(svc, f"{'─'*40}")
            _append_log(svc, f"接管远端 unit (already active)，仅起 journalctl tail")
            await _spawn_remote_tail(svc, remote, unit)
            return

    await _do_stop(svc)   # 先把可能存在的 tail 清掉

    _append_log(svc, f"{'─'*40}")
    _append_log(svc, f"启动远端: ssh {remote['user']}@{remote['host']} systemctl --user start {unit}")

    code, out = await _ssh_run(remote, f"systemctl --user start {unit}")
    if code != 0:
        _append_log(svc, f"[启动失败 code={code}] {out.strip()[:300]}")
        return
    _append_log(svc, "远端 unit 已启动，开始抓日志...")
    await _spawn_remote_tail(svc, remote, unit)


async def _spawn_remote_tail(svc: str, remote: dict, unit: str) -> None:
    """起一个长连接 ssh + journalctl -f 把远端日志吐回本地 _logs deque。

    用 _SYSTEMD_USER_UNIT 过滤而不是 `--user`，因为部分 Pi 配置下 user journal
    不写盘（"No journal files were found"），但 user 单元的日志仍在系统 journal 里。
    """
    try:
        tail_proc = await asyncio.create_subprocess_exec(
            *_ssh_args(remote),
            f"journalctl _SYSTEMD_USER_UNIT={unit} -f -o cat -n 0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **_PROC_GROUP_KW,
        )
        _procs[svc]  = tail_proc
        _starts[svc] = time.time()
        asyncio.create_task(_drain(svc, tail_proc.stdout))
    except Exception as e:
        _append_log(svc, f"[日志 tail 启动失败] {e}")


async def _do_stop_remote(svc: str):
    defn   = SERVICES[svc]
    remote = defn["remote"]
    unit   = remote["unit"]
    proc   = _procs.get(svc)

    if remote.get("host"):
        _append_log(svc, "停止远端 unit...")
        code, out = await _ssh_run(remote, f"systemctl --user stop {unit}")
        if code != 0:
            _append_log(svc, f"[远端 stop 警告 code={code}] {out.strip()[:200]}")

    # 杀本地 tail 子进程
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=4)
        except asyncio.TimeoutError:
            proc.kill()
        _append_log(svc, f"已停止 (tail code={proc.returncode})")
    _procs[svc]  = None
    _starts[svc] = None


async def _do_start(svc: str):
    # 远端服务（如 BLE 跑在 Pi）走独立路径
    if SERVICES[svc].get("remote"):
        return await _do_start_remote(svc)

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
    if SERVICES[svc].get("remote"):
        return await _do_stop_remote(svc)

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

    # 包含历史路径 recorder_service.py（重构前），避免老进程漏扫成幽灵
    _orphan_pattern = (
        "services/recorder/service.py"
        "|services/web/server.py"
        "|services/voice/voice_service.py"
        "|recorder_service\\.py"
    )
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", _orphan_pattern],
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
    for svc in ("go2rtc", "ble", "server", "recorder", "voice"):
        await asyncio.sleep(0.3)
        await _do_start(svc)
    try:
        yield
    finally:
        # adoptable 服务（如 recorder）保留运行——下次 manager 启动时接管，避免录像中断
        for svc in ("voice", "recorder", "server", "ble", "go2rtc"):
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
                .replace("__WEB_PORT__", str(ROOT_CFG.get("web_port", 8080)))
                .replace("__CFG_VER__", _CFG_VER))
    return HTMLResponse(html)


@app.get("/api/manager/status")
async def get_status():
    return JSONResponse({
        svc: {
            **_svc_status(svc),
            "logs":     list(_logs[svc])[-80:],
            "name":     SERVICES[svc]["name"],
            "icon":     SERVICES[svc]["icon"],
            "desc":     SERVICES[svc]["desc"],
            # UI 用这两个 flag 决定是否渲染"检查更新/更新"按钮
            "remote":   bool(SERVICES[svc].get("remote")),
            "git":      bool((SERVICES[svc].get("remote") or {}).get("git_path")),
            "pairable": bool(SERVICES[svc].get("pairable")),
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


# ── 配置编辑（manager UI 写回 config.json）──────────────────────────

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def _set_dotted(obj: dict, path: str, value) -> None:
    """把 value 写入 obj[a][b][c]…，缺失的中间节点自动建为 dict。"""
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


@app.get("/api/manager/config")
async def get_config():
    """返回当前 config.json 的最新磁盘内容（绕过 ROOT_CFG cache）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return JSONResponse({"ok": True, "config": json.load(f)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"read fail: {e}"}, status_code=500)


@app.post("/api/manager/config")
async def post_config(request: Request):
    """把 patch 合并写回 config.json（dotted-path 平铺，atomic .tmp + rename）。"""
    body = await request.json()
    patch = body.get("patch")
    if not isinstance(patch, dict):
        return JSONResponse({"ok": False, "error": "patch must be object"}, status_code=400)

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"read fail: {e}"}, status_code=500)

    for k, v in patch.items():
        _set_dotted(cfg, str(k), v)

    tmp = CONFIG_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, CONFIG_PATH)
    except Exception as e:
        try: os.unlink(tmp)
        except Exception: pass
        return JSONResponse({"ok": False, "error": f"write fail: {e}"}, status_code=500)

    return JSONResponse({"ok": True})


# ── 远端 git 自检 / 更新 ─────────────────────────────────────────────

def _remote_git(svc: str) -> dict | None:
    r = (SERVICES.get(svc) or {}).get("remote") or {}
    return r if r.get("host") and r.get("git_path") else None


@app.get("/api/manager/{svc}/check_update")
async def check_update(svc: str):
    """ssh + git fetch + 看本地落后 origin 几个 commit。"""
    r = _remote_git(svc)
    if r is None:
        return JSONResponse({"ok": False, "error": "service is not a remote git service"}, status_code=400)

    cmd = (
        f"cd {r['git_path']} && "
        "git fetch -q origin 2>&1 && "
        "BEHIND=$(git rev-list --count HEAD..origin/HEAD 2>/dev/null) && "
        "echo \"BEHIND=$BEHIND\" && "
        "if [ \"$BEHIND\" != 0 ]; then git log -1 --format='LATEST=%h %s' origin/HEAD; fi"
    )
    code, out = await _ssh_run(r, cmd, timeout=20)
    if code != 0:
        return JSONResponse({"ok": False, "error": out.strip()[:300]}, status_code=500)

    behind = 0
    latest = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("BEHIND="):
            try: behind = int(line.split("=", 1)[1])
            except ValueError: pass
        elif line.startswith("LATEST="):
            latest = line.split("=", 1)[1]
    return JSONResponse({
        "ok":               True,
        "behind":           behind,
        "update_available": behind > 0,
        "latest_commit":    latest,
    })


@app.post("/api/manager/{svc}/update")
async def do_update(svc: str):
    """ssh + git pull + pip install -e . + 重启 unit。"""
    r = _remote_git(svc)
    if r is None:
        return JSONResponse({"ok": False, "error": "service is not a remote git service"}, status_code=400)

    _append_log(svc, f"{'─'*40}")
    _append_log(svc, "更新中：git pull ...")
    cmd = f"cd {r['git_path']} && git pull --ff-only 2>&1"
    code, out = await _ssh_run(r, cmd, timeout=60)
    for line in out.strip().splitlines()[-10:]:
        _append_log(svc, f"  git: {line}")
    if code != 0:
        _append_log(svc, f"[更新失败 code={code}]")
        return JSONResponse({"ok": False, "step": "git_pull", "log": out[-500:]}, status_code=500)

    _append_log(svc, "pip install -e . ...")
    cmd2 = f"cd {r['git_path']} && ./venv/bin/pip install -e . --quiet 2>&1"
    code2, out2 = await _ssh_run(r, cmd2, timeout=120)
    for line in out2.strip().splitlines()[-5:]:
        _append_log(svc, f"  pip: {line}")
    if code2 != 0:
        _append_log(svc, f"[pip 失败 code={code2}]")
        return JSONResponse({"ok": False, "step": "pip", "log": out2[-500:]}, status_code=500)

    _append_log(svc, "重启远端 unit 让新代码生效...")
    asyncio.create_task(_do_start(svc))   # _do_start 会先 stop 再 start
    return JSONResponse({"ok": True})


# ── BLE 配对（一次性获取 baby_code）─────────────────────────────────
#
# sense-u-ble 的 tools/pairing.py 是交互式工具：input() 等回车 + Phase 2 永远跑。
# 这里通过 SSH 让 Pi 跑该工具的非交互版本：
#   1. 停 sense-u-ble.service 释放 BLE 适配器
#   2. 删旧 baby_code.json（强制走 Phase 1）
#   3. echo '' | timeout 45 python tools/pairing.py
#      ↑ 喂空行让 input() 立即返回；timeout 在 Phase 2 起来后强杀
#   4. 检查 stdout 是否含 "baby_code 已保存"
#   5. 重启 service（无论成功失败）；失败时还原备份的 baby_code.bak.json

@app.post("/api/manager/ble/pair")
async def ble_pair():
    svc = "ble"
    defn = SERVICES.get(svc) or {}
    if not defn.get("pairable"):
        return JSONResponse({"ok": False, "error": "service not pairable"}, status_code=400)
    r = defn.get("remote") or {}
    if not r.get("host"):
        return JSONResponse({"ok": False, "error": "pi_host not configured"}, status_code=400)
    git_path = r.get("git_path")
    unit     = r.get("unit")
    if not git_path or not unit:
        return JSONResponse({"ok": False, "error": "remote missing git_path/unit"}, status_code=400)

    _append_log(svc, f"{'─'*40}")
    _append_log(svc, "[配对] 开始 — 请确认设备已长按两下进入配对模式（蓝灯慢闪）")

    # 1) 停 service
    _append_log(svc, "[配对] 停 sense-u-ble.service ...")
    code, out = await _ssh_run(r, f"systemctl --user stop {unit}", timeout=10)
    if code != 0:
        _append_log(svc, f"[配对] 停服务失败: {out.strip()[:200]}")
        return JSONResponse({"ok": False, "step": "stop_service", "log": out[-500:]}, status_code=500)

    # 2) 备份 + 删除旧 baby_code.json
    backup_cmd = (
        f"cd {git_path} && "
        f"if [ -f baby_code.json ]; then cp baby_code.json baby_code.bak.json; fi && "
        f"rm -f baby_code.json"
    )
    await _ssh_run(r, backup_cmd, timeout=5)

    # 3) 跑 pairing.py（非交互）
    _append_log(svc, "[配对] 运行 tools/pairing.py（45s 超时）...")
    pair_cmd = (
        f"cd {git_path} && "
        f"echo '' | timeout 45 venv/bin/python tools/pairing.py 2>&1 | tail -200; "
        f"if [ -f baby_code.json ]; then echo '__PAIR_OK__'; else echo '__PAIR_FAIL__'; fi"
    )
    code, out = await _ssh_run(r, pair_cmd, timeout=70)

    success = "__PAIR_OK__" in out and "baby_code 已保存" in out
    # 截短日志放到 UI（最后 ~60 行通常够定位问题）
    log_tail = "\n".join(out.strip().splitlines()[-60:])

    # 4) 失败时还原备份
    if not success:
        _append_log(svc, "[配对] ✗ 失败，还原旧 baby_code.json")
        await _ssh_run(
            r,
            f"cd {git_path} && [ -f baby_code.bak.json ] && cp baby_code.bak.json baby_code.json || true",
            timeout=5,
        )

    # 5) 重启 service（成功失败都要恢复 BLE 服务）
    asyncio.create_task(_do_start(svc))

    if success:
        _append_log(svc, "[配对] ✓ 配对成功 → 重启 service")
        return JSONResponse({"ok": True, "log": log_tail})
    else:
        _append_log(svc, f"[配对] ✗ 失败 (code={code})")
        return JSONResponse(
            {"ok": False, "step": "pair", "log": log_tail},
            status_code=500,
        )


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
