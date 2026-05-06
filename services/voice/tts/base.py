"""TTS provider abstract base class."""
from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        """
        Convert text to speech.

        Args:
            text: Text to synthesize.
            lang: Language code — "zh", "ja", or "en".

        Returns:
            WAV audio bytes (ready to play or stream back to the Pi).
        """
