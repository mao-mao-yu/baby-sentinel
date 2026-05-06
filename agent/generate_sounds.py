"""
Generate chime WAV files used by the voice agent.
Run once to (re-)generate sounds:
    python agent/generate_sounds.py
"""
import wave
from pathlib import Path

import numpy as np

SOUNDS_DIR = Path(__file__).parent / "sounds"
SAMPLE_RATE = 16000


def _write_wav(path: Path, samples: np.ndarray) -> None:
    data = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(data.tobytes())
    print(f"  {path.name}")


def _bell(freq: float, duration: float, amplitude: float = 0.55,
          decay_rate: float = 9.0) -> np.ndarray:
    """Bell/chime tone: exponential decay + inharmonic partials."""
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)

    # Exponential ring-out (bell character)
    env = np.exp(-t * decay_rate)
    # 5 ms attack to avoid click
    fade_in = int(SAMPLE_RATE * 0.005)
    env[:fade_in] *= np.linspace(0, 1, fade_in)

    # Inharmonic partials — gives metallic bell colour vs pure sine
    tone = (
        np.sin(2 * np.pi * freq * 1.000 * t) * 1.00 +
        np.sin(2 * np.pi * freq * 2.756 * t) * 0.35 +
        np.sin(2 * np.pi * freq * 5.404 * t) * 0.12 +
        np.sin(2 * np.pi * freq * 3.000 * t) * 0.10
    )
    # Normalise so peak ≈ amplitude
    tone /= 1.57
    return tone * env * amplitude


def generate_all() -> None:
    SOUNDS_DIR.mkdir(exist_ok=True)
    print(f"Writing to {SOUNDS_DIR}/")

    # Activation: two rising notes (like Siri) — A5 then C#6
    n1 = _bell(880,  0.28, amplitude=0.52, decay_rate=11)
    gap = np.zeros(int(SAMPLE_RATE * 0.055))   # 55 ms gap
    n2 = _bell(1109, 0.35, amplitude=0.62, decay_rate=8)
    _write_wav(SOUNDS_DIR / "beep_activate.wav", np.concatenate([n1, gap, n2]))

    # Error: two descending notes
    n1 = _bell(1109, 0.25, amplitude=0.52, decay_rate=11)
    n2 = _bell(880,  0.32, amplitude=0.46, decay_rate=9)
    _write_wav(SOUNDS_DIR / "beep_error.wav", np.concatenate([n1, gap, n2]))

    print("Done.")


if __name__ == "__main__":
    generate_all()
