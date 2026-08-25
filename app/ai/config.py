"""
Configuration Module for Revive Phase 8 AI Intelligence & Gemini Integration.
Supports provider selection ('mock' vs 'gemini'), model configuration, timeout controls, and test-mode isolation.
"""

import os
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AIConfig(BaseModel):
    """Configuration options for the AI Intelligence layer."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "mock"
    model: str = "gemini-3.5-flash-lite"
    api_key: Optional[str] = None
    request_timeout_seconds: float = 5.0
    max_output_tokens: int = 1024
    temperature: float = 0.2
    retry_limit: int = 1
    test_mode: bool = True
    structured_output: bool = True
    min_confidence_threshold: float = 0.50

    def __repr__(self) -> str:
        api_key_str = "'[REDACTED]'" if self.api_key else "None"
        return (
            f"AIConfig(provider={self.provider!r}, model={self.model!r}, api_key={api_key_str}, "
            f"request_timeout_seconds={self.request_timeout_seconds!r}, max_output_tokens={self.max_output_tokens!r}, "
            f"temperature={self.temperature!r}, retry_limit={self.retry_limit!r}, test_mode={self.test_mode!r}, "
            f"structured_output={self.structured_output!r}, min_confidence_threshold={self.min_confidence_threshold!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Instantiate AIConfig from environment variables."""
        provider_env = os.environ.get("AI_PROVIDER", "mock").lower()
        model_env = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        api_key_env = os.environ.get("GEMINI_API_KEY", None)

        return cls(
            provider=provider_env,
            model=model_env,
            api_key=api_key_env,
            test_mode=(provider_env == "mock"),
        )


DEFAULT_AI_CONFIG = AIConfig.from_env()
