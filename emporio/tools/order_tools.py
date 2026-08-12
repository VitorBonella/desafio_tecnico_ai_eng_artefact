from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from emporio.repo.repositories import OrderRepository


def build_order_tools(repo: OrderRepository) -> list[BaseTool]:
    """Cria as tools de pedidos ligadas ao repositório."""

    @tool
    def consultar_status_pedido(pedido_id: str) -> str:
        pedido = repo.get(pedido_id)
        if pedido is None:
            return (
                f"Não encontrei nenhum pedido com o número '{pedido_id}'. "
                "Peça ao cliente para confirmar o número que está no e-mail de "
                "confirmação da compra."
            )
        return pedido.resumo()

    @tool
    def buscar_pedidos_do_cliente(nome_ou_telefone: str) -> str:
        pedidos = repo.por_cliente(nome_ou_telefone)
        if not pedidos:
            return (
                f"Não encontrei pedidos para '{nome_ou_telefone}'. "
                "Confirme o nome completo ou o telefone usado na compra."
            )
        return "\n\n".join(pedido.resumo() for pedido in pedidos)

    return [consultar_status_pedido, buscar_pedidos_do_cliente]
