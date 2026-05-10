"""EdgeTTS fallback provider — free, no API key required."""
import gc
import io
import tempfile
import time
import wave
from pathlib import Path

import edge_tts
import librosa
import numpy as np

from services.voice.tts.base import TTSProvider

_VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "en": "en-US-JennyNeural",
}


class EdgeTTSProvider(TTSProvider):
    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        voice = _VOICES.get(lang, _VOICES["zh"])
        comm = edge_tts.Communicate(text, voice=voice)

        # Collect MP3 bytes via stream — avoids edge_tts holding a file handle
        mp3_bytes = bytearray()
        async for chunk_type, chunk_data in comm.stream():
            if chunk_type == "audio":
                mp3_bytes.extend(chunk_data)

        # Write to temp file ourselves (audioread backend needs a path, not BytesIO)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(mp3_bytes)
            mp3_path = Path(tmp.name)

        try:
            # Convert MP3 → WAV (16 kHz mono) for consistent playback on Pi
            audio, _ = librosa.load(str(mp3_path), sr=16000, mono=True)
            audio = (np.clip(audio, -1, 1) * 32767).astype(np.int16)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio.tobytes())
            return buf.getvalue()
        finally:
            # Release audioread handles before unlinking (Windows file lock fix)
            gc.collect()
            for _ in range(5):
                try:
                    mp3_path.unlink(missing_ok=True)
                    break
                except OSError:
                    time.sleep(0.1)
