from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

# project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"


def _str(nome: str, default: str) -> str:
    valor = os.environ.get(nome)
    return valor if valor not in (None, "") else default


def _opt_str(nome: str) -> str | None:
    valor = os.environ.get(nome)
    return valor or None


def _int(nome: str, default: int) -> int:
    try:
        return int(_str(nome, str(default)))
    except ValueError:
        return default


def _float(nome: str, default: float) -> float:
    try:
        return float(_str(nome, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:

    llm_provider: str = "gemini"
    google_api_key: str | None = None
    model_name: str = "gemini-2.5-flash-lite"
    embedding_model: str = "models/gemini-embedding-001"
    temperature: float = 0.2

    data_dir: Path = PROJECT_ROOT / "data"
    retrieval_k: int = 4 
    chunk_size: int = 1200
    chunk_overlap: int = 150

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(DOTENV_PATH, override=False)
        return cls(
            llm_provider=_str("LLM_PROVIDER", cls.llm_provider).lower(),
            google_api_key=_opt_str("GEMINI_API_KEY") or _opt_str("GOOGLE_API_KEY"),
            model_name=_str("MODEL_NAME", cls.model_name),
            embedding_model=_str("EMBEDDING_MODEL", cls.embedding_model),
            temperature=_float("TEMPERATURE", cls.temperature),
            data_dir=Path(_str("DATA_DIR", str(cls.data_dir))).expanduser(),
            retrieval_k=_int("RETRIEVAL_K", cls.retrieval_k),
            chunk_size=_int("CHUNK_SIZE", cls.chunk_size),
            chunk_overlap=_int("CHUNK_OVERLAP", cls.chunk_overlap),
            api_host=_str("API_HOST", cls.api_host),
            api_port=_int("API_PORT", cls.api_port),
        )

    def com(self, **overrides: object) -> Settings:
        """Cópia com campos sobrescritos (útil em testes e na CLI)."""
        return replace(self, **overrides)

# factory
def get_settings(**overrides: object) -> Settings:
    settings = Settings.from_env()
    limpos = {k: v for k, v in overrides.items() if v is not None}
    return settings.com(**limpos) if limpos else settings
