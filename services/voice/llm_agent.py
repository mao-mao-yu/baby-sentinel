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
from datetime import datetime

from services.voice.llm.base import LLMProvider
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

【尿布消歧规则 / おむつ記録の解釈】
amount 和 consistency 的 enum 都含『通常』，遇到日语『普通』『ふつう』时按以下规则消歧：
1. 若用户**同时**说了性状词（『下痢』『軟便』『ゆるい』『硬い』『水様』）和『普通』
   → 性状词填 consistency，『普通』必须填 amount=通常
   例：「うんち、普通、下痢、黄色」→ amount=通常, consistency=泻, color=黄色
2. 若用户**单独**说『普通』『ふつう』『普通くらい』而无其他性状/量描述
   → 默认填 amount=通常（量比硬度更常见地用『普通』表达）
3. 若用户明确说『硬さは普通』『普通便』『いつも通りの便』
   → 填 consistency=通常

【时间处理 / 時刻処理】
- 用户明确说出时间（"3 点喝的"、"11 時 30 分にミルク"）或相对时间（"一小时前换的尿布"、"30 分前にうんち"）时，
  把发生时间换算为 24 小时制 HH:MM 填到 tool 的 time 参数（基于下方"当前时间"做基准）。
  · "下午 3 点" / 当前 14:00 → time="15:00"
  · "1 小时前" / 当前 14:30 → time="13:30"
  · "晚上 11 点" / 当前 01:00 次日 → time="23:00"（系统会自动当作昨天）
- 用户没说时间 → 不要传 time 参数（默认用当前时间记录）。

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
    def __init__(self, provider: LLMProvider) -> None:
        # provider 决定了 chat/completions 走哪家（MiniMax / DeepSeek / …）。
        # LLMAgent 自身只负责工具编排、history、time-injection 这层业务逻辑。
        self._provider = provider
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
            raw_content = msg.get("content") or ""
            reply = _strip_think(raw_content)
            needs_followup = reply.rstrip().endswith(("？", "?"))
            if not reply:
                # 诊断：finish_reason、原始 content 长度、是否全在 <think> 里
                fr = response["choices"][0].get("finish_reason")
                has_think = "<think>" in raw_content
                log.warning(f"[LLM] empty reply diagnosis:  finish_reason={fr}  "
                            f"raw_content_len={len(raw_content)}  has_think_tag={has_think}  "
                            f"raw_content={raw_content!r}")
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
        # DeepSeek thinking 模式要求 reasoning_content 必须随 round-1 的 assistant 消息一并回传，
        # 否则 round 2 会 400。MiniMax 把 think 内嵌在 content 里没有此字段，conditional add
        # 让两家都能跑。
        r1_assistant: dict = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        if msg.get("reasoning_content"):
            r1_assistant["reasoning_content"] = msg["reasoning_content"]

        r2_messages = (
            history_msgs
            + [current_user]
            + [r1_assistant]
            + tool_results
        )
        response2 = await self._chat(r2_messages)
        reply = _strip_think(response2["choices"][0]["message"].get("content", "")) or "已记录。"
        log.info(f"[LLM] Reply: {reply!r}")

        self._history.append([
            current_user,
            r1_assistant,
            *tool_results,
            {"role": "assistant", "content": reply},
        ])
        return reply, False

    async def _chat(self, messages: list) -> dict:
        # 把"当前时间"注入到 system prompt，让 LLM 能把"3点"/"一小时前"换算成绝对 HH:MM
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M %A")
        system_content = f"{_SYSTEM_PROMPT}\n\n【当前时间 / 現在時刻】{now_str}"
        return await self._provider.chat(
            messages=[{"role": "system", "content": system_content}] + messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            max_tokens=2048,
        )
