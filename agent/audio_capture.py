"""
Audio capture with WebRTC VAD-based end-of-speech detection.
Reads from ReSpeaker (or system default) via PyAudio.
"""
import io
import wave
from typing import Optional

import pyaudio
import webrtcvad

from agent.config import SAMPLE_RATE, CHUNK_SIZE, CHANNELS

# WebRTC VAD requires exact 10/20/30 ms frames at supported sample rates
_VAD_MS    = 30
_VAD_SAMP  = SAMPLE_RATE * _VAD_MS // 1000   # 480 samples @ 16 kHz
_VAD_BYTES = _VAD_SAMP * 2                    # 960 bytes (int16)


class AudioCapture:
    def __init__(self, device_index: Optional[int] = None) -> None:
        self._pa = pyaudio.PyAudio()
        if device_index is not None:
            self._device = device_index
        else:
            self._device = self._find_respeaker()

        name = "auto-detect ReSpeaker"
        if self._device is not None:
            info = self._pa.get_device_info_by_index(self._device)
            name = info["name"]
        print(f"[AudioCapture] Input device: [{self._device}] {name}")

    def _find_respeaker(self) -> Optional[int]:
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0 and "respeaker" in info["name"].lower():
                return i
        return None  # falls back to system default

    def open_stream(self) -> pyaudio.Stream:
        return self._pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=self._device,
            frames_per_buffer=CHUNK_SIZE,
        )

    def record_until_silence(
        self,
        stream: pyaudio.Stream,
        _silence_threshold: int = 200,   # unused (WebRTC VAD replaces RMS), kept for API compat
        silence_duration: float = 2.0,
        max_duration: float = 15.0,
    ) -> bytes:
        """
        Record until silence_duration seconds of non-speech (WebRTC VAD),
        or max_duration seconds total.
        Returns WAV bytes (16 kHz, mono, int16).

        VAD aggressiveness 2 = good balance between cutting off too early
        and waiting too long after the user stops speaking.
        Min-speech guard (MIN_SPEECH_FRAMES) prevents noise right after the
        activation beep from immediately triggering the silence counter.
        """
        vad = webrtcvad.Vad(2)  # aggressiveness 0–3

        silence_needed  = int(silence_duration * 1000 / _VAD_MS)
        max_chunks      = int(max_duration * SAMPLE_RATE / CHUNK_SIZE)
        MIN_SPEECH_FRAMES = 5   # 5 × 30 ms = 150 ms of speech before silence counts

        all_frames: list[bytes] = []
        vad_buf        = b""
        speech_count   = 0
        silence_count  = 0

        for _ in range(max_chunks):
            raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            all_frames.append(raw)
            vad_buf += raw

            while len(vad_buf) >= _VAD_BYTES:
                frame   = vad_buf[:_VAD_BYTES]
                vad_buf = vad_buf[_VAD_BYTES:]

                try:
                    is_speech = vad.is_speech(frame, SAMPLE_RATE)
                except Exception:
                    is_speech = False

                if is_speech:
                    speech_count += 1
                    silence_count = 0
                else:
                    if speech_count >= MIN_SPEECH_FRAMES:
                        silence_count += 1
                        if silence_count >= silence_needed:
                            return self._frames_to_wav(all_frames)

        return self._frames_to_wav(all_frames)

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self._pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def close(self) -> None:
        self._pa.terminate()
