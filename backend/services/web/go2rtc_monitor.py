"""go2rtc 健康监测 + 自愈（精简版）。

go2rtc 子进程由 manager (`SERVICES['go2rtc']`) 负责拉起；这里只做两件事：
  1. 周期 TCP connect probe go2rtc 端口（1984）。连得上 → cam_ok=true，否则 false。
  2. 连续 5 次 (≥15s) TCP 连不上 → POST `/api/manager/go2rtc/restart`（90s cooldown）。

历史教训：曾用 HTTP `/api/streams?src=baby` 探活，看 producer.bytes_recv 是否
增长来抓 "假活"。但 go2rtc 1.9.14 这个 API 在同时服务多 WebRTC consumer 时
有 ~50% 概率返回空 body / 偶发 10s lock 卡死。任何基于 HTTP 的判定都不可靠，
会误把 cam_ok 翻 false → 所有浏览器同步拆 WebRTC → 死循环式 flicker。

纯 TCP probe 不走 go2rtc HTTP 栈，不受 API bug 影响。代价：丢了 "假活" 检测
（go2rtc 进程在但 RTSP 断流的情况）—— 这场景下浏览器侧 ICE 会自己检测到无帧，
30-60s 后浏览器主动失败重连；不再依赖服务端帮忙。
"""
import asyncio
import socket
import time
import urllib.request

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


async def _probe_tcp(port: int, timeout: float = 2.0) -> bool:
    """TCP connect 探活。Connect 成功就当 go2rtc 还活着——不走 HTTP 栈避免
    go2rtc 1.9.14 的 /api API bug。
    用 'localhost' 而非 '127.0.0.1'：go2rtc 二进制有时只 bind IPv6 [::]，
    硬编码 IPv4 会永远连不上。socket.create_connection 会按 getaddrinfo
    顺序尝试 IPv4 / IPv6，任一成功即可。"""
    loop = asyncio.get_event_loop()

    def _connect() -> bool:
        try:
            with socket.create_connection(("localhost", port), timeout=timeout):
                return True
        except OSError:
            return False

    try:
        return await loop.run_in_executor(None, _connect)
    except Exception:
        return False


async def _trigger_restart() -> bool:
    """请求 manager 重启 go2rtc。带 cooldown 防抖。"""
    global _last_restart_at
    now = time.time()
    if now - _last_restart_at < _RESTART_COOLDOWN_S:
        return False
    _last_restart_at = now

    mgr_port = ROOT_CFG.get("manager_port", 9091)
    loop = asyncio.get_event_loop()

    def _req() -> int:
        req = urllib.request.Request(
            f"http://127.0.0.1:{mgr_port}/api/manager/go2rtc/restart",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status

    try:
        status = await loop.run_in_executor(None, _req)
        log.warning(f"[go2rtc] TCP 持续不通，已请求 manager 重启 → HTTP {status}")
        return status == 200
    except Exception as e:
        log.warning(f"[go2rtc] manager 重启请求失败：{e}")
        return False


async def rtsp_loop() -> None:
    global _bad_count
    port = int(ROOT_CFG.get("go2rtc_port", 1984))
    log.info(f"[go2rtc] 健康监测启动（TCP probe）→ :{port}")

    while True:
        alive = await _probe_tcp(port)

        if alive:
            _bad_count = 0
        else:
            _bad_count += 1

        ok = _bad_count < _BAD_PROBES_FOR_BAD

        if ok != state.sensor_state["cam_ok"]:
            state.sensor_state["cam_ok"] = ok
            await state.broadcast({"type": "sensor", **state.sensor_state})
            log.info(f"[go2rtc] {'就绪' if ok else f'离线 (TCP 连不上, bad={_bad_count})'}")

        if _bad_count >= _BAD_PROBES_FOR_RESTART:
            if await _trigger_restart():
                _bad_count = 0

        await asyncio.sleep(_PROBE_INTERVAL_S)
