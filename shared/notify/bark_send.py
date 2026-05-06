"""Bark iOS 推送 — 支持多设备 key

设计原则：跟 notify/discord_send.py 风格对齐，纯同步函数供 run_in_executor 调用。
"""

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("BabySentinel")

DEFAULT_SERVER = "https://api.day.app"

# 告警等级 → Bark 推送参数
# - danger  : critical 关键告警，绕过静音/勿扰，最大音量 + alarm 铃声 + 持续响铃直到点开
# - warning : active 普通通知（不打扰，但能看到）
# - info    : passive 静默通知（不亮屏，仅出现在通知中心）
_LEVEL_PRESET = {
    "danger": {
        "level":     "critical",   # 关键告警，绕过静音/勿扰
        "volume":    10,           # 最大音量（默认 5）
        "sound":     "alarm",      # 警报铃声
        "call":      "1",          # 持续重复响铃直到点开
        "isArchive": "1",          # 自动存进 App 历史，方便事后回看
    },
    "warning": {"level": "active"},
    "info":    {"level": "passive"},
}


def send_bark(
    server: str,
    keys: list,
    message: str,
    level: str = "warning",
    group: str = "BabySentinel",
    timeout: float = 5,
) -> bool:
    """向多个 Bark device key 推送同一条消息。返回 True 当至少一个成功。"""
    if not keys:
        return False

    preset = _LEVEL_PRESET.get(level, _LEVEL_PRESET["warning"])

    # 标题/正文：第一行作标题，剩余作 body
    parts = message.split("\n", 1)
    title = parts[0]
    body  = parts[1].strip() if len(parts) > 1 else title

    payload: dict = {
        "title": title,
        "body":  body,
        "group": group,
        **preset,
    }

    base = (server or DEFAULT_SERVER).rstrip("/")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    ok_count = 0
    for key in keys:
        if not key or not isinstance(key, str):
            continue
        req = urllib.request.Request(
            f"{base}/{key}",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if 200 <= r.status < 300:
                    ok_count += 1
                else:
                    log.warning(f"[Bark] HTTP {r.status} key={key[:6]}...")
        except urllib.error.HTTPError as e:
            log.warning(f"[Bark] HTTP {e.code} key={key[:6]}...")
        except Exception as e:
            log.warning(f"[Bark] 推送失败 key={key[:6]}...: {e}")

    if ok_count:
        log.debug(f"[Bark] 已推送至 {ok_count}/{len(keys)} 设备: {title}")
    return ok_count > 0
