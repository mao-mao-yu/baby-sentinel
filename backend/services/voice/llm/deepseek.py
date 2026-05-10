"""DeepSeek LLM provider — uses the official OpenAI SDK (DeepSeek is OpenAI-compatible)."""
import logging
import os

from openai import AsyncOpenAI

from services.voice import config as cfg
from services.voice.llm.base import LLMProvider

log = logging.getLogger("VoiceService.LLM.DeepSeek")


class DeepSeekLLM(LLMProvider):
    def __init__(self) -> None:
        # 优先环境变量 DEEPSEEK_API_KEY（对齐官方示例风格、避免 key 进 git），
        # 没设环境变量再走 services/voice/config.json:deepseek_api_key
        api_key = os.environ.get("DEEPSEEK_API_KEY") or cfg.DEEPSEEK_API_KEY
        # AsyncOpenAI 在构造期就要求非空 api_key；若都没配置就传 placeholder，
        # 让真正的鉴权失败发生在调用 chat() 时（与 MinimaxLLM 行为一致）
        self._client = AsyncOpenAI(
            api_key=api_key or "MISSING_DEEPSEEK_API_KEY",
            base_url=cfg.DEEPSEEK_BASE_URL,
            timeout=60.0,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 2048,
        tool_choice: str = "auto",
    ) -> dict:
        kwargs: dict = {
            "model":      cfg.DEEPSEEK_MODEL,
            "messages":   messages,
            "max_tokens": max_tokens,
            "stream":     False,
        }
        if tools:
            kwargs["tools"]       = tools
            kwargs["tool_choice"] = tool_choice
        if cfg.DEEPSEEK_REASONING_EFFORT:
            kwargs["reasoning_effort"] = cfg.DEEPSEEK_REASONING_EFFORT
        if cfg.DEEPSEEK_THINKING_ENABLED:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            log.error(f"DeepSeek call failed: {type(e).__name__}: {e}")
            raise

        # AsyncOpenAI 返回 Pydantic 模型；转 dict 后与 MinimaxLLM 形状一致，
        # 上层 LLMAgent 不用关心 provider 差异
        return response.model_dump()
