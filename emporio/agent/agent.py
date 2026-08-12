from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from emporio.agent.persona import SYSTEM_PROMPT
from emporio.llm.provider import get_chat_model, get_embeddings
from emporio.rag.policy_store import build_policy_retriever
from emporio.repo.loaders import load_table
from emporio.repo.repositories import CatalogRepository, OrderRepository
from emporio.settings import Settings, get_settings
from emporio.tools.order_tools import build_order_tools
from emporio.tools.policy_tools import build_policy_tool
from emporio.tools.product_tools import build_product_tools


def _texto(mensagem: BaseMessage) -> str:
    """Extrai texto de uma mensagem"""
    conteudo = mensagem.content
    if isinstance(conteudo, str):
        return conteudo.strip()
    partes = [
        bloco.get("text", "") if isinstance(bloco, dict) else str(bloco)
        for bloco in conteudo or []
    ]
    return "\n".join(p for p in partes if p).strip()

#Facade
class EmporioAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        data_dir = self.settings.data_dir

        self.catalogo = CatalogRepository(
            produtos=load_table(data_dir, "products"),
            categorias=load_table(data_dir, "categories"),
            promocoes=load_table(data_dir, "promotions"),
        )
        self.pedidos = OrderRepository(
            pedidos=load_table(data_dir, "orders"),
            itens=load_table(data_dir, "order_items"),
            clientes=load_table(data_dir, "customers"),
            catalogo=self.catalogo,
        )

        self.retriever = build_policy_retriever(
            self.settings, get_embeddings(self.settings)
        )

        self.tools = [
            *build_product_tools(self.catalogo),
            *build_order_tools(self.pedidos),
            build_policy_tool(self.retriever),
        ]

        # lanchchain router
        self._agent = create_agent(
            model=get_chat_model(self.settings),
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
        )

    def chat(self, mensagem: str, historico: list[BaseMessage] | None = None) -> str:
        """Processa uma mensagem e devolve a resposta do agente."""
        mensagens = [*(historico or []), HumanMessage(content=mensagem)]
        resultado = self._agent.invoke({"messages": mensagens})

        for msg in reversed(resultado["messages"]):
            if isinstance(msg, AIMessage) and _texto(msg):
                return _texto(msg)
        return "Desculpe, não consegui formular uma resposta. Pode repetir?"

    @staticmethod
    def append_turn(
        historico: list[BaseMessage], pergunta: str, resposta: str
    ) -> list[BaseMessage]:
        historico.append(HumanMessage(content=pergunta))
        historico.append(AIMessage(content=resposta))
        return historico
