import asyncio
from datetime import datetime

from app.config import ALERT_MAX_LOG, CFG, log
from app.state import alert_log, broadcast


async def notify_qq(message: str) -> None:
    """TODO: 接入 go-cqhttp 等 QQ 推送方案"""
    log.debug(f"[QQ STUB] {message}")


async def notify_discord(message: str, level: str = "warning") -> None:
    from notify.discord_send import send_alert
    token       = CFG.get("discord_token", "")
    channel_ids = CFG.get("discord_channel_ids", [])
    user_ids    = CFG.get("discord_user_ids", [])
    if not token or (not channel_ids and not user_ids):
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, send_alert, token, channel_ids, user_ids, message, level
    )


async def notify_bark(message: str, level: str = "warning") -> None:
    from notify.bark_send import send_bark
    keys   = CFG.get("bark_keys", [])
    server = CFG.get("bark_server_url", "https://api.day.app")
    if not keys:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send_bark, server, keys, message, level)


async def trigger_alert(message: str, level: str = "warning") -> None:
    """触发告警：写日志 + 广播 WebSocket + 分发通知渠道"""
    entry = {
        "type":      "alert",
        "level":     level,
        "message":   message,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    alert_log.append(entry)
    if len(alert_log) > ALERT_MAX_LOG:
        alert_log.pop(0)
    await broadcast(entry)
    await notify_qq(message)
    await notify_discord(message, level)
    await notify_bark(message, level)
