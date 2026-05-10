"""LLM provider abstract base — OpenAI-compatible chat completions interface."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 2048,
        tool_choice: str = "auto",
    ) -> dict:
        """
        Issue a chat-completions request.

        Returns an OpenAI-compatible response dict:
            {"choices": [{"message": {"content"|"tool_calls": ...},
                           "finish_reason": "..."}],
             "usage": {...}}

        Implementations are expected to:
          - raise on transport errors / non-success API responses
          - convert vendor-specific responses to the canonical shape above
            (so LLMAgent never has to branch on provider)
        """
