"""
MiniMax TTS provider — WebSocket streaming (t2a_v2).

Flow: connect → task_start → task_continue (text) → receive hex audio chunks
      until is_final → task_finish → decode MP3 → WAV
"""
import io
import json
import logging
import ssl
import wave

import librosa
import numpy as np
import websockets

from services.voice.tts.base import TTSProvider
from services.voice import config as cfg

log = logging.getLogger("VoiceService.TTS")

_WS_URL = "wss://api.minimaxi.com/ws/v1/t2a_v2"

_VOICES = {
    "zh": lambda: cfg.TTS_VOICE_ZH,
    "ja": lambda: cfg.TTS_VOICE_JA,
    "en": lambda: cfg.TTS_VOICE_EN,
}


def _mp3_bytes_to_wav(mp3_bytes: bytes, sample_rate: int = 32000) -> bytes:
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        tmp_path.write_bytes(mp3_bytes)
        audio, _ = librosa.load(str(tmp_path), sr=sample_rate, mono=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class MinimaxTTSProvider(TTSProvider):
    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        voice_id = _VOICES.get(lang, _VOICES["zh"])()

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        headers = {"Authorization": f"Bearer {cfg.MINIMAX_API_KEY}"}
        audio_chunks: list[bytes] = []

        async with websockets.connect(
            _WS_URL, additional_headers=headers, ssl=ssl_ctx
        ) as ws:
            # ── Handshake ──────────────────────────────────────────────
            msg = json.loads(await ws.recv())
            if msg.get("event") != "connected_success":
                raise RuntimeError(f"TTS WS connect failed: {msg}")

            # ── Start task ─────────────────────────────────────────────
            await ws.send(json.dumps({
                "event": "task_start",
                "model": cfg.TTS_MODEL,
                "voice_setting": {
                    "voice_id": voice_id,
                    "speed": 1.0, "vol": 1.0, "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 32000, "bitrate": 128000,
                    "format": "mp3", "channel": 1,
                },
            }))
            msg = json.loads(await ws.recv())
            if msg.get("event") != "task_started":
                raise RuntimeError(f"TTS task_start failed: {msg}")

            # ── Send text ──────────────────────────────────────────────
            await ws.send(json.dumps({"event": "task_continue", "text": text + ","}))

            # ── Receive audio chunks ───────────────────────────────────
            while True:
                msg = json.loads(await ws.recv())
                audio_hex = (msg.get("data") or {}).get("audio", "")
                if audio_hex:
                    audio_chunks.append(bytes.fromhex(audio_hex))
                if msg.get("is_final"):
                    try:
                        await ws.send(json.dumps({"event": "task_finish"}))
                    except Exception:
                        pass
                    break

        if not audio_chunks:
            raise RuntimeError("TTS: no audio received from WebSocket")

        log.info(f"[TTS] Received {len(audio_chunks)} chunks, converting to WAV")
        return _mp3_bytes_to_wav(b"".join(audio_chunks))
