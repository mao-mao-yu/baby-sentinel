"""
Voice Service — FastAPI microservice running on the server.

Receives WAV audio from voice_agent (Pi):
  POST /voice/process  →  STT → LLM tool calling → TTS  →  returns WAV

Usage:
    python voice/voice_service.py
    uvicorn voice.voice_service:app --host 0.0.0.0 --port 8001 --reload
"""
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from services.voice import config as cfg
from services.voice.stt import STT
from services.voice.llm_agent import LLMAgent
from services.voice.llm import get_provider as get_llm_provider
from services.voice.tts import get_provider as get_tts_provider

log = logging.getLogger("VoiceService")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="BabySentinel Voice Service", version="1.0")

# Lazy-init singletons (loaded once at first request to avoid blocking startup)
_stt: STT | None = None
_llm: LLMAgent | None = None
_tts = None


def _get_stt() -> STT:
    global _stt
    if _stt is None:
        _stt = STT()
    return _stt


def _get_llm() -> LLMAgent:
    global _llm
    if _llm is None:
        _llm = LLMAgent(get_llm_provider())
    return _llm


def _get_tts():
    global _tts
    if _tts is None:
        _tts = get_tts_provider()
    return _tts


@app.on_event("startup")
async def _startup():
    log.info(f"[VoiceService] Starting on port {cfg.VOICE_SERVICE_PORT}")
    log.info(f"[VoiceService] Whisper: {cfg.WHISPER_MODEL} / {cfg.WHISPER_DEVICE} / backend={cfg.WHISPER_BACKEND}")
    if cfg.LLM_PROVIDER == "minimax":
        log.info(f"[VoiceService] LLM: minimax / {cfg.MINIMAX_LLM_MODEL}  @ {cfg.MINIMAX_BASE_URL}  key={'set' if cfg.MINIMAX_API_KEY else 'MISSING'}")
    elif cfg.LLM_PROVIDER == "deepseek":
        log.info(f"[VoiceService] LLM: deepseek / {cfg.DEEPSEEK_MODEL}  @ {cfg.DEEPSEEK_BASE_URL}  "
                 f"reasoning={cfg.DEEPSEEK_REASONING_EFFORT or 'off'}  thinking={cfg.DEEPSEEK_THINKING_ENABLED}  "
                 f"key={'set' if cfg.DEEPSEEK_API_KEY else 'MISSING'}")
    else:
        log.warning(f"[VoiceService] LLM: unknown provider {cfg.LLM_PROVIDER!r}")
    log.info(f"[VoiceService] TTS: {cfg.TTS_PROVIDER} / {cfg.TTS_MODEL}")
    log.info(f"[VoiceService] Baby API: {cfg.BABY_API_URL}")
    # Load Whisper in thread pool so the event loop stays unblocked during startup
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, _get_stt)
    log.info("[VoiceService] Ready.")


@app.post("/voice/process", response_class=Response)
async def process_voice(audio: UploadFile = File(...)) -> Response:
    """
    Main endpoint called by voice_agent.py on the Pi.
    Accepts multipart WAV, returns WAV TTS audio.
    """
    wav_bytes = await audio.read()
    if len(wav_bytes) < 1000:
        raise HTTPException(400, "Audio too short")

    # 1. Speech-to-Text
    text, lang = await _get_stt().transcribe(wav_bytes)
    if not text:
        log.info("[VoiceService] No speech detected, ignoring")
        return Response(status_code=204)   # agent will stay silent (no error beep)

    # 2. LLM + tool calling
    try:
        reply, needs_followup = await _get_llm().process(text, lang)
    except Exception as exc:
        log.error(f"[VoiceService] LLM error: {type(exc).__name__}: {exc}", exc_info=True)
        return Response(status_code=503)

    # LLM 返回空文本时跳过 TTS（agent 静默，与"无语音"分支一致）
    if not reply or not reply.strip():
        log.info("[VoiceService] LLM returned empty reply, skipping TTS")
        return Response(status_code=204)

    # 3. Text-to-Speech
    try:
        tts_wav = await _get_tts().synthesize(reply, lang)
    except Exception as exc:
        log.error(f"[VoiceService] TTS error: {type(exc).__name__}: {exc}", exc_info=True)
        return Response(status_code=503)

    headers = {"X-Followup": "1"} if needs_followup else {}
    return Response(content=tts_wav, media_type="audio/wav", headers=headers)


@app.post("/voice/test_llm")
async def test_llm(payload: dict) -> dict:
    """
    Debug endpoint: LLM tool-call chain only. 跳过 STT 和 TTS。

    Body: {"text": "记录配方奶 90 毫升", "lang": "zh"}
    Resp: {"reply": "...", "needs_followup": false, "elapsed_s": 2.31}

    工具会真实执行（写入 baby_log），不是 dry-run。要撤销说"撤销"或调 delete_last_entry。
    LLM 的 tool_calls 详情看 voice service 日志。
    """
    import time
    text = (payload.get("text") or "").strip()
    lang = payload.get("lang") or "zh"
    if not text:
        raise HTTPException(400, "missing 'text' field")

    log.info(f"[test_llm] in: text={text!r}  lang={lang}")
    t0 = time.time()
    try:
        reply, needs_followup = await _get_llm().process(text, lang)
    except Exception as exc:
        elapsed = time.time() - t0
        log.error(f"[test_llm] LLM error after {elapsed:.2f}s: {type(exc).__name__}: {exc}",
                  exc_info=True)
        raise HTTPException(503, f"LLM error: {type(exc).__name__}: {exc}")
    elapsed = round(time.time() - t0, 2)
    log.info(f"[test_llm] out: reply={reply!r}  needs_followup={needs_followup}  elapsed={elapsed}s")
    return {
        "text_in":         text,
        "lang":            lang,
        "reply":           reply,
        "needs_followup":  needs_followup,
        "elapsed_s":       elapsed,
    }


@app.get("/health")
async def health():
    return {"ok": True, "whisper": cfg.WHISPER_MODEL, "tts": cfg.TTS_PROVIDER}


if __name__ == "__main__":
    uvicorn.run(
        "services.voice.voice_service:app",
        host="0.0.0.0",
        port=cfg.VOICE_SERVICE_PORT,
        reload=False,
    )
