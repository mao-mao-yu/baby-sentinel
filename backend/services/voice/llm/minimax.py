"""MiniMax LLM provider — direct httpx call against /v1/chat/completions."""
import logging

import httpx

from services.voice import config as cfg
from services.voice.llm.base import LLMProvider

log = logging.getLogger("VoiceService.LLM.MiniMax")


class MinimaxLLM(LLMProvider):
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 2048,
        tool_choice: str = "auto",
    ) -> dict:
        base = cfg.MINIMAX_BASE_URL.rstrip("/")
        payload: dict = {
            "model":      cfg.MINIMAX_LLM_MODEL,
            "messages":   messages,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = tool_choice

        # M2.7 thinking 模型在多事件复杂请求下 LLM 阶段 ~30s，给 60s 余量
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.MINIMAX_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )

        if r.status_code >= 400:
            log.error(f"HTTP {r.status_code}: {r.text[:600]}")
        r.raise_for_status()

        data = r.json()
        # MiniMax-specific：200 OK 仍可能在 base_resp 里携带错误码
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(
                f"MiniMax error {base_resp.get('status_code')}: "
                f"{base_resp.get('status_msg', '')} | body: {data}"
            )
        if not data.get("choices"):
            log.error(f"Unexpected response (no choices): {data}")
            raise RuntimeError(f"MiniMax returned no choices: {data}")
        return data
