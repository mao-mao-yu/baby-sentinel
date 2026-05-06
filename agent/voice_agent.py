"""
Voice Agent — runs on Raspberry Pi.

Loop:
  1. Feed mic chunks to openwakeword
  2. score >= WAKE_THRESHOLD → play activation beep → record until silence
  3. POST WAV to voice_service → receive TTS WAV → play back
  4. On error → play error beep

Usage:
    python agent/voice_agent.py
    python agent/voice_agent.py --device 1   # specific audio device index
    python agent/voice_agent.py --list-devices
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import openwakeword
from openwakeword.model import Model as OWWModel

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from agent.config import (
    VOICE_SERVICE_URL,
    WAKE_MODEL_PATH,
    WAKE_THRESHOLD,
    WAKE_CONFIRM_FRAMES,
    WAKE_PEAK_THRESHOLD,
    SAMPLE_RATE,
    CHUNK_SIZE,
    SILENCE_RMS,
    SILENCE_S,
    MAX_RECORD_S,
    REQUEST_TIMEOUT_S,
    COOLDOWN_S,
)
from agent.audio_capture import AudioCapture
from agent.playback import Playback

log = logging.getLogger("VoiceAgent")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%H:%M:%S",
)

_SOUNDS = Path(__file__).parent / "sounds"
_BEEP_ACTIVATE = str(_SOUNDS / "beep_activate.wav")
_BEEP_ERROR    = str(_SOUNDS / "beep_error.wav")


def _ensure_sounds() -> None:
    if not (_SOUNDS / "beep_activate.wav").exists():
        from agent.generate_sounds import generate_all
        generate_all()


def _list_devices() -> None:
    import pyaudio
    pa = pyaudio.PyAudio()
    print(f"{'Index':<6} {'Name':<50} In-Ch")
    print("-" * 65)
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            marker = " ◄ ReSpeaker" if "respeaker" in info["name"].lower() else ""
            print(f"  {i:<4} {info['name'][:49]:<50}{marker}")
    pa.terminate()


async def _post_audio(wav: bytes) -> tuple[bytes, bool] | None:
    """
    Returns (audio_bytes, needs_followup), or None on error.
    audio_bytes=b"" means no speech detected (stay silent).
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            r = await client.post(
                f"{VOICE_SERVICE_URL}/voice/process",
                files={"audio": ("audio.wav", wav, "audio/wav")},
            )
        if r.status_code == 200:
            followup = r.headers.get("X-Followup") == "1"
            return r.content, followup
        if r.status_code == 204:
            log.info("[VoiceAgent] No speech detected, skipping")
            return b"", False
        log.error(f"[VoiceAgent] Service {r.status_code}: {r.text[:200]}")
    except httpx.TimeoutException:
        log.error("[VoiceAgent] Request timed out")
    except httpx.ConnectError:
        log.error(f"[VoiceAgent] Cannot reach voice_service at {VOICE_SERVICE_URL}")
    except Exception as exc:
        log.error(f"[VoiceAgent] {exc}")
    return None


async def run(device_index: int | None = None) -> None:
    _ensure_sounds()

    log.info("[VoiceAgent] Loading wake word model …")
    oww = OWWModel(wakeword_model_paths=[WAKE_MODEL_PATH])
    model_key = Path(WAKE_MODEL_PATH).stem

    capture  = AudioCapture(device_index)
    playback = Playback()
    stream   = capture.open_stream()
    cooldown_until  = 0.0
    confirm_counter = 0
    confirm_peak    = 0.0

    log.info(
        f"[VoiceAgent] Listening — model={model_key}  "
        f"threshold={WAKE_THRESHOLD}  confirm={WAKE_CONFIRM_FRAMES}f  "
        f"peak={WAKE_PEAK_THRESHOLD}  service={VOICE_SERVICE_URL}"
    )

    try:
        while True:
            raw   = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            chunk = np.frombuffer(raw, dtype=np.int16)
            preds = oww.predict(chunk)
            score = preds.get(model_key, 0.0)

            if time.monotonic() < cooldown_until:
                confirm_counter = 0
                confirm_peak    = 0.0
                continue

            if score >= WAKE_THRESHOLD:
                confirm_counter += 1
                confirm_peak = max(confirm_peak, score)
            else:
                confirm_counter = 0
                confirm_peak    = 0.0

            if confirm_counter < WAKE_CONFIRM_FRAMES:
                continue
            if confirm_peak < WAKE_PEAK_THRESHOLD:
                # enough consecutive frames but no strong peak → noise, reset
                confirm_counter = 0
                confirm_peak    = 0.0
                continue

            confirm_counter = 0
            confirm_peak    = 0.0
            log.info(f"[VoiceAgent] Wake word detected (score={score:.3f})")
            playback.play_file(_BEEP_ACTIVATE)

            log.info("[VoiceAgent] Recording …")
            wav = capture.record_until_silence(
                stream,
                _silence_threshold=SILENCE_RMS,
                silence_duration=SILENCE_S,
                max_duration=MAX_RECORD_S,
            )
            log.info(f"[VoiceAgent] Captured {len(wav) // 1024} KB — sending …")

            result = await _post_audio(wav)
            if result is None:
                playback.play_file(_BEEP_ERROR)
            else:
                tts, needs_followup = result
                log.info(f"[VoiceAgent] tts={len(tts)} bytes  needs_followup={needs_followup}")
                if tts:
                    playback.play_bytes(tts)
                if needs_followup:
                    log.info("[VoiceAgent] Follow-up — recording again …")
                    playback.play_file(_BEEP_ACTIVATE)
                    wav2 = capture.record_until_silence(
                        stream,
                        _silence_threshold=SILENCE_RMS,
                        silence_duration=SILENCE_S,
                        max_duration=MAX_RECORD_S,
                    )
                    result2 = await _post_audio(wav2)
                    if result2 is None:
                        playback.play_file(_BEEP_ERROR)
                    elif result2[0]:
                        playback.play_bytes(result2[0])

            cooldown_until = time.monotonic() + COOLDOWN_S

    except KeyboardInterrupt:
        log.info("[VoiceAgent] Stopped.")
    finally:
        stream.stop_stream()
        stream.close()
        capture.close()
        playback.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=None,
                        help="Audio device index (default: auto-detect ReSpeaker)")
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()

    if args.list_devices:
        _list_devices()
    else:
        asyncio.run(run(args.device))
