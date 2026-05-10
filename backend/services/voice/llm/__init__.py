"""LLM provider package — chat/completions backends for tool-calling LLMAgent."""
from services.voice.llm.base import LLMProvider


def get_provider(name: str = "") -> LLMProvider:
    """Return LLM provider by name (falls back to config.LLM_PROVIDER)."""
    from services.voice import config as cfg
    key = (name or cfg.LLM_PROVIDER).lower()
    if key == "minimax":
        from services.voice.llm.minimax import MinimaxLLM
        return MinimaxLLM()
    if key == "deepseek":
        from services.voice.llm.deepseek import DeepSeekLLM
        return DeepSeekLLM()
    raise ValueError(f"Unknown LLM provider: {key!r}. Choose 'minimax' or 'deepseek'.")
