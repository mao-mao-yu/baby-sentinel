"""Discord Gateway 客户端 — Slash Command 交互处理"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import websockets

from services.web.notify._http import request_async as _http

from services.web.i18n import t, posture_label, entry_type_label, diaper_kind_label

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
        {"name": _CMD_LOG,    "description": t("discord_cmd_desc_log"),    "type": 1},
    ]


# ── Sub → emoji + i18n 标签 ───────────────────────────────────────────

# 不进 i18n 的纯 emoji 装饰，跨语言通用
_SUB_EMOJI: dict[str, str] = {
    "formula":     "🍼",
    "breastfeed":  "🤱",
    "bottle":      "🍶",
    "diaper":      "👶",
    "sleep_start": "😴",
    "sleep_end":   "☀️",
    "bath":        "🛁",
    "temperature": "🌡️",
    "weight":      "⚖️",
    "height":      "📏",
}


def _sub_text(sub: str) -> str:
    """sub → 当前语言下显示用文本（不带 emoji）。"""
    if sub == "sleep_start":
        return t("entry_sleep_start")
    if sub == "sleep_end":
        return t("entry_sleep_end")
    if sub == "bottle":
        return entry_type_label("bottle_milk")
    return entry_type_label(sub)  # formula / breastfeed / diaper / bath / temperature / weight / height


def _sub_label(sub: str) -> str:
    """sub → emoji + 文本，给按钮和 modal 标题用。"""
    return f"{_SUB_EMOJI.get(sub, '')} {_sub_text(sub)}"


# ── Component builders ────────────────────────────────────────────────

def _btn(label: str, custom_id: str, style: int = 2) -> dict:
    """style: 1=primary(blue) 2=secondary(gray) 3=success(green) 4=danger(red)."""
    return {"type": 2, "style": style, "label": label, "custom_id": custom_id}


def _main_menu_components() -> list[dict]:
    """`/log` 触发后展示的 11 个事件按钮（3 行 + 撤销单独一行）。"""
    cid = lambda s: f"{_PFX_LOG_BTN}{s}"
    return [
        {"type": 1, "components": [
            _btn(_sub_label("formula"),    cid("formula"),    1),
            _btn(_sub_label("breastfeed"), cid("breastfeed"), 1),
            _btn(_sub_label("bottle"),     cid("bottle"),     1),
            _btn(_sub_label("diaper"),     cid("diaper"),     1),
        ]},
        {"type": 1, "components": [
            _btn(_sub_label("sleep_start"), cid("sleep_start")),
            _btn(_sub_label("sleep_end"),   cid("sleep_end")),
            _btn(_sub_label("bath"),        cid("bath")),
        ]},
        {"type": 1, "components": [
            _btn(_sub_label("temperature"), cid("temperature")),
            _btn(_sub_label("weight"),      cid("weight")),
            _btn(_sub_label("height"),      cid("height")),
        ]},
        {"type": 1, "components": [
            _btn(t("log_undo_btn"), cid("undo"), 4),
        ]},
    ]


def _side_picker_components() -> list[dict]:
    return [{"type": 1, "components": [
        _btn(t("side_left"),  f"{_PFX_LOG_SIDE}left",  1),
        _btn(t("side_right"), f"{_PFX_LOG_SIDE}right", 1),
        _btn(t("side_both"),  f"{_PFX_LOG_SIDE}both",  1),
    ]}]


def _kind_picker_components() -> list[dict]:
    return [{"type": 1, "components": [
        _btn(f"💧 {t('diaper_kind_wet')}",       f"{_PFX_LOG_KIND}wet",   1),
        _btn(f"💩 {t('diaper_kind_dirty')}",     f"{_PFX_LOG_KIND}dirty", 1),
        _btn(f"💧💩 {t('diaper_kind_both')}",    f"{_PFX_LOG_KIND}both",  1),
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
    return _text_input("time", t("log_field_time"), False, "HH:MM")


def _modal(custom_id: str, title: str, *fields: dict) -> dict:
    """通用 modal 构造器，所有 modal 都自带 time 输入框作为最后一项。"""
    return {
        "type": _RT_MODAL,
        "data": {
            "custom_id":  custom_id,
            "title":      title,
            "components": [*fields, _time_input()],
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
            return {"title": t("log_unavailable"), "color": 0xED4245}
        try:
            entries = _build_entries(sub, opts)
            if not entries:
                return {"title": t("log_unknown_action"), "description": sub, "color": 0xED4245}
            for e in entries:
                await self.add_entry(e)
        except (KeyError, ValueError) as ex:
            return {"title": t("log_invalid_arg"), "description": str(ex), "color": 0xED4245}
        except Exception as ex:
            log.warning(f"[Discord] /log {sub} failed: {ex}")
            return {"title": t("log_failed"), "description": str(ex), "color": 0xED4245}

        return {
            "title":       t("log_logged"),
            "description": "\n".join(_fmt_entry_line(e) for e in entries),
            "color":       0x57F287,
        }

    @staticmethod
    def _normalize_modal_opts(sub: str, raw: dict) -> dict:
        """modal text inputs 都是字符串；按 sub 把数值字段转成数字。time 留给 _resolve_time 处理。"""
        out = dict(raw)
        if sub in ("formula", "bottle"):
            out["amount"] = float(raw["amount"])
        elif sub in ("temperature", "height"):
            out["value"] = float(raw["value"])
        elif sub == "weight":
            out["value"] = int(float(raw["value"]))   # 克数取整
        elif sub == "breastfeed":
            out["minutes"] = int(float(raw["minutes"]))
        return out

    def _modal_for(self, sub: str, *extras: str) -> dict:
        """
        每个 sub 都走 modal，让用户都有机会改时间（即使无其他输入）。
        custom_id 形如：
          - logmodal:formula
          - logmodal:breastfeed:left   (extras 编码 side)
          - logmodal:diaper:wet        (extras 编码 kind)
        """
        cid_parts = [sub, *extras]
        cid = _PFX_LOG_MOD + ":".join(cid_parts)
        title = _sub_label(sub)

        # 列出 sub 需要的（除 time 外的）输入字段
        if sub in ("formula", "bottle"):
            return _modal(cid, title,
                          _text_input("amount", t("log_field_amount_ml"), True, "90"))
        if sub == "breastfeed":
            return _modal(cid, title,
                          _text_input("minutes", t("log_field_minutes"), True, "15"))
        if sub == "temperature":
            return _modal(cid, title,
                          _text_input("value", t("log_field_temp"), True, "37.2"))
        if sub == "weight":
            return _modal(cid, title,
                          _text_input("value", t("log_field_weight"), True, "5000"))
        if sub == "height":
            return _modal(cid, title,
                          _text_input("value", t("log_field_height"), True, "60"))
        # 无其他输入：sleep_start / sleep_end / bath / diaper-after-kind → 仅 time
        return _modal(cid, title)

    async def _on_log_button(self, custom_id: str) -> dict:
        """主菜单按钮 → 返回 Discord interaction callback."""
        sub = custom_id[len(_PFX_LOG_BTN):]

        if sub == "undo":
            embed = await self._handle_undo()
            return {"type": _RT_UPDATE, "data": {
                "embeds": [embed], "components": [], "content": "", "flags": _FLAG_EPHEMERAL,
            }}

        # 二级 picker — 哺乳侧 / 尿布种类
        if sub == "breastfeed":
            return {"type": _RT_UPDATE, "data": {
                "content":    t("log_pick_side"),
                "embeds":     [],
                "components": _side_picker_components(),
                "flags":      _FLAG_EPHEMERAL,
            }}
        if sub == "diaper":
            return {"type": _RT_UPDATE, "data": {
                "content":    t("log_pick_kind"),
                "embeds":     [],
                "components": _kind_picker_components(),
                "flags":      _FLAG_EPHEMERAL,
            }}

        # 其它所有 sub（含 sleep_start/end/bath、formula/bottle、temperature/weight/height）
        # 都走 modal，统一让用户能改时间
        return self._modal_for(sub)

    async def _on_side_button(self, custom_id: str) -> dict:
        """哺乳侧按钮 → 弹 modal 收 minutes + time，side 编码进 custom_id extras."""
        side = custom_id[len(_PFX_LOG_SIDE):]
        return self._modal_for("breastfeed", side)

    async def _on_kind_button(self, custom_id: str) -> dict:
        """尿布种类按钮 → 弹 modal 收 time，kind 编码进 custom_id extras."""
        kind = custom_id[len(_PFX_LOG_KIND):]
        return self._modal_for("diaper", kind)

    async def _on_modal_submit(self, custom_id: str, fields: dict) -> dict:
        """modal 提交 → 解析参数 → 提交 entry."""
        # custom_id 形如 "logmodal:formula" / "logmodal:breastfeed:left" / "logmodal:diaper:wet"
        parts = custom_id[len(_PFX_LOG_MOD):].split(":")
        sub = parts[0]
        extras = parts[1:]

        try:
            opts = self._normalize_modal_opts(sub, fields)
        except (KeyError, ValueError) as ex:
            embed = {"title": t("log_invalid_arg"), "description": str(ex), "color": 0xED4245}
        else:
            if sub == "breastfeed" and extras:
                opts["side"] = extras[0]
            elif sub == "diaper" and extras:
                opts["kind"] = extras[0]
            embed = await self._submit_log(sub, opts)

        return {"type": _RT_REPLY, "data": {"embeds": [embed], "flags": _FLAG_EPHEMERAL}}

    async def _handle_undo(self) -> dict:
        if not (self.delete_entry and self.get_today_log):
            return {"title": t("log_unavailable"), "color": 0xED4245}
        try:
            entries, _ = self.get_today_log()
        except Exception as e:
            return {"title": t("log_failed"), "description": str(e), "color": 0xED4245}
        if not entries:
            return {"title": t("log_no_undo"), "color": 0xFEE75C}

        last = entries[-1]
        ts   = last.get("ts")
        if not ts:
            return {"title": t("log_failed"), "description": "missing ts", "color": 0xED4245}

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
                return {"title": t("log_failed"), "color": 0xED4245}

        return {
            "title":       t("log_undone"),
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
                            "content":    t("log_menu_title"),
                            "components": _main_menu_components(),
                            "flags":      _FLAG_EPHEMERAL,
                        }})
            return
