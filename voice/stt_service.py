"""OpenAI Speech-to-Text service."""
import io
import logging
import time

import openai

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self, openai_api_key: str, model: str = "gpt-4o-mini-transcribe"):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.model = model
        self.fallback_model = "whisper-1"

    async def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "webm",
        language: str | None = None,
    ) -> dict:
        start = time.time()
        audio_file = io.BytesIO(audio_data)
        audio_file.name = f"audio.{audio_format}"

        kwargs = {"model": self.model, "file": audio_file}
        if language:
            kwargs["language"] = language

        model_used = self.model
        try:
            response = self.client.audio.transcriptions.create(**kwargs)
        except Exception as e:
            logger.warning(f"STT with {self.model} failed: {e}, falling back to {self.fallback_model}")
            audio_file.seek(0)
            kwargs["model"] = self.fallback_model
            model_used = self.fallback_model
            try:
                response = self.client.audio.transcriptions.create(**kwargs)
            except Exception as e2:
                logger.error(f"STT fallback also failed: {e2}")
                raise

        latency_ms = int((time.time() - start) * 1000)

        text = response.text if hasattr(response, "text") else str(response)

        return {
            "text": text,
            "language": language or "auto",
            "model_used": model_used,
            "latency_ms": latency_ms,
        }
