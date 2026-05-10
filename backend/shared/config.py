"""
项目级共享配置 + 服务自管 config 加载工具。

设计：
  - 根 config.json 只存「跨服务」字段（端口、baby、language、log_level、binary 路径、
    跨设备/跨服务的网络地址等）。
  - 各 service 自管它自己的 config.json（如 services/voice/config.json）。
  - service 通过 `load_service_config(svc_dir)` 加载自己那份；需要跨服务字段时
    从本模块的 `ROOT_CFG` 拿。

兼容性：
  - 保留 `CFG`（指向 ROOT_CFG），让正在迁移的老代码继续跑；新代码不要再用 `CFG`，
    迁移完成后移除。
"""
import json
import logging
import os
from pathlib import Path

# shared/config.py 移到了 backend/shared/config.py，所以爬 3 层 dirname 才回到
# 项目根（config.json / logs/ / recordings/ 都在根）：file → shared → backend → root
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE  = os.path.join(BASE_DIR, "config.json")
EXAMPLE_FILE = os.path.join(BASE_DIR, "config.example.json")
CODE_FILE    = os.path.join(BASE_DIR, "baby_code.json")


def _load_defaults_from(example_path: str) -> dict:
    """从 *.example.json 读取默认值，过滤 `_xxx` 注释/分组键。"""
    if not os.path.exists(example_path):
        return {}
    with open(example_path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _load_with_defaults(cfg_path: str, example_path: str) -> dict:
    """读取 cfg_path（不存在则从 example 复制），合并 example 默认值在下层。"""
    defaults = _load_defaults_from(example_path)
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            return {**defaults, **json.load(f)}
    if defaults:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)
    return defaults.copy()


def load_service_config(service_dir) -> dict:
    """加载某 service 自己的 config.json（service_dir/config.json + service_dir/config.example.json）。
    用法：
        from pathlib import Path
        from shared.config import load_service_config
        SVC_CFG = load_service_config(Path(__file__).parent)
    """
    d = str(service_dir)
    return _load_with_defaults(
        os.path.join(d, "config.json"),
        os.path.join(d, "config.example.json"),
    )


# ── 项目级（跨服务）配置 ────────────────────────────────────────────────
# 仅放真正跨服务的字段（端口、baby、language、log_level、binary 路径、
# 跨设备/跨服务的网络地址、通知凭据等）。Service 内部参数请走 load_service_config。
ROOT_CFG: dict = _load_with_defaults(CONFIG_FILE, EXAMPLE_FILE)


# ── 日志（基于根配置 log_level）─────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, ROOT_CFG.get("log_level", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("BabySentinel")

# websockets logs WARNING on dead socket before our broadcast() cleans up
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("websockets.server").setLevel(logging.ERROR)


# ── 代码级常量（不放配置）──────────────────────────────────────────────
REC_DIR       = os.path.join(BASE_DIR, "recordings")
AUDIO_BITRATE = "32k"
ALERT_MAX_LOG = 100
