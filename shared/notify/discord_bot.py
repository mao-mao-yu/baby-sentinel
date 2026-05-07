"""Discord Gateway 客户端 — Slash Command 交互处理"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import websockets

from shared.notify._http import request_async as _http

from shared.i18n import t, posture_label, entry_type_label, diaper_kind_label

log = logging.getLogger("BabySentinel")

_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

_CMD_SENSOR = "get_sensor_status_now"
_CMD_TODAY  = "get_status_today"
_CMD_LOG    = "log"

# Component custom_id prefixes（Discord 状态全靠这个字符串编码，无需服务端 session）
_PFX_LOG_BTN  = "log:"        # 主菜单按钮 → log:formula / log:diaper / log:undo …
_PFX_LOG_SIDE = "logside:"    # 哺乳侧二级 picker → logside:left/right/both
_PFX_LOG_KIND = "logkind:"    # 尿布种类二级 picker → logkind:wet/dirty/both
_PFX_LOG_MOD  = "logmodal:"   # modal 提交 → logmodal:formula / logmodal:breastfeed:left

# Discord interaction response types
_RT_PONG          = 1
_RT_REPLY         = 4   # CHANNEL_MESSAGE_WITH_SOURCE
_RT_DEFER         = 5   # DEFERRED
_RT_UPDATE        = 7   # UPDATE_MESSAGE (edit原 component 消息)
_RT_MODAL         = 9

_FLAG_EPHEMERAL = 64    # 仅触发用户可见


def _commands() -> list[dict]:
    # 注册时延迟取 i18n 文案，避免在 import 期就锁定语言
    return [
        {"name": _CMD_SENSOR, "description": t("discord_cmd_desc_sensor"), "type": 1},
        {"name": _CMD_TODAY,  "description": t("discord_cmd_desc_today"),  "type": 1},
        {"name": _CMD_LOG,    "description": "记录育儿事件 / Log baby event", "type": 1},
    ]


# ── Component builders ────────────────────────────────────────────────

def _btn(label: str, custom_id: str, style: int = 2) -> dict:
    """style: 1=primary(blue) 2=secondary(gray) 3=success(green) 4=danger(red)."""
    return {"type": 2, "style": style, "label": label, "custom_id": custom_id}


def _main_menu_components() -> list[dict]:
    """`/log` 触发后展示的 11 个事件按钮（3 行 + 撤销单独一行）。"""
    return [
        {"type": 1, "components": [
            _btn("🍼 配方奶",   f"{_PFX_LOG_BTN}formula",     1),
            _btn("🤱 母乳",     f"{_PFX_LOG_BTN}breastfeed",  1),
            _btn("🍶 瓶喂",     f"{_PFX_LOG_BTN}bottle",      1),
            _btn("👶 尿布",     f"{_PFX_LOG_BTN}diaper",      1),
        ]},
        {"type": 1, "components": [
            _btn("😴 入睡",     f"{_PFX_LOG_BTN}sleep_start"),
            _btn("☀️ 醒来",     f"{_PFX_LOG_BTN}sleep_end"),
            _btn("🛁 洗澡",     f"{_PFX_LOG_BTN}bath"),
        ]},
        {"type": 1, "components": [
            _btn("🌡️ 体温",     f"{_PFX_LOG_BTN}temperature"),
            _btn("⚖️ 体重",     f"{_PFX_LOG_BTN}weight"),
            _btn("📏 身高",     f"{_PFX_LOG_BTN}height"),
        ]},
        {"type": 1, "components": [
            _btn("↩️ 撤销最后一条", f"{_PFX_LOG_BTN}undo", 4),
        ]},
    ]


def _side_picker_components() -> list[dict]:
    return [{"type": 1, "components": [
        _btn("左 / Left",   f"{_PFX_LOG_SIDE}left",  1),
        _btn("右 / Right",  f"{_PFX_LOG_SIDE}right", 1),
        _btn("两侧 / Both", f"{_PFX_LOG_SIDE}both",  1),
    ]}]


def _kind_picker_components() -> list[dict]:
    return [{"type": 1, "components": [
        _btn("💧 尿 / Wet",       f"{_PFX_LOG_KIND}wet",   1),
        _btn("💩 便 / Dirty",     f"{_PFX_LOG_KIND}dirty", 1),
        _btn("💧💩 都有 / Both",  f"{_PFX_LOG_KIND}both",  1),
    ]}]


def _text_input(name: str, label: str, required: bool = True,
                placeholder: str = "") -> dict:
    inp: dict = {
        "type": 4, "custom_id": name, "label": label,
        "style": 1,  # short single-line
        "required": required,
    }
    if placeholder:
        inp["placeholder"] = placeholder
    return {"type": 1, "components": [inp]}


def _time_input() -> dict:
    return _text_input("time", "时间 / Time HH:MM (留空=现在)", False, "HH:MM")


def _modal_amount(custom_id: str, title: str) -> dict:
    return {
        "type": _RT_MODAL,
        "data": {
            "custom_id": custom_id,
            "title":     title,
            "components": [_text_input("amount", "毫升 / mL", True, "90"), _time_input()],
        },
    }


def _modal_value(custom_id: str, title: str, label: str, placeholder: str = "") -> dict:
    return {
        "type": _RT_MODAL,
        "data": {
            "custom_id": custom_id,
            "title":     title,
            "components": [_text_input("value", label, True, placeholder), _time_input()],
        },
    }


def _modal_breastfeed(side: str) -> dict:
    side_zh = {"left": "左", "right": "右", "both": "两侧"}.get(side, side)
    return {
        "type": _RT_MODAL,
        "data": {
            "custom_id": f"{_PFX_LOG_MOD}breastfeed:{side}",
            "title":     f"🤱 母乳 ({side_zh})",
            "components": [
                _text_input("minutes", "分钟 / Minutes", True, "15"),
                _time_input(),
            ],
        },
    }


def _modal_fields(d: dict) -> dict[str, str]:
    """从 modal_submit 的 data.components 抽出 {custom_id: value}."""
    out = {}
    for row in d.get("data", {}).get("components", []):
        for c in row.get("components", []):
            out[c["custom_id"]] = c.get("value", "") or ""
    return out


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


def _resolve_time(at: str | None) -> tuple[str, int]:
    """解析 HH:MM 字符串 → (展示用 HH:MM, 时间戳)。
    传入空/无效 → 当前时间；解析后若指向未来（如凌晨说昨晚 23 点）→ 当作昨天。
    与 services/voice/tools/baby_records.py 保持同一语义。"""
    now_dt = datetime.now()
    if not at:
        return now_dt.strftime("%H:%M"), int(now_dt.timestamp())
    try:
        h, m = (int(x) for x in str(at).strip().split(":"))
        target = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if target > now_dt:
            target -= timedelta(days=1)
        return target.strftime("%H:%M"), int(target.timestamp())
    except Exception:
        return now_dt.strftime("%H:%M"), int(now_dt.timestamp())


def _opt_map(options: list[dict] | None) -> dict[str, Any]:
    """Discord interaction options [{name, value}, …] → {name: value}."""
    return {o["name"]: o["value"] for o in (options or [])}


def _build_entries(sub_name: str, opts: dict) -> list[dict]:
    """根据 subcommand 构造一或多条 baby_log entry。Returns [] for 'undo'."""
    t_str, ts = _resolve_time(opts.get("time"))

    if sub_name == "formula":
        return [{"type": "formula", "amount_ml": opts["amount"], "time": t_str, "ts": ts}]
    if sub_name == "bottle":
        return [{"type": "bottle_milk", "amount_ml": opts["amount"], "time": t_str, "ts": ts}]
    if sub_name == "breastfeed":
        side = opts["side"]
        mins = opts["minutes"]
        e: dict = {"type": "breastfeed", "side": side, "time": t_str, "ts": ts}
        if side == "both":
            e["left_min"]  = mins
            e["right_min"] = mins
        else:
            e["duration_min"] = mins
        return [e]
    if sub_name == "diaper":
        kind = opts["kind"]
        if kind == "both":
            # 与 voice tool 一致：写两条邻接 entry，前端 timeline / emoji 按 wet|dirty 二元处理
            return [
                {"type": "diaper", "kind": "wet",   "time": t_str, "ts": ts},
                {"type": "diaper", "kind": "dirty", "time": t_str, "ts": ts},
            ]
        return [{"type": "diaper", "kind": kind, "time": t_str, "ts": ts}]
    if sub_name == "sleep_start":
        return [{"type": "sleep", "action": "start", "time": t_str, "ts": ts}]
    if sub_name == "sleep_end":
        return [{"type": "sleep", "action": "end", "time": t_str, "ts": ts}]
    if sub_name == "temperature":
        return [{"type": "temperature", "value": opts["value"], "time": t_str, "ts": ts}]
    if sub_name == "weight":
        return [{"type": "weight", "value": opts["value"], "time": t_str, "ts": ts}]
    if sub_name == "height":
        return [{"type": "height", "value": opts["value"], "time": t_str, "ts": ts}]
    if sub_name == "bath":
        return [{"type": "bath", "time": t_str, "ts": ts}]
    return []


class GatewayClient:
    def __init__(
        self,
        token: str,
        get_state: Callable[[], dict],
        get_today_log: Callable[[], tuple[list[dict], dict]],
        add_entry: Callable[[dict], Awaitable[dict]] | None = None,
        delete_entry: Callable[[int], Awaitable[bool]] | None = None,
    ):
        self.token         = token
        self.app_id        = _parse_app_id(token)
        self.get_state     = get_state
        self.get_today_log = get_today_log
        # add_entry / delete_entry 为 None 时不注册 /log 命令的写入路径，bot 仍可只读运行
        self.add_entry     = add_entry
        self.delete_entry  = delete_entry
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

    async def _submit_log(self, sub: str, opts: dict) -> dict:
        """sub + 已 normalize 的 opts → 写入 baby_log → 回执 embed dict."""
        if not self.add_entry:
            return {"title": "❌ /log 不可用", "description": "服务端未启用写入路径", "color": 0xED4245}
        try:
            entries = _build_entries(sub, opts)
            if not entries:
                return {"title": "❌ Unknown sub", "description": sub, "color": 0xED4245}
            for e in entries:
                await self.add_entry(e)
        except (KeyError, ValueError) as ex:
            return {"title": "❌ 参数错误", "description": str(ex), "color": 0xED4245}
        except Exception as ex:
            log.warning(f"[Discord] /log {sub} failed: {ex}")
            return {"title": "❌ 记录失败", "description": str(ex), "color": 0xED4245}

        return {
            "title":       "✅ 已记录 / Logged",
            "description": "\n".join(_fmt_entry_line(e) for e in entries),
            "color":       0x57F287,
        }

    @staticmethod
    def _normalize_modal_opts(sub: str, raw: dict) -> dict:
        """modal text inputs are strings; convert to numeric where needed."""
        out = dict(raw)
        if sub in ("formula", "bottle"):
            out["amount"] = float(raw["amount"])
        elif sub in ("temperature", "weight", "height"):
            out["value"] = float(raw["value"])
        elif sub == "breastfeed":
            out["minutes"] = int(float(raw["minutes"]))
        return out

    async def _on_log_button(self, custom_id: str) -> dict:
        """主菜单按钮 → 返回 Discord interaction callback."""
        sub = custom_id[len(_PFX_LOG_BTN):]

        # 直接提交（无需更多输入）—— update 当前菜单为已记录
        if sub in ("sleep_start", "sleep_end", "bath"):
            embed = await self._submit_log(sub, {})
            return {"type": _RT_UPDATE, "data": {
                "embeds": [embed], "components": [], "flags": _FLAG_EPHEMERAL,
            }}

        if sub == "undo":
            embed = await self._handle_undo()
            return {"type": _RT_UPDATE, "data": {
                "embeds": [embed], "components": [], "flags": _FLAG_EPHEMERAL,
            }}

        # 二级 picker — 哺乳侧 / 尿布种类
        if sub == "breastfeed":
            return {"type": _RT_UPDATE, "data": {
                "content":    "🤱 选择哺乳侧 / Pick side:",
                "embeds":     [],
                "components": _side_picker_components(),
                "flags":      _FLAG_EPHEMERAL,
            }}
        if sub == "diaper":
            return {"type": _RT_UPDATE, "data": {
                "content":    "👶 选择类型 / Pick kind:",
                "embeds":     [],
                "components": _kind_picker_components(),
                "flags":      _FLAG_EPHEMERAL,
            }}

        # 数值输入 → modal
        if sub == "formula":
            return _modal_amount(f"{_PFX_LOG_MOD}formula", "🍼 配方奶 / Formula")
        if sub == "bottle":
            return _modal_amount(f"{_PFX_LOG_MOD}bottle", "🍶 瓶喂母乳 / Bottle")
        if sub == "temperature":
            return _modal_value(f"{_PFX_LOG_MOD}temperature", "🌡️ 体温 / Temperature",
                                "体温 °C / Value", "37.2")
        if sub == "weight":
            return _modal_value(f"{_PFX_LOG_MOD}weight", "⚖️ 体重 / Weight",
                                "克 / Grams", "5000")
        if sub == "height":
            return _modal_value(f"{_PFX_LOG_MOD}height", "📏 身高 / Height",
                                "厘米 / cm", "60")

        return {"type": _RT_REPLY, "data": {
            "content": f"❌ Unknown action: {sub}", "flags": _FLAG_EPHEMERAL,
        }}

    async def _on_side_button(self, custom_id: str) -> dict:
        """哺乳侧按钮 → 还需要 minutes，弹 modal."""
        side = custom_id[len(_PFX_LOG_SIDE):]
        return _modal_breastfeed(side)

    async def _on_kind_button(self, custom_id: str) -> dict:
        """尿布种类按钮 → 直接提交（time=now）."""
        kind = custom_id[len(_PFX_LOG_KIND):]
        embed = await self._submit_log("diaper", {"kind": kind})
        return {"type": _RT_UPDATE, "data": {
            "embeds": [embed], "components": [], "flags": _FLAG_EPHEMERAL,
        }}

    async def _on_modal_submit(self, custom_id: str, fields: dict) -> dict:
        """modal 提交 → 解析参数 → 提交 entry."""
        # custom_id 形如 "logmodal:formula" or "logmodal:breastfeed:left"
        parts = custom_id[len(_PFX_LOG_MOD):].split(":")
        sub = parts[0]
        extras = parts[1:]

        try:
            opts = self._normalize_modal_opts(sub, fields)
        except (KeyError, ValueError) as ex:
            embed = {"title": "❌ 参数无效", "description": str(ex), "color": 0xED4245}
        else:
            if sub == "breastfeed" and extras:
                opts["side"] = extras[0]
            embed = await self._submit_log(sub, opts)

        return {"type": _RT_REPLY, "data": {"embeds": [embed], "flags": _FLAG_EPHEMERAL}}

    async def _handle_undo(self) -> dict:
        if not (self.delete_entry and self.get_today_log):
            return {"title": "❌ undo 不可用", "color": 0xED4245}
        try:
            entries, _ = self.get_today_log()
        except Exception as e:
            return {"title": "❌ 读取今日记录失败", "description": str(e), "color": 0xED4245}
        if not entries:
            return {"title": "ℹ️ 今日暂无记录可撤销", "color": 0xFEE75C}

        last = entries[-1]
        ts   = last.get("ts")
        if not ts:
            return {"title": "❌ 无 ts 无法撤销", "color": 0xED4245}

        # 配对撤销：与 voice tool 同语义。/log diaper kind:both 写出 wet+dirty 两条相邻 entry，
        # 撤销时连同前一条一起删，符合"一次操作=一次撤销"的心智。
        deleted = []
        if (len(entries) >= 2 and last.get("type") == "diaper"
                and last.get("kind") in ("wet", "dirty")):
            prev = entries[-2]
            opposite = "dirty" if last["kind"] == "wet" else "wet"
            prev_ts = prev.get("ts")
            if (prev.get("type") == "diaper" and prev.get("kind") == opposite
                    and prev.get("time") == last.get("time")
                    and prev_ts and abs(ts - prev_ts) <= 2):
                if await self.delete_entry(ts):       deleted.append(last)
                if await self.delete_entry(prev_ts):  deleted.append(prev)

        if not deleted:
            if await self.delete_entry(ts):
                deleted.append(last)
            else:
                return {"title": "❌ 删除失败", "color": 0xED4245}

        return {
            "title":       "↩️ 已撤销 / Undone",
            "description": "\n".join(_fmt_entry_line(e) for e in deleted),
            "color":       0xFAA61A,
        }

    async def _handle_interaction(self, d: dict):
        # Discord interaction type:
        #   2 = APPLICATION_COMMAND (slash command invocation)
        #   3 = MESSAGE_COMPONENT  (button / select click)
        #   5 = MODAL_SUBMIT
        itype = d.get("type")

        # ── type 3: component (button) interactions ────────────────────
        if itype == 3:
            cid = d.get("data", {}).get("custom_id", "")
            try:
                if cid.startswith(_PFX_LOG_BTN):
                    callback = await self._on_log_button(cid)
                elif cid.startswith(_PFX_LOG_SIDE):
                    callback = await self._on_side_button(cid)
                elif cid.startswith(_PFX_LOG_KIND):
                    callback = await self._on_kind_button(cid)
                else:
                    return
            except Exception as e:
                log.warning(f"[Discord] component {cid} failed: {e}")
                callback = {"type": _RT_REPLY, "data": {
                    "content": f"❌ {e}", "flags": _FLAG_EPHEMERAL,
                }}
            await _http(self.token, "POST",
                        f"/interactions/{d['id']}/{d['token']}/callback", callback)
            return

        # ── type 5: modal submit ───────────────────────────────────────
        if itype == 5:
            cid = d.get("data", {}).get("custom_id", "")
            if not cid.startswith(_PFX_LOG_MOD):
                return
            fields = _modal_fields(d)
            callback = await self._on_modal_submit(cid, fields)
            await _http(self.token, "POST",
                        f"/interactions/{d['id']}/{d['token']}/callback", callback)
            return

        # ── type 2: slash command ──────────────────────────────────────
        if itype != 2:
            return

        data = d.get("data", {})
        cmd  = data.get("name")
        if cmd == _CMD_SENSOR:
            embed = {
                "title":       t("discord_title"),
                "description": _fmt_status(self.get_state()),
                "color":       0x5865F2,
            }
            await _http(self.token, "POST",
                        f"/interactions/{d['id']}/{d['token']}/callback",
                        {"type": _RT_REPLY, "data": {"embeds": [embed]}})
            return

        if cmd == _CMD_TODAY:
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
            await _http(self.token, "POST",
                        f"/interactions/{d['id']}/{d['token']}/callback",
                        {"type": _RT_REPLY, "data": {"embeds": [embed]}})
            return

        if cmd == _CMD_LOG:
            # 弹按钮菜单（ephemeral，仅触发用户可见）
            await _http(self.token, "POST",
                        f"/interactions/{d['id']}/{d['token']}/callback",
                        {"type": _RT_REPLY, "data": {
                            "content":    "📝 选择要记录的事件 / Pick an event to log:",
                            "components": _main_menu_components(),
                            "flags":      _FLAG_EPHEMERAL,
                        }})
            return
