"""
Baby record tools — LLM tool definitions + HTTP executors.
Each tool maps to a BabySentinel REST API call.
"""
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Any

# 共享给所有 log_* 工具的 time 参数 schema
_TIME_PROP = {
    "time": {
        "type": "string",
        "description": (
            "事件发生时间 / イベントの発生時刻，24 小时制 HH:MM。"
            "用户明确说出时间或相对时间（如『3点』『一小时前』『11時半』）时填入。"
            "未提及时间则省略此参数（默认按服务器当前时间记录）。"
        ),
    },
}

from services.voice import config as cfg

# ── Tool definitions (OpenAI function-calling schema) ─────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "log_feeding",
            "description": (
                "记录喂奶事件 / 授乳イベントを記録する。"
                "【formula/bottle_milk】amount_ml 必填，缺失时先调用 request_followup。"
                "【breastfeed】side + duration_min 必填，缺失时先调用 request_followup。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feed_type": {
                        "type": "string",
                        "enum": ["formula", "breastfeed", "bottle_milk"],
                        "description": (
                            "配方奶/粉ミルク=formula, "
                            "直接哺乳/直接授乳=breastfeed, "
                            "瓶喂母乳/搾乳ボトル=bottle_milk"
                        ),
                    },
                    "amount_ml": {
                        "type": "number",
                        "description": "奶量（毫升）。formula 和 bottle_milk 必填，breastfeed 不用填",
                    },
                    "duration_min": {
                        "type": "number",
                        "description": "哺乳时长（分钟）。breastfeed 必填，formula/bottle_milk 不用填",
                    },
                    "side": {
                        "type": "string",
                        "enum": ["left", "right", "both"],
                        "description": (
                            "哺乳侧，仅 breastfeed 填写。"
                            "左乳/左=left, 右乳/右=right, 两侧/両方=both"
                        ),
                    },
                    **_TIME_PROP,
                },
                "required": ["feed_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_diaper",
            "description": (
                "记录换尿布 / おむつ交換を記録する。"
                "kind 必填：尿/おしっこ=wet，大便/うんち=dirty，两者/両方=both。"
                "⚠️ kind 未明时，必须先调用 request_followup。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["wet", "dirty", "both"],
                        "description": "尿=wet, 便便/大便=dirty, 尿+便便=both",
                    },
                    "amount": {
                        "type": "string",
                        "enum": ["一点点", "少", "通常", "大"],
                        "description": (
                            "便便的【量】/ 量。仅 dirty/both 可选。"
                            "极少=一点点(少しだけ), 少=少(少なめ), "
                            "中等=通常(普通の量), 多=大(たくさん)。"
                            "用户说『普通の量』『普通くらい』『普通』(指量) → 通常。"
                        ),
                    },
                    "consistency": {
                        "type": "string",
                        "enum": ["泻", "软", "通常", "硬"],
                        "description": (
                            "便便的【软硬/性状】/ 硬さ・状態。仅 dirty/both 可选。"
                            "水样/拉稀=泻(下痢/水様), 软便=软(軟便/ゆるい), "
                            "正常硬度=通常(普通便/いつも通り), 硬便=硬(硬い)。"
                            "⚠️『下痢』『ゆるい』『水っぽい』→ 必填 泻。"
                        ),
                    },
                    "color": {
                        "type": "string",
                        "description": "大便颜色（黄色/绿色/黑色等），可选",
                    },
                    **_TIME_PROP,
                },
                "required": ["kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_sleep",
            "description": (
                "记录睡眠开始或结束 / 睡眠の開始または終了を記録する。"
                "入睡/ねんね/睡着=start，醒来/起きた/醒了=end。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "end"],
                        "description": "入睡=start, 醒来=end",
                    },
                    **_TIME_PROP,
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_temperature",
            "description": (
                "记录体温 / 体温を記録する。"
                "⚠️ value 未提供时，必须先调用 request_followup。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "体温数值，如 37.2。必填",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["C", "F"],
                        "description": "摄氏=C（默认），华氏=F",
                        "default": "C",
                    },
                    **_TIME_PROP,
                },
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_today",
            "description": (
                "查询今日育儿统计摘要 / 本日の育児サマリーを取得する。"
                "返回喂奶次数/总量、换尿布次数、睡眠时长等今日汇总数据。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_last",
            "description": (
                "查询今日最近一次某类事件 / 本日の直近イベントを取得する。"
                "用于'上次喂奶是什么时候'、'最后一次换尿布'等查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["feeding", "diaper", "sleep", "temperature"],
                        "description": "喂奶=feeding, 换尿布=diaper, 睡眠=sleep, 体温=temperature",
                    },
                },
                "required": ["event_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_last_entry",
            "description": (
                "撤销/删除今日最后一条记录 / 直近の記録を削除する。"
                "用于'撤销'、'刚才记错了'、'取消上一条'、「取り消して」等场景。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_followup",
            "description": (
                "【唯一的提问方式】当必要信息缺失时调用此工具向用户追问。"
                "系统会将 question 播放给用户并等待语音回答。"
                "⚠️ 严禁直接在回复文本中提问，必须通过本工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "播报给用户的问题，简短清晰，如'多少毫升？'",
                    },
                },
                "required": ["question"],
            },
        },
    },
]


