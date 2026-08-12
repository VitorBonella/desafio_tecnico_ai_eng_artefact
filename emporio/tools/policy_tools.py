from __future__ import annotations

from langchain_core.tools import BaseTool, tool
from langchain_core.vectorstores import VectorStoreRetriever


def build_policy_tool(retriever: VectorStoreRetriever) -> BaseTool:
    @tool
    def consultar_politicas(pergunta: str) -> str:
        """Consulta o manual de políticas da loja para responder à pergunta."""
        docs = retriever.invoke(pergunta)
        if not docs:
            return (
                "Não encontrei nada sobre isso no manual de políticas. "
                "Seja honesto com o cliente e ofereça encaminhar à equipe."
            )
        # A seção vai junto: o agente pode citar de onde saiu a regra.
        return "\n\n---\n\n".join(doc.page_content.strip() for doc in docs)

    return consultar_politicas
