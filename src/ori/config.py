"""Server-side Gemini configuration shared by Ori's modules."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(repr=False)
    gemini_model: str = "gemini-2.5-flash"


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load local config without overriding existing environment variables."""
    path = Path(env_file) if env_file else Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(path, override=False)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY in .env before using Gemini.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not model:
        raise ValueError("GEMINI_MODEL must not be empty.")
    return Settings(gemini_api_key=api_key, gemini_model=model)