# ── HTTP helpers ──────────────────────────────────────────────────────

def _api_call(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{cfg.BABY_API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": cfg.BABY_API_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _now_time() -> str:
    return datetime.now().strftime("%H:%M")


def _resolve_time(at: str | None) -> tuple[str, int]:
    """解析 LLM 传入的 HH:MM 时间字符串 → (展示用 HH:MM, 时间戳)。
    传入空/无效 → 当前时间；解析后若指向未来（如凌晨说昨晚 23 点）→ 当作昨天。"""
    now_dt = datetime.now()
    if not at:
        return now_dt.strftime("%H:%M"), int(now_dt.timestamp())
    try:
        h, m = (int(x) for x in at.strip().split(":"))
        target = now_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if target > now_dt:
            target -= timedelta(days=1)
        return target.strftime("%H:%M"), int(target.timestamp())
    except Exception:
        return now_dt.strftime("%H:%M"), int(now_dt.timestamp())


# ── Tool executors ────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> tuple[bool, str]:
    """
    Execute a tool call and return (success, result_text).
    result_text is fed back to LLM for final response generation.
    """
    try:
        if name == "log_feeding":
            return _log_feeding(**args)
        if name == "log_diaper":
            return _log_diaper(**args)
        if name == "log_sleep":
            return _log_sleep(**args)
        if name == "log_temperature":
            return _log_temperature(**args)
        if name == "delete_last_entry":
            return _delete_last_entry()
        if name == "query_today":
            return _query_today()
        if name == "query_last":
            return _query_last(**args)
        return False, f"Unknown tool: {name}"
    except Exception as exc:
        return False, f"Tool error: {exc}"


def _log_feeding(feed_type: str, amount_ml: float | None = None,
                 duration_min: float | None = None, side: str | None = None,
                 time: str | None = None) -> tuple[bool, str]:
    t_str, ts = _resolve_time(time)
    entry: dict[str, Any] = {"type": feed_type, "time": t_str, "ts": ts}
    if feed_type == "breastfeed":
        entry["side"] = side or "left"
        if side == "both" and duration_min is not None:
            # Frontend & backend both expect left_min/right_min for bilateral feeds
            entry["left_min"] = duration_min
            entry["right_min"] = duration_min
        elif duration_min is not None:
            entry["duration_min"] = duration_min
    elif amount_ml is not None:
        entry["amount_ml"] = amount_ml
    _api_call("POST", "/api/log", entry)
    desc = f"{amount_ml}ml " if amount_ml else f"{duration_min}分 " if duration_min else ""
    return True, f"log_feeding ok: {feed_type} {desc}{t_str}"


def _log_diaper(kind: str, amount: str | None = None,
                consistency: str | None = None, color: str | None = None,
                time: str | None = None) -> tuple[bool, str]:
    t_str, ts = _resolve_time(time)

    # kind=both → 写两条 entry（一条 wet 一条 dirty），与手动录入数据形态一致。
    # 前端 timeline / emoji / 统计逻辑都基于 wet|dirty 二元分类，不识别 both；
    # 后端 add_entry 会自动避开 ts 冲突（time 相同时第二条 ts+=1）。
    if kind == "both":
        _api_call("POST", "/api/log",
                  {"type": "diaper", "kind": "wet", "time": t_str, "ts": ts})
        dirty_entry: dict[str, Any] = {
            "type": "diaper", "kind": "dirty", "time": t_str, "ts": ts,
        }
        if amount:
            dirty_entry["amount"] = amount
        if consistency:
            dirty_entry["consistency"] = consistency
        if color:
            dirty_entry["color"] = color
        _api_call("POST", "/api/log", dirty_entry)
        return True, f"log_diaper ok: wet+dirty {t_str}"

    entry: dict[str, Any] = {"type": "diaper", "kind": kind, "time": t_str, "ts": ts}
    if amount:
        entry["amount"] = amount
    if consistency:
        entry["consistency"] = consistency
    if color:
        entry["color"] = color
    _api_call("POST", "/api/log", entry)
    return True, f"log_diaper ok: {kind} {t_str}"


def _log_sleep(action: str, time: str | None = None) -> tuple[bool, str]:
    t_str, ts = _resolve_time(time)
    entry = {"type": "sleep", "action": action, "time": t_str, "ts": ts}
    _api_call("POST", "/api/log", entry)
    return True, f"log_sleep ok: {action} {t_str}"


def _log_temperature(value: float, unit: str = "C",
                     time: str | None = None) -> tuple[bool, str]:
    t_str, ts = _resolve_time(time)
    val_c = value if unit == "C" else round((value - 32) * 5 / 9, 1)
    entry = {"type": "temperature", "value": val_c, "time": t_str, "ts": ts}
    _api_call("POST", "/api/log", entry)
    return True, f"log_temperature ok: {val_c}°C {t_str}"


def _delete_last_entry() -> tuple[bool, str]:
    today = _api_call("GET", "/api/log/today")
    if not today:
        return False, "No entries to delete today."
    last = today[-1]
    ts = last.get("ts")
    if not ts:
        return False, "Last entry has no timestamp, cannot delete."

    # Paired-undo: voice tool 的 kind=both 会写出 wet+dirty 两条邻接 entry（同 time，
    # ts 相差 ≤ 2s）。撤销时把这一对一起删，符合"一次语音=一次撤销"的用户心智。
    if len(today) >= 2 and last.get("type") == "diaper" and last.get("kind") in ("wet", "dirty"):
        prev = today[-2]
        prev_ts = prev.get("ts")
        opposite = "dirty" if last["kind"] == "wet" else "wet"
        is_pair = (
            prev.get("type") == "diaper"
            and prev.get("kind") == opposite
            and prev.get("time") == last.get("time")
            and prev_ts and abs(ts - prev_ts) <= 2
        )
        if is_pair:
            _api_call("DELETE", f"/api/log/entry/{ts}")
            _api_call("DELETE", f"/api/log/entry/{prev_ts}")
            return True, f"Deleted paired diaper entries (wet+dirty) at {last.get('time')}"

    _api_call("DELETE", f"/api/log/entry/{ts}")
    return True, f"Deleted last entry: {last.get('type')} at {last.get('time')}"


def _query_today() -> tuple[bool, str]:
    stats = _api_call("GET", "/api/log/stats")
    today = _api_call("GET", "/api/log/today")
    return True, json.dumps({"stats": stats, "today_count": len(today)}, ensure_ascii=False)


def _query_last(event_type: str) -> tuple[bool, str]:
    today = _api_call("GET", "/api/log/today")
    type_map = {
        "feeding": {"formula", "breastfeed", "bottle_milk"},
        "diaper":  {"diaper", "wet", "poop"},   # wet/poop: backwards compat with old entries
        "sleep":   {"sleep", "wake"},            # wake: backwards compat with old entries
        "temperature": {"temperature"},
    }
    allowed = type_map.get(event_type, set())
    matches = [e for e in reversed(today) if e.get("type") in allowed]
    if matches:
        return True, json.dumps(matches[0], ensure_ascii=False)
    return True, f"No {event_type} records today."
