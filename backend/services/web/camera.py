"""go2rtc 健康监测 + 自愈。

go2rtc 子进程由 manager (`SERVICES['go2rtc']`) 负责拉起；这里只做：
  - 周期 HTTP probe `/api/streams?src=baby` 拿 producer.bytes_recv
  - 任一不正常状态（HTTP 不通 / producers 空 / bytes_recv 不增长）→ cam_ok=false
  - 持续 4 次（12s）异常 → POST `/api/manager/go2rtc/restart` 让 manager 拉起新进程
    （带 90s cooldown 防抖）。这里覆盖两类故障：
      a) Tapo "假活"：TCP/HTTP 都 200 但 bytes_recv 不动（PLAY 后断流）
      b) go2rtc 进程整个死掉：HTTP connection refused —— manager 接管的孤儿
         没有 watchdog 时这里就是唯一的复活路径
  - 状态切换时广播 `{type: sensor}` 给 WS client，前端 cam pill / WebRTC 跟着切

go2rtc.yaml 由 manager._gen_go2rtc_yaml 生成；这里不再 spawn / 写 yaml。
"""
import asyncio
import json
import time
import urllib.request

import services.web.state as state
from shared.config import ROOT_CFG, log


# 连续 N 次异常 probe（HTTP 不通 / producers 空 / bytes 不增长）→ cam_ok=false 并请求重启。
# 周期 3s × 4 = 12s 容忍窗，足以吸收正常网络抖动，又不至于让画面僵太久。
_BAD_PROBES_FOR_RESTART = 4
# 连发重启请求的最小间隔，避免 manager 起新进程过程中再次被触发，造成 restart loop。
# Tapo 抽风时新 go2rtc 起来到拉到第一帧大概 5-10s，给点冗余。
_RESTART_COOLDOWN_S = 90

_last_bytes:      int   = -1     # 上一次 probe 的 bytes_recv；-1 = 还没基线
_bad_count:       int   = 0      # 连续异常 probe 数（不区分 HTTP 死 / 假活）
_last_restart_at: float = 0.0    # unix 秒，0 = 从未触发


async def _probe_stream(port: int) -> tuple[bool, int]:
    """probe go2rtc /api/streams?src=baby。
    返回 (alive, bytes_recv)；alive=False 时 bytes 永远 0。
    alive=True 但 producers=[] 也算 not alive（RTSP 连不上 Tapo 时 go2rtc 仍会响应 HTTP，
    但 producers 是空列表）。"""
    loop = asyncio.get_event_loop()

    def _req() -> tuple[bool, int]:
        url = f"http://127.0.0.1:{port}/api/streams?src=baby"
        with urllib.request.urlopen(url, timeout=2) as r:
            data = json.load(r)
        producers = data.get("producers") or []
        if not producers:
            return (False, 0)
        return (True, int(producers[0].get("bytes_recv", 0)))

    try:
        return await loop.run_in_executor(None, _req)
    except Exception:
        return (False, 0)


async def _trigger_restart() -> bool:
    """让 manager 重启 go2rtc。带 cooldown 防抖，超出 _RESTART_COOLDOWN_S 才会真发请求。"""
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
        log.warning(f"[go2rtc] 出帧停滞，已请求 manager 重启 → HTTP {status}")
        return status == 200
    except Exception as e:
        log.warning(f"[go2rtc] manager 重启请求失败：{e}")
        return False


async def rtsp_loop() -> None:
    global _last_bytes, _bad_count
    port = int(ROOT_CFG.get("go2rtc_port", 1984))
    log.info(f"[go2rtc] 健康监测启动 → :{port}")

    while True:
        alive, bytes_recv = await _probe_stream(port)

        if not alive:
            # HTTP 不通 / producers 空 → 异常计数，复位 bytes 基线
            _bad_count += 1
            _last_bytes = -1
            ok = False
        elif _last_bytes < 0:
            # 首次拿到值，作基线，本轮判 ok（不计入异常）
            _last_bytes = bytes_recv
            _bad_count = 0
            ok = True
        elif bytes_recv > _last_bytes:
            _last_bytes = bytes_recv
            _bad_count = 0
            ok = True
        else:
            # HTTP 活但 bytes 没动 → 计为异常（"假活"）
            _bad_count += 1
            ok = _bad_count < _BAD_PROBES_FOR_RESTART

        if ok != state.sensor_state["cam_ok"]:
            state.sensor_state["cam_ok"] = ok
            await state.broadcast({"type": "sensor", **state.sensor_state})
            cause = "HTTP 不通" if not alive else f"假活 stall (bytes={bytes_recv})"
            log.info(f"[go2rtc] {'就绪' if ok else f'离线 ({cause}, bad={_bad_count})'}")

        # 异常累计够阈值 → 请求 manager 重启（cooldown 内幂等）
        if (not ok) and _bad_count >= _BAD_PROBES_FOR_RESTART:
            if await _trigger_restart():
                # 已发起重启，复位计数让新进程上来时重新建立基线，cooldown 期间不重复触发
                _last_bytes = -1
                _bad_count = 0

        await asyncio.sleep(3)
