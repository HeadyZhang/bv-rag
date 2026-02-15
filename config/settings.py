from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    openai_api_key: str
    anthropic_api_key: str
    qdrant_url: str
    qdrant_api_key: str

    # Railway auto-injects these
    database_url: str
    redis_url: str

    # Model configuration
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    llm_model_primary: str = "claude-sonnet-4-20250514"
    llm_model_fast: str = "claude-haiku-4-5-20251001"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "ash"

    # System configuration
    port: int = 8000
    environment: str = "production"
    log_level: str = "INFO"
    max_conversation_turns: int = 10
    session_ttl_hours: int = 24

    model_config = {"env_file": ".env"}


settings = Settings()
