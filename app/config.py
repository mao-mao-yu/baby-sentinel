import json
import logging
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CODE_FILE   = os.path.join(BASE_DIR, "baby_code.json")

_DEFAULTS: dict = {
    # ── Connections ──────────────────────────────────────────────────────
    "ble_address":            "AA:BB:CC:DD:EE:FF",
    "tapo_rtsp":              "rtsp://YOUR_USER:YOUR_PASSWORD@192.168.x.x:554/stream1",
    "ffmpeg_path":            "",
    "go2rtc_path":            "",
    # ── Ports ────────────────────────────────────────────────────────────
    "web_host":               "0.0.0.0",
    "web_port":               8080,
    "go2rtc_port":            1984,
    "ble_port":               8082,
    "manager_port":           9091,
    # ── Recording ────────────────────────────────────────────────────────
    "segment_s":              180,    # video segment length (seconds)
    "sensor_interval_s":      5,      # how often sensor snapshots are written
    # ── BLE timing ───────────────────────────────────────────────────────
    "ble_scan_timeout_s":     20,     # max wait while scanning for device
    "ble_connect_timeout_s":  15,     # GATT connection timeout
    "ble_poll_interval_s":    5,      # period between 0xBA data requests
    "ble_reconnect_delay_s":  10,     # wait after disconnect before retry
    # ── Alerts ───────────────────────────────────────────────────────────
    "prone_alert_cooldown_s": 300,    # min seconds between consecutive prone alerts
    "feed_repeat_s":          1800,   # repeat feed reminder every N seconds
    # ── Notifications ────────────────────────────────────────────────────
    "discord_token":          "",
    "discord_channel_ids":    [],
    "discord_user_ids":       [],
    # ── Logging ──────────────────────────────────────────────────────────
    "log_level":              "INFO",
    # ── Baby profile ─────────────────────────────────────────────────────
    "baby": {
        "birth_date":         "",
        "weight_g":           0,
        "feed_type":          "formula",
        "feed_interval_min":  150,
    },
}


def _load() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return {**_DEFAULTS, **json.load(f)}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(_DEFAULTS, f, indent=2, ensure_ascii=False)
    return _DEFAULTS.copy()


CFG: dict = _load()

logging.basicConfig(
    level=getattr(logging, CFG.get("log_level", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("BabySentinel")

# websockets logs WARNING on dead socket before our broadcast() cleans up
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("websockets.server").setLevel(logging.ERROR)

# ── Code-level constants ──────────────────────────────────────────────
# Not user-tunable; defined once here so all modules share a single source.

# Recording
REC_DIR       = os.path.join(BASE_DIR, "recordings")
AUDIO_BITRATE = "32k"

# Alerts
ALERT_MAX_LOG = 100
