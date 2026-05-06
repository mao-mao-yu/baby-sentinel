"""Discord Gateway 客户端 — Slash Command 交互处理"""

import asyncio
import base64
import json
import logging
from typing import Callable

import websockets

from shared.notify._http import request_async as _http

from shared.i18n import t, posture_label, entry_type_label, diaper_kind_label

log = logging.getLogger("BabySentinel")

_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

_CMD_SENSOR = "get_sensor_status_now"
_CMD_TODAY  = "get_status_today"


def _commands() -> list[dict]:
    # 注册时延迟取 i18n 文案，避免在 import 期就锁定语言
    return [
        {"name": _CMD_SENSOR, "description": t("discord_cmd_desc_sensor"), "type": 1},
        {"name": _CMD_TODAY,  "description": t("discord_cmd_desc_today"),  "type": 1},
    ]


def _parse_app_id(token: str) -> str:
    seg  = token.split(".")[0]
    seg += "=" * (-len(seg) % 4)
    return base64.b64decode(seg).decode()


def _fmt_status(s: dict) -> str:
    ble_label = t("discord_ble_on") if s.get("ble_ok") else t("discord_ble_off")
    lines = [f"{'🟢' if s.get('ble_ok') else '🔴'} BLE {ble_label}"]
    if s.get("posture"):
        lines.append(t("discord_posture", value=posture_label(s["posture"])))
    if s.get("breath_rate") is not None:
        lines.append(t("discord_breath", rate=s["breath_rate"]))
    if s.get("temperature") is not None:
        lines.append(t("discord_temp", value=s["temperature"]))
    if s.get("battery") is not None:
        icon = "🔋" if s["battery"] > 20 else "🪫"
        lines.append(t("discord_battery", icon=icon, value=s["battery"]))
    lines.append(t("discord_update", value=s.get("last_update") or "—"))
    return "\n".join(lines)


def _fmt_duration_min(total_min: int) -> str:
    """复用 i18n 的 duration 模板（不依赖 baby_log，避免循环）。"""
    h, m = divmod(max(0, int(total_min)), 60)
    return t("duration_h_m", h=h, m=m) if h else t("duration_m", m=m)


def _fmt_entry_line(e: dict) -> str:
    typ = e.get("type", "") or ""
    time_str = e.get("time", "") or "--:--"
    label = entry_type_label(typ)
    detail = ""

    if typ in ("formula", "bottle_milk"):
        ml = e.get("amount_ml")
        detail = f"{ml} mL" if ml else ""
    elif typ == "breastfeed":
        l_min = e.get("left_min")
        r_min = e.get("right_min")
        if l_min and r_min:
            detail = f"{t('side_left')}{l_min} / {t('side_right')}{r_min} 分"
        else:
            side = e.get("side", "")
            side_label = {
                "left":  t("side_left"),
                "right": t("side_right"),
                "both":  t("side_both"),
            }.get(side, "")
            mins = e.get("duration_min")
            if mins:
                detail = f"{side_label} {mins}分".strip()
            else:
                detail = side_label
    elif typ == "diaper":
        detail = diaper_kind_label(e.get("kind", ""))
    elif typ == "sleep":
        action = e.get("action")
        if action == "start":
            label = t("entry_sleep_start")
        elif action == "end":
            label = t("entry_sleep_end")
            if e.get("duration_str"):
                detail = e["duration_str"]
    elif typ in ("temperature", "weight", "height"):
        v = e.get("value")
        units = {"temperature": "°C", "weight": "g", "height": "cm"}
        if v is not None:
            detail = f"{v} {units.get(typ, '')}".strip()

    parts = [f"`{time_str}`", label]
    if detail:
        parts.append(detail)
    return "• " + " ".join(parts)


def _fmt_today_log(entries: list[dict], stats: dict) -> str:
    if not entries:
        return t("discord_today_empty")

    # 概览
    summary = []
    if stats.get("feed_count"):
        summary.append(t(
            "discord_today_feeds",
            count=stats["feed_count"],
            total=stats.get("total_ml", 0),
        ))
    wet   = stats.get("diaper_wet", 0)
    dirty = stats.get("diaper_dirty", 0)
    if wet or dirty:
        summary.append(t("discord_today_diapers", wet=wet, dirty=dirty))
    if stats.get("sleep_total_min"):
        summary.append(t(
            "discord_today_sleep",
            duration=_fmt_duration_min(stats["sleep_total_min"]),
            longest=_fmt_duration_min(stats.get("sleep_longest_min", 0)),
        ))

    sections: list[str] = []
    if summary:
        sections.append(f"**{t('discord_today_summary')}**\n" + "\n".join(summary))

    # 详细记录（按时间升序，baby_log 已排好）
    detail_lines = [_fmt_entry_line(e) for e in entries]
    sections.append(f"**{t('discord_today_entries')}**\n" + "\n".join(detail_lines))

    out = "\n\n".join(sections)
    # Discord embed description 上限 4096，超长截断兜底
    if len(out) > 4000:
        out = out[:3990].rsplit("\n", 1)[0] + "\n…"
    return out


class GatewayClient:
    def __init__(
        self,
        token: str,
        get_state: Callable[[], dict],
        get_today_log: Callable[[], tuple[list[dict], dict]],
    ):
        self.token         = token
        self.app_id        = _parse_app_id(token)
        self.get_state     = get_state
        self.get_today_log = get_today_log
        self._seq: int | None = None

    async def run(self):
        result = await _http(self.token, "PUT",
                             f"/applications/{self.app_id}/commands", _commands())
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
        cmd = d.get("data", {}).get("name")
        if cmd == _CMD_SENSOR:
            embed = {
                "title":       t("discord_title"),
                "description": _fmt_status(self.get_state()),
                "color":       0x5865F2,
            }
        elif cmd == _CMD_TODAY:
            try:
                entries, stats = self.get_today_log()
            except Exception as e:
                log.warning(f"[Discord] 获取今日记录失败: {e}")
                entries, stats = [], {}
            embed = {
                "title":       t("discord_today_title"),
                "description": _fmt_today_log(entries, stats),
                "color":       0x57F287,
            }
        else:
            return

        await _http(self.token, "POST",
                    f"/interactions/{d['id']}/{d['token']}/callback",
                    {"type": 4, "data": {"embeds": [embed]}})
