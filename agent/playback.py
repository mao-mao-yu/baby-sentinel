"""Audio playback — beep files and TTS WAV responses."""
import io
import time
import wave

import pyaudio


class Playback:
    def __init__(self) -> None:
        self._pa = pyaudio.PyAudio()

    def play_file(self, path: str) -> None:
        with open(path, "rb") as f:
            self.play_bytes(f.read())

    def play_bytes(self, data: bytes) -> None:
        buf = io.BytesIO(data)
        with wave.open(buf, "rb") as wf:
            stream = self._pa.open(
                format=self._pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
            )
            try:
                chunk = 1024
                total_frames = 0
                audio = wf.readframes(chunk)
                while audio:
                    total_frames += len(audio) // (wf.getsampwidth() * wf.getnchannels())
                    stream.write(audio)
                    audio = wf.readframes(chunk)
                # wait for hardware output buffer to drain before closing
                drain_s = total_frames / wf.getframerate()
                time.sleep(drain_s * 0.5 + 0.05)
            finally:
                stream.stop_stream()
                stream.close()

    def close(self) -> None:
        self._pa.terminate()
