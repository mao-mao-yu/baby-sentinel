"""go2rtc 健康监测。

go2rtc 子进程由 manager (`SERVICES['go2rtc']`) 负责拉起；
这里只做：
  - 周期 HTTP probe `/api/streams`
  - 在 online ↔ offline 切换时更新 `sensor_state['cam_ok']` + 广播给 WS client

历史版本同时 spawn go2rtc 二进制 + 写 go2rtc.yaml，跟 manager 重复了，已删。
yaml 由 manager._gen_go2rtc_yaml 生成。
"""
import asyncio
import urllib.request

import shared.state as state
from shared.config import ROOT_CFG, log


async def _probe(port: int) -> bool:
    """非阻塞 HTTP probe go2rtc /api/streams。"""
    loop = asyncio.get_event_loop()

    def _req() -> bool:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/streams", timeout=2)
        return True

    try:
        return await loop.run_in_executor(None, _req)
    except Exception:
        return False


async def rtsp_loop() -> None:
    port = int(ROOT_CFG.get("go2rtc_port", 1984))
    log.info(f"[go2rtc] 健康监测启动 → :{port}")
    while True:
        ok = await _probe(port)
        if ok != state.sensor_state["cam_ok"]:
            state.sensor_state["cam_ok"] = ok
            await state.broadcast({"type": "sensor", **state.sensor_state})
            log.info(f"[go2rtc] {'就绪' if ok else '离线'}")
        await asyncio.sleep(3)
