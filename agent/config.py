"""
Voice Agent config — self-contained, no dependency on shared/.
Reads config.json from the project root (parent of agent/).
"""
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_cfg_file = _ROOT / "config.json"

_CFG: dict = {}
if _cfg_file.exists():
    with open(_cfg_file, encoding="utf-8") as _f:
        _CFG = json.load(_f)

def _get(key: str, default):
    return _CFG.get(key, default)

# ── Server ────────────────────────────────────────────────────────────
VOICE_SERVICE_URL: str = _get("voice_service_url", "http://localhost:8001")

# ── Wake word ─────────────────────────────────────────────────────────
WAKE_MODEL_PATH:     str   = str(_ROOT / "wakeword_training/models/hey_momobot.onnx")
WAKE_THRESHOLD:      float = _get("wake_threshold", 0.5)
WAKE_CONFIRM_FRAMES: int   = _get("wake_confirm_frames", 2)
WAKE_PEAK_THRESHOLD: float = _get("wake_peak_threshold", 0.5)

# ── Audio ─────────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16000
CHUNK_SIZE:  int = 1280
CHANNELS:    int = 1

# ── VAD / recording ───────────────────────────────────────────────────
SILENCE_RMS:  int   = _get("voice_silence_rms", 200)
SILENCE_S:    float = _get("voice_silence_s",   2.0)
MAX_RECORD_S: float = _get("voice_max_record_s", 15.0)

# ── Network ───────────────────────────────────────────────────────────
# 90s 余量：M2.7 thinking 模型在多事件请求下 LLM 阶段 ~30s + TTS 合成 ~10-20s + 网络 + WAV 传输。
REQUEST_TIMEOUT_S: float = 90.0
COOLDOWN_S:        float = _get("wake_cooldown_s", 3.0)

# ── 白噪保活 / Bluetooth speaker keep-alive ─────────────────────────────
# 持续在默认输出播放极低音量白噪，防止蓝牙音响因长时间静默自动断连。
KEEPALIVE_NOISE:     bool  = bool(_get("keepalive_noise", False))
KEEPALIVE_NOISE_AMP: float = float(_get("keepalive_noise_amplitude", 0.005))
