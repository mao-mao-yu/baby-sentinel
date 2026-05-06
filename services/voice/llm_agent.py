"""
LLM Agent — MiniMax chat completions + tool calling.

Flow:
  1. Send transcribed text + tool definitions to MiniMax LLM
  2. LLM responds with tool_calls → execute each against BabySentinel API
  3. Send tool results back → LLM generates confirmation text
  4. Return confirmation text (will be fed to TTS)

History: last 3 turns are kept so users can say "撤销刚刚" etc.
"""
import json
import logging
import re
from collections import deque

import httpx

from services.voice import config as cfg
from services.voice.tools.baby_records import TOOL_DEFINITIONS, execute_tool

log = logging.getLogger("VoiceService.LLM")

_SYSTEM_PROMPT = """你是育儿助手，通过语音帮父母记录宝宝日常。

【⚠️ 最高优先级：你没有能力用文字提问】
信息不完整时，唯一方式是调用 request_followup 工具，绝对禁止直接输出问句。

【追问措辞 — 调 request_followup 时使用以下原文】
· 未说奶量        → "喝了多少毫升？"          /「何mlですか？」
· 未说哺乳侧/时长  → "左乳还是右乳，喂了多少分钟？" /「左右どちらで何分ですか？」
· 未说尿/便便     → "是尿、便便、还是都有？"    /「おしっこ、うんち、両方？」
· 未说体温数值     → "多少度？"               /「何度ですか？」

【工具选择由 tool description 决定，意图不明时礼貌说没听清，不要乱猜】

【语言规则】
- 只输出纯文字，禁止 emoji，句尾必须有标点。
- 用户说中文 → 全程中文；用户说日语 → 全程日语，禁止中日混用。
- 日语术语：配方奶=粉ミルク、瓶喂=ボトル授乳、母乳=直接授乳、オムツ、うんち、ねんね。

【回复格式】工具调用后一句话确认，20字以内。
  中文示例："已记录配方奶90毫升。" "已记录左乳哺乳15分钟。" "已记录换尿布（尿）。"
  日語示例："粉ミルク90mlを記録しました。" "左授乳15分を記録しました。" """

_HISTORY_TURNS = 3   # number of complete turns to retain
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


class LLMAgent:
    def __init__(self) -> None:
        # Each element is a list of messages representing one complete turn:
        # [user_msg, assistant_msg(±tool_calls), *tool_results, assistant_final_msg]
        self._history: deque[list[dict]] = deque(maxlen=_HISTORY_TURNS)

    async def process(self, text: str, lang: str = "zh") -> tuple[str, bool]:
        """
        Process transcribed text through LLM → tool calling → confirmation.

        Returns:
            (reply_text, needs_followup)
            needs_followup=True means the agent should play beep and record again.
        """
        history_msgs = [m for turn in self._history for m in turn]
        current_user = {"role": "user", "content": text}

        # Round 1: LLM decides which tools to call
        response = await self._chat(history_msgs + [current_user])
        msg = response["choices"][0]["message"]

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            reply = _strip_think(msg.get("content", "没有听清楚，请再说一次。"))
            needs_followup = reply.rstrip().endswith(("？", "?"))
            log.info(f"[LLM] no tool_calls — reply={reply!r}  needs_followup={needs_followup}")
            self._history.append([current_user, {"role": "assistant", "content": reply}])
            return reply, needs_followup

        # Intercept request_followup before executing other tools
        followup_tc = next((tc for tc in tool_calls
                            if tc["function"]["name"] == "request_followup"), None)
        log.info(f"[LLM] tool_calls={[tc['function']['name'] for tc in tool_calls]}  request_followup={'YES' if followup_tc else 'NO'}")
        if followup_tc:
            args = json.loads(followup_tc["function"].get("arguments", "{}"))
            question = _strip_think(args.get("question", ""))
            log.info(f"[LLM] Follow-up requested: {question!r}")
            self._history.append([current_user, {"role": "assistant", "content": question}])
            return question, True

        # Execute regular tool calls
        tool_results = []
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"].get("arguments", "{}"))
            ok, result = execute_tool(fn_name, fn_args)
            log.info(f"[LLM] Tool {fn_name}({fn_args}) → {'ok' if ok else 'fail'}: {result}")
            tool_results.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      result,
            })

        # Round 2: LLM generates confirmation with tool results
        r2_messages = (
            history_msgs
            + [current_user]
            + [{"role": "assistant", "content": None, "tool_calls": tool_calls}]
            + tool_results
        )
        response2 = await self._chat(r2_messages)
        reply = _strip_think(response2["choices"][0]["message"].get("content", "")) or "已记录。"
        log.info(f"[LLM] Reply: {reply!r}")

        self._history.append([
            current_user,
            {"role": "assistant", "content": None, "tool_calls": tool_calls},
            *tool_results,
            {"role": "assistant", "content": reply},
        ])
        return reply, False

    async def _chat(self, messages: list) -> dict:
        base = cfg.MINIMAX_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.MINIMAX_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       cfg.MINIMAX_LLM_MODEL,
                    "messages":    [{"role": "system", "content": _SYSTEM_PROMPT}] + messages,
                    "tools":       TOOL_DEFINITIONS,
                    "tool_choice": "auto",
                    "max_tokens":  256,
                },
            )
        if r.status_code >= 400:
            log.error(f"[LLM] HTTP {r.status_code}: {r.text[:600]}")
        r.raise_for_status()
        data = r.json()
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(
                f"MiniMax error {base_resp.get('status_code')}: "
                f"{base_resp.get('status_msg', '')} | body: {data}"
            )
        if not data.get("choices"):
            log.error(f"[LLM] Unexpected response (no choices): {data}")
            raise RuntimeError(f"MiniMax returned no choices: {data}")
        return data
