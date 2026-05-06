"""
Background white-noise keep-alive — prevents Bluetooth/wireless speakers from
auto-sleeping during silent periods.

Daemon thread continuously writes very-low-amplitude white noise to the default
audio output. ALSA / USB audio class allows only one open stream per device, so
foreground playback (TTS/beeps) calls pause() to release the device, then resume()
when finished. Playback wraps this transparently.
"""
import logging
import threading
import time

import numpy as np
import pyaudio

log = logging.getLogger("WhiteNoise")


class WhiteNoiseKeepAlive:
    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        amplitude: float = 0.005,
        chunk_ms: int = 100,
        output_device_index: int | None = None,
    ):
        self._sr = sample_rate
        # Clamp amplitude into [0.0001, 0.5] — very loud noise would be a UX disaster
        self._amp = max(0.0001, min(amplitude, 0.5))
        self._chunk = int(sample_rate * chunk_ms / 1000)
        self._device = output_device_index
        self._pa = pyaudio.PyAudio()
        self._stop = threading.Event()
        self._active = threading.Event()
        self._active.set()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="WhiteNoise")
        self._thread.start()
        log.info(f"[WhiteNoise] started  amp={self._amp}  rate={self._sr}Hz")

    def stop(self) -> None:
        self._stop.set()
        self._active.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        try:
            self._pa.terminate()
        except Exception:
            pass

    def pause(self) -> None:
        """Release the audio device so foreground playback can grab it."""
        self._active.clear()
        # Brief wait for the noise thread to close its stream before caller opens its own
        time.sleep(0.05)

    def resume(self) -> None:
        self._active.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._active.wait()
            if self._stop.is_set():
                break

            stream = None
            try:
                stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self._sr,
                    output=True,
                    output_device_index=self._device,
                )
            except OSError as e:
                # Device busy or rate unsupported; back off and retry
                log.debug(f"[WhiteNoise] open failed ({e}), retry in 1s")
                time.sleep(1.0)
                continue

            try:
                while self._active.is_set() and not self._stop.is_set():
                    samples = (np.random.randn(self._chunk) * self._amp * 32767).astype(np.int16)
                    stream.write(samples.tobytes())
            except OSError:
                pass
            finally:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
