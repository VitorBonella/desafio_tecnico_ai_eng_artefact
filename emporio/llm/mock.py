from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class MockChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "emporio-mock"

    def bind_tools(self, tools: Iterable[Any], **kwargs: Any) -> Any:
        kwargs.pop("tool_choice", None)
        return self.bind(tools=list(tools), **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        pergunta = next(
            (str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        resposta = f"{pergunta[::-1]} [RESPONSE TEST]"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=resposta))])


class MockEmbeddings(Embeddings):
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vetor(self, texto: str) -> list[float]:
        vetor = [0.0] * self.dim
        for palavra in re.findall(r"[a-z0-9]+", texto.lower()):
            indice = int(hashlib.md5(palavra.encode()).hexdigest(), 16) % self.dim
            vetor[indice] += 1.0
        return vetor

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vetor(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vetor(text)
