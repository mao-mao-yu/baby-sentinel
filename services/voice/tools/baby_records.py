"""
Baby record tools — LLM tool definitions + HTTP executors.
Each tool maps to a BabySentinel REST API call.
"""
import json
import time
import urllib.request
from datetime import datetime
from typing import Any

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
                        "description": "便便量，可选，仅 dirty/both",
                    },
                    "consistency": {
                        "type": "string",
                        "enum": ["泻", "软", "通常", "硬"],
                        "description": "大便性状，可选，仅 dirty/both",
                    },
                    "color": {
                        "type": "string",
                        "description": "大便颜色（黄色/绿色/黑色等），可选",
                    },
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
                 duration_min: float | None = None, side: str | None = None) -> tuple[bool, str]:
    entry: dict[str, Any] = {"type": feed_type, "time": _now_time(), "ts": int(time.time())}
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
    return True, f"log_feeding ok: {feed_type} {desc}{_now_time()}"


def _log_diaper(kind: str, amount: str | None = None,
                consistency: str | None = None, color: str | None = None) -> tuple[bool, str]:
    entry: dict[str, Any] = {"type": "diaper",
                              "kind": kind, "time": _now_time(), "ts": int(time.time())}
    if amount:
        entry["amount"] = amount
    if consistency:
        entry["consistency"] = consistency
    if color:
        entry["color"] = color
    _api_call("POST", "/api/log", entry)
    return True, f"log_diaper ok: {kind} {_now_time()}"


def _log_sleep(action: str) -> tuple[bool, str]:
    entry = {"type": "sleep", "action": action, "time": _now_time(), "ts": int(time.time())}
    _api_call("POST", "/api/log", entry)
    return True, f"log_sleep ok: {action} {_now_time()}"


def _log_temperature(value: float, unit: str = "C") -> tuple[bool, str]:
    val_c = value if unit == "C" else round((value - 32) * 5 / 9, 1)
    entry = {"type": "temperature", "value": val_c, "time": _now_time(), "ts": int(time.time())}
    _api_call("POST", "/api/log", entry)
    return True, f"log_temperature ok: {val_c}°C {_now_time()}"


def _delete_last_entry() -> tuple[bool, str]:
    today = _api_call("GET", "/api/log/today")
    if not today:
        return False, "No entries to delete today."
    last = today[-1]
    ts = last.get("ts")
    if not ts:
        return False, "Last entry has no timestamp, cannot delete."
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
