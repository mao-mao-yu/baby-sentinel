"""
Web Service config — UI/notifications service-internal + cross-service ports.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from shared.config import ROOT_CFG, load_service_config

_SVC = load_service_config(Path(__file__).parent)

# ── Service-internal ──────────────────────────────────────────────────
WEB_HOST:        str = _SVC.get("web_host", "0.0.0.0")
FEED_REPEAT_S:   int = int(_SVC.get("feed_repeat_s", 1800))

# ── Cross-service (from root) ─────────────────────────────────────────
# 通知凭据归属 root —— 因为 shared/alerts 也要读（被 BLE 等多服务调用）
DISCORD_TOKEN: str = ROOT_CFG.get("discord_token", "")
WEB_PORT:              int   = int(ROOT_CFG.get("web_port", 8080))
MANAGER_PORT:          int   = int(ROOT_CFG.get("manager_port", 9091))
SEGMENT_S:             int   = int(ROOT_CFG.get("segment_s", 360))  # for playback UI alignment
BLE_POLL_INTERVAL_S:   float = float(ROOT_CFG.get("ble_poll_interval_s", 2))
BLE_HEALTH_TIMEOUT_S:  float = float(ROOT_CFG.get("ble_health_timeout_s", 10))
LANGUAGE:              str   = ROOT_CFG.get("language", "ja")
BABY:                  dict  = ROOT_CFG.get("baby", {})
