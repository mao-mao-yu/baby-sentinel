"""
Voice Service config — reads `services/voice/config.json` for service-internal
settings (whisper / llm / tts / api key) and falls back to root ROOT_CFG for
cross-service fields (ports, baby profile).
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from shared.config import ROOT_CFG, load_service_config

_SVC = load_service_config(Path(__file__).parent)

# ── Service-internal ──────────────────────────────────────────────────

# STT
WHISPER_MODEL:   str = _SVC.get("whisper_model",   "large-v3")
WHISPER_DEVICE:  str = _SVC.get("whisper_device",  "cuda")
WHISPER_COMPUTE: str = _SVC.get("whisper_compute", "float16")
WHISPER_BACKEND: str = _SVC.get("whisper_backend", "auto")
WHISPER_BEAM_SIZE: int = int(_SVC.get("whisper_beam_size", 10))
WHISPER_INITIAL_PROMPT: str = _SVC.get(
    "whisper_initial_prompt",
    # Chinese: covers all baby-care commands the user might say
    "宝宝喝了配方奶九十毫升，奶粉冲了一百毫升。"
    "母乳左乳喂了十五分钟，右乳喂了十分钟，两边都喂了。"
    "瓶喂母乳六十毫升。"
    "换尿布了，是尿尿，是便便，尿尿和便便都有，大便有点稀，颜色偏黄。"
    "体温三十七点二度，有点发烧，三十八度。"
    "宝宝睡着了，宝宝入睡了，宝宝醒来了，宝宝起来了。"
    "撤销上一条，取消刚才的记录，删除上一条。"
    "今天喂了几次，上次换尿布是几点，今日统计。"
    # Japanese: same vocabulary in Japanese
    "粉ミルクを九十ミリ飲みました。母乳、左おっぱい十五分、右おっぱい十分、両方授乳。"
    "哺乳瓶で六十ミリ。おむつを替えました。おしっこ、うんち、両方。"
    "うんちが少し柔らかい、黄色っぽい。体温三十七度二分、熱がある、三十八度。"
    "ねんねしました、寝ました、起きました、起きた。"
    "取り消して、さっきの記録を削除。今日の記録、前回の授乳は何時。",
)

# LLM provider selection
LLM_PROVIDER: str = _SVC.get("llm_provider", "minimax")

# LLM (MiniMax)
MINIMAX_API_KEY:  str = _SVC.get("minimax_api_key", "")
MINIMAX_BASE_URL: str = _SVC.get("minimax_base_url", "https://api.minimax.io")
MINIMAX_LLM_MODEL: str = _SVC.get("minimax_llm_model", "MiniMax-Text-01")

# LLM (DeepSeek)
DEEPSEEK_API_KEY:          str  = _SVC.get("deepseek_api_key", "")
DEEPSEEK_BASE_URL:         str  = _SVC.get("deepseek_base_url", "https://api.deepseek.com")
DEEPSEEK_MODEL:            str  = _SVC.get("deepseek_model", "deepseek-v4-flash")
DEEPSEEK_REASONING_EFFORT: str  = _SVC.get("deepseek_reasoning_effort", "high")
DEEPSEEK_THINKING_ENABLED: bool = bool(_SVC.get("deepseek_thinking_enabled", True))

# TTS
TTS_PROVIDER: str = _SVC.get("tts_provider", "minimax")
TTS_MODEL:    str = _SVC.get("tts_model", "speech-2.6-hd")
TTS_VOICE_ZH: str = _SVC.get("tts_voice_zh", "Mandarin_Female")
TTS_VOICE_JA: str = _SVC.get("tts_voice_ja", "Japanese_Female")
TTS_VOICE_EN: str = _SVC.get("tts_voice_en", "English_Female")

# Internal API auth (for calling baby_log on web service)
BABY_API_KEY: str = _SVC.get("internal_api_key", "")

# ── Cross-service (from root) ─────────────────────────────────────────
VOICE_SERVICE_PORT: int = ROOT_CFG.get("voice_service_port", 8001)
BABY_API_URL: str = f"http://127.0.0.1:{ROOT_CFG.get('web_port', 8080)}"
BABY_NAME: str = ROOT_CFG.get("baby", {}).get("name", "赤ちゃん")
