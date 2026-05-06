import json
import logging
import os

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE  = os.path.join(BASE_DIR, "config.json")
EXAMPLE_FILE = os.path.join(BASE_DIR, "config.example.json")
CODE_FILE    = os.path.join(BASE_DIR, "baby_code.json")


def _load_defaults() -> dict:
    """从 config.example.json 读取默认值（单一数据源）。
    过滤掉 `_xxx` 形式的注释/分组键。"""
    with open(EXAMPLE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _load() -> dict:
    defaults = _load_defaults()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return {**defaults, **json.load(f)}
    # 首次运行：从 example 复制一份给用户
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(defaults, f, indent=2, ensure_ascii=False)
    return defaults.copy()


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
