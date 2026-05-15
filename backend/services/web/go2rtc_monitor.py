"""go2rtc 健康监测 + 自愈（极简版 / 零 TCP）。

go2rtc 子进程由 manager (`SERVICES['go2rtc']`) 负责拉起；这里只做：
  1. 周期 `pgrep -f go2rtc` 检查进程是否还在。
  2. 连续 N 次找不到进程 → cam_ok=false。

历史教训演进：
  - v1: HTTP /api/streams?src=baby 探活看 bytes_recv —— go2rtc 1.9.14 该 API
    50% 空响应、偶发 lock 卡 10s，误判 cam_ok 让前端拆 WebRTC，flicker 死循环。
  - v2: TCP connect probe localhost:1984 —— 每次 socket.create_connection 是
    一次性新连接，close 后留 TIME_WAIT。3s 间隔每天累积 28k TIME_WAIT，几小时
    内耗光 macOS 16k ephemeral port 池，整个 Mac 出站 TCP 全瘫。
  - v3（本版）: pgrep 检查进程存在。纯 syscall，零网络，零 TIME_WAIT，永久不会
    把端口池吃光。代价：失去 "假活" 检测（进程在但 RTSP 断流），但浏览器自己
    的 ICE 在数十秒内会感知到无帧，影响可接受。
"""
import asyncio
import subprocess
import time

import services.web.state as state
from shared.config import ROOT_CFG, log


_PROBE_INTERVAL_S       = 30    # probe 间隔（之前 3s）。socket.create_connection 每次
                                # 都是一次性新连接 close 后留 TIME_WAIT，3s 间隔每天
                                # 累积 ~28k TIME_WAIT，把 macOS 16k ephemeral port
                                # 全填光，所有 localhost 出站连接挂死。30s 后每天
                                # 累积 ~2900，30s msl×2 后自然消化。
_BAD_PROBES_FOR_BAD     = 2     # 连续 2 次 (60s) 失败 → cam_ok=false
_BAD_PROBES_FOR_RESTART = 4     # 连续 4 次 (2min) 失败 → 请求 manager 重启
_RESTART_COOLDOWN_S     = 90    # 重启请求最小间隔

_bad_count:       int   = 0
_last_restart_at: float = 0.0


async def _probe_pgrep() -> bool:
    """pgrep -f go2rtc 检查进程是否存在。纯 fork/exec syscall，无任何网络连接。
    pgrep exit 0 = 有匹配 = 活；exit 1 = 无匹配 = 死。"""
    loop = asyncio.get_event_loop()

    def _check() -> bool:
        try:
            r = subprocess.run(
                ["pgrep", "-f", "go2rtc -config"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2,
            )
            return r.returncode == 0
        except Exception:
            # subprocess 异常（pgrep 不存在 / timeout）→ 别误报 false，保持上一态
            return True

    try:
        return await loop.run_in_executor(None, _check)
    except Exception:
        return True


async def _trigger_restart() -> bool:
    """go2rtc 进程不在 → 让 manager 重启。带 cooldown 防抖。
    用 curl 子进程而非 urlopen：避免 server 这边再开新的 TIME_WAIT。
    （manager 端 webhook 监听本来就是为外部触发设计的，curl 一次性可接受。）"""
    global _last_restart_at
    now = time.time()
    if now - _last_restart_at < _RESTART_COOLDOWN_S:
        return False
    _last_restart_at = now

    mgr_port = ROOT_CFG.get("manager_port", 9091)
    loop = asyncio.get_event_loop()

    def _req() -> bool:
        try:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "5",
                 "-X", "POST",
                 f"http://127.0.0.1:{mgr_port}/api/manager/go2rtc/restart"],
                capture_output=True, text=True, timeout=8,
            )
            return r.stdout.strip() == "200"
        except Exception:
            return False

    try:
        ok = await loop.run_in_executor(None, _req)
        log.warning(f"[go2rtc] 进程不在，已请求 manager 重启 → {'OK' if ok else 'FAIL'}")
        return ok
    except Exception as e:
        log.warning(f"[go2rtc] manager 重启请求失败：{e}")
        return False


async def rtsp_loop() -> None:
    global _bad_count
    log.info("[go2rtc] 健康监测启动（pgrep 进程检查）")

    while True:
        alive = await _probe_pgrep()

        if alive:
            _bad_count = 0
        else:
            _bad_count += 1

        ok = _bad_count < _BAD_PROBES_FOR_BAD

        if ok != state.sensor_state["cam_ok"]:
            state.sensor_state["cam_ok"] = ok
            await state.broadcast({"type": "sensor", **state.sensor_state})
            log.info(f"[go2rtc] {'就绪' if ok else f'离线 (进程不在, bad={_bad_count})'}")

        if _bad_count >= _BAD_PROBES_FOR_RESTART:
            if await _trigger_restart():
                _bad_count = 0

        await asyncio.sleep(_PROBE_INTERVAL_S)
