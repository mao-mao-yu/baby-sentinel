"""
BLE Service config — service-internal (sensor address, BLE timings, alert
thresholds) + cross-service ports from ROOT_CFG.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from shared.config import ROOT_CFG, load_service_config

_SVC = load_service_config(Path(__file__).parent)

# ── Service-internal ──────────────────────────────────────────────────

# Sensor identity
BLE_ADDRESS:     str  = _SVC.get("ble_address", "")
BLE_MAC:         str  = _SVC.get("ble_mac", "")
BLE_DUMP_RAW:    bool = bool(_SVC.get("ble_dump_raw", False))

# BLE link timings (this service's own; the manager-monitored heartbeat lives in root)
BLE_SCAN_TIMEOUT_S:    float = float(_SVC.get("ble_scan_timeout_s", 20))
BLE_CONNECT_TIMEOUT_S: float = float(_SVC.get("ble_connect_timeout_s", 15))
BLE_RECONNECT_DELAY_S: float = float(_SVC.get("ble_reconnect_delay_s", 10))

# Alert thresholds (BLE owns alert detection from sensor data)
PRONE_ALERT_THRESHOLD_S:   float = float(_SVC.get("prone_alert_threshold_s", 30))
PRONE_ALERT_COOLDOWN_S:    float = float(_SVC.get("prone_alert_cooldown_s", 300))
BREATH_ALERT_THRESHOLD_RATE: float = float(_SVC.get("breath_alert_threshold_rate", 8))
BREATH_ALERT_DURATION_S:   float = float(_SVC.get("breath_alert_duration_s", 20))
BREATH_ALERT_COOLDOWN_S:   float = float(_SVC.get("breath_alert_cooldown_s", 300))

# ── Cross-service (from root) ─────────────────────────────────────────
BLE_PORT:              int   = int(ROOT_CFG.get("ble_port", 8082))
WEB_PORT:              int   = int(ROOT_CFG.get("web_port", 8080))
# 这两个是跨服务时序契约（web 也消费），所以放在 root：
BLE_POLL_INTERVAL_S:   float = float(ROOT_CFG.get("ble_poll_interval_s", 2))
BLE_HEALTH_TIMEOUT_S:  float = float(ROOT_CFG.get("ble_health_timeout_s", 10))
