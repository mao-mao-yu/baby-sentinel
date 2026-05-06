"""
STT module — faster-whisper (CUDA/CPU) or mlx-whisper (Apple Silicon).

Backend selection via config whisper_backend:
  "auto"           — mlx on macOS arm64, faster-whisper everywhere else
  "faster-whisper" — force CTranslate2 (CUDA / CPU)
  "mlx"            — force Apple MLX (macOS only)
"""
import io
import logging
import platform
import sys
import wave
from typing import Optional

import numpy as np

log = logging.getLogger("VoiceService.STT")

_MLX_REPOS = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "medium":   "mlx-community/whisper-medium-mlx",
    "small":    "mlx-community/whisper-small-mlx",
    "base":     "mlx-community/whisper-base-mlx",
    "tiny":     "mlx-community/whisper-tiny-mlx",
}

_ct2_model: Optional[object] = None   # faster-whisper WhisperModel


def _use_mlx() -> bool:
    from services.voice.config import WHISPER_BACKEND
    if WHISPER_BACKEND == "mlx":
        return True
    if WHISPER_BACKEND == "auto":
        return sys.platform == "darwin" and platform.machine() == "arm64"
    return False


def _get_ct2_model():
    global _ct2_model
    if _ct2_model is None:
        from faster_whisper import WhisperModel
        from services.voice.config import WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE
        device, compute = WHISPER_DEVICE, WHISPER_COMPUTE
        if device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA not available")
            except Exception:
                log.warning("[STT] CUDA unavailable, falling back to cpu / int8")
                device, compute = "cpu", "int8"
        log.info(f"[STT] Loading Whisper {WHISPER_MODEL} via faster-whisper on {device} ({compute}) …")
        _ct2_model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute)
        log.info("[STT] Model ready.")
    return _ct2_model


def _wav_to_float32(wav_bytes: bytes) -> np.ndarray:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


class STT:
    def __init__(self) -> None:
        if _use_mlx():
            from services.voice.config import WHISPER_MODEL
            repo = _MLX_REPOS.get(WHISPER_MODEL, f"mlx-community/whisper-{WHISPER_MODEL}-mlx")
            log.info(f"[STT] Backend: mlx-whisper  repo={repo}")
            # mlx downloads/caches on first inference; trigger it now so startup reveals errors early
            import mlx_whisper
            silence = np.zeros(16000, dtype=np.float32)
            mlx_whisper.transcribe(silence, path_or_hf_repo=repo, verbose=False)
            log.info("[STT] mlx-whisper ready.")
        else:
            _get_ct2_model()

    async def transcribe(self, wav_bytes: bytes) -> tuple[str, str]:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, wav_bytes)

    def _transcribe_sync(self, wav_bytes: bytes) -> tuple[str, str]:
        if _use_mlx():
            text, lang = self._transcribe_mlx(wav_bytes)
        else:
            text, lang = self._transcribe_ct2(wav_bytes)

        if lang not in ("zh", "ja"):
            log.info(f"[STT] Detected '{lang}', re-running forced zh")
            if _use_mlx():
                text, lang = self._transcribe_mlx(wav_bytes, force_lang="zh")
            else:
                text, lang = self._transcribe_ct2(wav_bytes, force_lang="zh")

        log.info(f"[STT] [{lang}] {text!r}")
        return text, lang

    def _transcribe_ct2(self, wav_bytes: bytes, force_lang: str | None = None) -> tuple[str, str]:
        from services.voice.config import WHISPER_BEAM_SIZE, WHISPER_INITIAL_PROMPT
        model = _get_ct2_model()
        audio = _wav_to_float32(wav_bytes)
        segments, info = model.transcribe(
            audio,
            language=force_lang,
            initial_prompt=WHISPER_INITIAL_PROMPT,
            beam_size=WHISPER_BEAM_SIZE,
            temperature=0.0,                        # deterministic; no hallucination escalation
            condition_on_previous_text=False,       # prevent short-clip cross-contamination
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            no_speech_threshold=0.6,
        )
        text = "".join(s.text for s in segments).strip()
        return text, force_lang or (info.language or "zh")

    def _transcribe_mlx(self, wav_bytes: bytes, force_lang: str | None = None) -> tuple[str, str]:
        import mlx_whisper
        from services.voice.config import WHISPER_MODEL, WHISPER_BEAM_SIZE, WHISPER_INITIAL_PROMPT
        repo  = _MLX_REPOS.get(WHISPER_MODEL, f"mlx-community/whisper-{WHISPER_MODEL}-mlx")
        audio = _wav_to_float32(wav_bytes)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=repo,
            language=force_lang,
            initial_prompt=WHISPER_INITIAL_PROMPT,
            beam_size=WHISPER_BEAM_SIZE,
            temperature=0.0,
            condition_on_previous_text=False,
            verbose=False,
        )
        text = result.get("text", "").strip()
        lang = force_lang or result.get("language") or "zh"
        return text, lang
