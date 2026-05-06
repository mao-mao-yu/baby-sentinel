from services.voice.tts.base import TTSProvider
from services.voice.tts.minimax import MinimaxTTSProvider
from services.voice.tts.edge import EdgeTTSProvider


def get_provider(name: str = "") -> TTSProvider:
    """Return TTS provider by name (falls back to config.TTS_PROVIDER)."""
    from services.voice import config as cfg
    key = (name or cfg.TTS_PROVIDER).lower()
    if key == "minimax":
        return MinimaxTTSProvider()
    if key == "edge":
        return EdgeTTSProvider()
    raise ValueError(f"Unknown TTS provider: {key!r}. Choose 'minimax' or 'edge'.")
