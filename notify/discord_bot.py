"""Discord Gateway 客户端 — Slash Command 交互处理"""

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Callable

import websockets

log = logging.getLogger("BabySentinel")

_API         = "https://discord.com/api/v10"
_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

_COMMANDS = [
    {"name": "get_babystatus", "description": "查看宝宝实时传感器状态", "type": 1},
]


def _parse_app_id(token: str) -> str:
    seg  = token.split(".")[0]
    seg += "=" * (-len(seg) % 4)
    return base64.b64decode(seg).decode()


async def _http(token: str, method: str, path: str, payload=None) -> dict | None:
    url  = f"{_API}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type":  "application/json; charset=utf-8",
            "User-Agent":    "BabySentinel (https://github.com, 1.0)",
        },
        method=method,
    )
    loop = asyncio.get_event_loop()

    def _do():
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            log.warning(f"[Discord] HTTP {e.code} {path}: {e.read().decode(errors='replace')}")
            return None
        except Exception as e:
            log.warning(f"[Discord] 请求失败 {path}: {e}")
            return None

    return await loop.run_in_executor(None, _do)


_POSTURE_JA = {"仰卧": "仰向け", "俯卧": "うつ伏せ", "左侧卧": "左向き", "右侧卧": "右向き"}


def _fmt_status(s: dict) -> str:
    lines = [f"{'🟢' if s.get('ble_ok') else '🔴'} BLE {'接続中' if s.get('ble_ok') else '未接続'}"]
    if s.get("is_wearing") is not None:
        lines.append("👶 装着中" if s["is_wearing"] else "❌ 未装着")
    if s.get("posture"):
        posture_ja = _POSTURE_JA.get(s["posture"], s["posture"])
        lines.append(f"🤸 姿勢: {posture_ja}")
    if s.get("breath_rate") is not None:
        lines.append(f"💨 呼吸: {s['breath_rate']} 回/分")
    if s.get("temperature") is not None:
        lines.append(f"🌡️ 体温: {s['temperature']} °C")
    if s.get("battery") is not None:
        icon = "🔋" if s["battery"] > 20 else "🪫"
        lines.append(f"{icon} バッテリー: {s['battery']}%")
    lines.append(f"🕐 更新: {s.get('last_update') or '—'}")
    return "\n".join(lines)


class GatewayClient:
    def __init__(self, token: str, get_state: Callable[[], dict]):
        self.token     = token
        self.app_id    = _parse_app_id(token)
        self.get_state = get_state
        self._seq: int | None = None

    async def run(self):
        result = await _http(self.token, "PUT",
                             f"/applications/{self.app_id}/commands", _COMMANDS)
        if result is not None:
            log.info(f"[Discord] Slash 命令已注册: {[c['name'] for c in (result or [])]}")
        while True:
            try:
                await self._connect()
            except Exception as e:
                log.warning(f"[Discord Gateway] 断线: {e}")
            log.debug("[Discord Gateway] 10 秒后重连...")
            await asyncio.sleep(10)

    async def _connect(self):
        async with websockets.connect(_GATEWAY_URL) as ws:
            hb_task = None
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    op  = msg["op"]
                    if op == 10:
                        interval = msg["d"]["heartbeat_interval"] / 1000
                        await ws.send(json.dumps({"op": 1, "d": None}))
                        await ws.send(json.dumps({
                            "op": 2,
                            "d": {
                                "token":   self.token,
                                "intents": 0,
                                "properties": {"os": "windows", "browser": "BabySentinel", "device": "BabySentinel"},
                                "presence": {
                                    "status": "online", "afk": False,
                                    "activities": [{"name": "👶 宝宝监控中", "type": 3}],
                                },
                            },
                        }))
                        hb_task = asyncio.create_task(self._heartbeat(ws, interval))
                    elif op == 0:
                        self._seq = msg.get("s")
                        t = msg.get("t")
                        if t == "READY":
                            log.info("[Discord Gateway] 已连接，Slash 命令就绪")
                        elif t == "INTERACTION_CREATE":
                            asyncio.create_task(self._handle_interaction(msg["d"]))
                    elif op in (7, 9):
                        break
            finally:
                if hb_task:
                    hb_task.cancel()

    async def _heartbeat(self, ws, interval: float):
        while True:
            await asyncio.sleep(interval)
            await ws.send(json.dumps({"op": 1, "d": self._seq}))

    async def _handle_interaction(self, d: dict):
        if d.get("data", {}).get("name") != "get_babystatus":
            return
        await _http(self.token, "POST",
                    f"/interactions/{d['id']}/{d['token']}/callback",
                    {"type": 4, "data": {
                        "embeds": [{"title": "👶 赤ちゃんのリアルタイム状態",
                                    "description": _fmt_status(self.get_state()),
                                    "color": 0x5865F2}],
                    }})
