"""
Voice Service config — reads from the shared BabySentinel config.json.
Runs on the Windows/Linux server alongside manager.py.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
from shared.config import CFG

# ── Service ───────────────────────────────────────────────────────────
VOICE_SERVICE_PORT: int = CFG.get("voice_service_port", 8001)

# ── STT ───────────────────────────────────────────────────────────────
WHISPER_MODEL:   str = CFG.get("whisper_model",   "large-v3")
WHISPER_DEVICE:  str = CFG.get("whisper_device",  "cuda")     # "cuda" or "cpu"
WHISPER_COMPUTE: str = CFG.get("whisper_compute", "float16")
WHISPER_BACKEND: str = CFG.get("whisper_backend", "auto")     # "auto" | "faster-whisper" | "mlx"
WHISPER_BEAM_SIZE: int = int(CFG.get("whisper_beam_size", 10))
# Domain initial_prompt: primes Whisper's decoder with baby-care vocabulary.
# Override via config.json "whisper_initial_prompt" if needed.
WHISPER_INITIAL_PROMPT: str = CFG.get(
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

# ── LLM (MiniMax) ─────────────────────────────────────────────────────
MINIMAX_API_KEY:  str = CFG.get("minimax_api_key", "")
MINIMAX_BASE_URL: str = CFG.get("minimax_base_url", "https://api.minimax.io")
MINIMAX_LLM_MODEL: str = CFG.get("minimax_llm_model", "MiniMax-Text-01")

# ── TTS ───────────────────────────────────────────────────────────────
TTS_PROVIDER:     str = CFG.get("tts_provider", "minimax")   # "minimax" or "edge"
TTS_MODEL:        str = CFG.get("tts_model", "speech-2.6-hd")
TTS_VOICE_ZH:     str = CFG.get("tts_voice_zh", "Mandarin_Female")
TTS_VOICE_JA:     str = CFG.get("tts_voice_ja", "Japanese_Female")
TTS_VOICE_EN:     str = CFG.get("tts_voice_en", "English_Female")

# ── Baby API (local BabySentinel server) ──────────────────────────────
BABY_API_URL: str = f"http://127.0.0.1:{CFG.get('web_port', 8080)}"
BABY_API_KEY: str = CFG.get("internal_api_key", "")

# ── Baby profile ──────────────────────────────────────────────────────
BABY_NAME: str = CFG.get("baby", {}).get("name", "赤ちゃん")
