from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from emporio.settings import Settings

PROVIDERS = ("gemini", "mock")

_SEM_CHAVE = (
    "Provider 'gemini' exige uma API key. Crie uma (gratuita) em "
    "https://aistudio.google.com/apikey e exporte GEMINI_API_KEY=... "
    "(ou coloque no arquivo .env). Para rodar sem chave nenhuma, use o "
    "provider dumb: `make cli-mock` / `--provider mock`."
)


def _erro_provider(nome: str) -> ValueError:
    return ValueError(
        f"Provider '{nome}' não suportado. Opções: {', '.join(PROVIDERS)}. "
        "Para adicionar outro, inclua um ramo em emporio/llm/provider.py."
    )


def get_chat_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "mock":
        from emporio.llm.mock import MockChatModel

        return MockChatModel()

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.google_api_key:
            raise ValueError(_SEM_CHAVE)

        return ChatGoogleGenerativeAI(
            model=settings.model_name,
            temperature=settings.temperature,
            google_api_key=settings.google_api_key,
            max_retries=3,
        )

    raise _erro_provider(settings.llm_provider)


def get_embeddings(settings: Settings) -> Embeddings:
    if settings.llm_provider == "mock":
        from emporio.llm.mock import MockEmbeddings

        return MockEmbeddings()

    if settings.llm_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not settings.google_api_key:
            raise ValueError(_SEM_CHAVE)

        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.google_api_key,
        )

    raise _erro_provider(settings.llm_provider)
