"""OpenAI Text-to-Speech service."""
import logging
import re
from typing import Generator

import openai

logger = logging.getLogger(__name__)


class TTSService:
    MARITIME_INSTRUCTIONS = (
        "Speak clearly and at a moderate pace. "
        "When reading regulation numbers like 'II-1/3-6' or 'SOLAS Chapter XII', "
        "pronounce each part distinctly with a brief pause between segments. "
        "Emphasize numerical values such as dimensions, tonnage, and dates. "
        "Maintain a professional, authoritative tone."
    )

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "ash",
    ):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.model = model
        self.voice = voice

    def synthesize(self, text: str, output_format: str = "mp3") -> bytes:
        try:
            response = self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                instructions=self.MARITIME_INSTRUCTIONS,
                response_format=output_format,
            )
            return response.content
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            raise

    def synthesize_stream(self, text: str, output_format: str = "mp3") -> Generator[bytes, None, None]:
        try:
            response = self.client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                instructions=self.MARITIME_INSTRUCTIONS,
                response_format=output_format,
            )
            yield from response.iter_bytes(chunk_size=4096)
        except Exception as e:
            logger.error(f"TTS stream error: {e}")
            raise

    @staticmethod
    def prepare_tts_text(answer: str, max_length: int = 1500) -> str:
        text = answer

        source_patterns = [
            r"\n*参考来源.*$",
            r"\n*Sources:.*$",
            r"\n*References:.*$",
        ]
        for pattern in source_patterns:
            text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"#{1,6}\s*", "", text)
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[-*]\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\[([^\]]+)\]", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) > max_length:
            truncated = text[:max_length]
            last_period = truncated.rfind(".")
            if last_period > max_length * 0.5:
                text = truncated[:last_period + 1]
            else:
                text = truncated

        return text
