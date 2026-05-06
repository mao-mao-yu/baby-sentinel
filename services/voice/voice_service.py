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
from services.voice.tts import get_provider

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
        _llm = LLMAgent()
    return _llm


def _get_tts():
    global _tts
    if _tts is None:
        _tts = get_provider()
    return _tts


@app.on_event("startup")
async def _startup():
    log.info(f"[VoiceService] Starting on port {cfg.VOICE_SERVICE_PORT}")
    log.info(f"[VoiceService] Whisper: {cfg.WHISPER_MODEL} / {cfg.WHISPER_DEVICE}")
    log.info(f"[VoiceService] TTS: {cfg.TTS_PROVIDER}")
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
        log.error(f"[VoiceService] LLM error: {exc}")
        return Response(status_code=503)

    # 3. Text-to-Speech
    try:
        tts_wav = await _get_tts().synthesize(reply, lang)
    except Exception as exc:
        log.error(f"[VoiceService] TTS error: {exc}")
        return Response(status_code=503)

    headers = {"X-Followup": "1"} if needs_followup else {}
    return Response(content=tts_wav, media_type="audio/wav", headers=headers)


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
