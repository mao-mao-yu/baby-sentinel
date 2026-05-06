"""
Recorder Service config — service-internal (sampling cadence) + cross-service
constants from ROOT_CFG (segment length, ffmpeg path, RTSP source).
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from shared.config import ROOT_CFG, load_service_config

_SVC = load_service_config(Path(__file__).parent)

# ── Service-internal ──────────────────────────────────────────────────
SENSOR_INTERVAL_S: int = int(_SVC.get("sensor_interval_s", 5))

# ── Cross-service (from root) ─────────────────────────────────────────
SEGMENT_S:           int = int(ROOT_CFG.get("segment_s", 360))
WEB_PORT:            int = int(ROOT_CFG.get("web_port", 8080))
BLE_POLL_INTERVAL_S: float = float(ROOT_CFG.get("ble_poll_interval_s", 2))
FFMPEG_PATH:         str = ROOT_CFG.get("ffmpeg_path", "")
TAPO_RTSP:           str = ROOT_CFG.get("tapo_rtsp", "")
