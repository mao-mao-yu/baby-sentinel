"""Discord Bot 通知 — 同步发送告警消息（供 run_in_executor 使用）"""

import logging

from notify._http import request

log = logging.getLogger("BabySentinel")

_COLORS = {"danger": 0xE74C3C, "warning": 0xF39C12, "info": 0x3498DB}

_dm_channel_cache: dict[str, str] = {}


def _get_dm_channel(token: str, user_id: str) -> str | None:
    if user_id in _dm_channel_cache:
        return _dm_channel_cache[user_id]
    result = request(token, "POST", "/users/@me/channels", {"recipient_id": user_id})
    if result and "id" in result:
        _dm_channel_cache[user_id] = result["id"]
        return result["id"]
    return None


def _send_to_channel(token: str, channel_id: str, message: str, level: str) -> bool:
    color   = _COLORS.get(level, _COLORS["warning"])
    payload = {"embeds": [{"description": message, "color": color}]}
    return request(token, "POST", f"/channels/{channel_id}/messages", payload) is not None


def _to_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [str(v) for v in val if v and str(v).strip()]


def send_alert(token: str, channel_ids, user_ids, message: str, level: str = "warning") -> bool:
    """向多个频道和/或用户私信发送告警。阻塞调用，供 run_in_executor 使用。"""
    if not token:
        return False
    channels = _to_list(channel_ids)
    users    = _to_list(user_ids)
    if not channels and not users:
        return False

    ok = True
    for cid in channels:
        ok &= _send_to_channel(token, cid, message, level)
    for uid in users:
        dm_id = _get_dm_channel(token, uid)
        if dm_id:
            ok &= _send_to_channel(token, dm_id, message, level)
        else:
            log.warning(f"[Discord] 无法创建私信频道 user_id={uid}")
            ok = False

    if ok:
        log.debug(f"[Discord] 已发送至 {len(channels)} 频道 {len(users)} 用户: {message}")
    return ok
