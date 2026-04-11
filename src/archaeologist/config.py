"""Application configuration via environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Endpoint
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_auth_token: str = ""

    # Models
    extraction_model: str = "claude-4.6-sonnet"
    synthesis_model: str = "claude-4.6-opus"
    refinement_model: str = "claude-4.6-opus"
    embedding_model: str = "text-embedding-3-large"

    # Infrastructure
    database_url: str = "postgresql://archaeologist:archaeologist@localhost:5432/session_archaeologist"
    redis_url: str = "redis://localhost:6379/0"

    # Pipeline
    max_parallel_extractions: int = 5
    cost_confirmation_threshold: float = 5.00
    chunk_target_tokens: int = 120_000
    chunk_overlap_tokens: int = 15_000
    chunk_lookahead_tokens: int = 20_000

    @property
    def anthropic_base_url_trimmed(self) -> str:
        """Base URL without trailing slash for Anthropic SDK."""
        return self.anthropic_base_url.rstrip("/")

    @property
    def openai_base_url(self) -> str:
        """Base URL for OpenAI-compatible endpoint (embeddings)."""
        base = self.anthropic_base_url.rstrip("/")
        return f"{base}/v1"


settings = Settings()
