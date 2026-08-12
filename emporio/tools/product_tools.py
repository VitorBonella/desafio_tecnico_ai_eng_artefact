from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from emporio.repo.repositories import CatalogRepository, brl

MAX_RESULTADOS = 5


def build_product_tools(repo: CatalogRepository) -> list[BaseTool]:
    @tool
    def buscar_produtos(
        texto: str = "",
        categoria: str = "",
        preco_maximo: float = 0,
        preco_minimo: float = 0,
    ) -> str:
        encontrados = repo.search(
            texto=texto or None,
            categoria=categoria or None,
            preco_max=preco_maximo or None,
            preco_min=preco_minimo or None,
        )
        produtos = encontrados[:MAX_RESULTADOS]
        if not produtos:
            filtros = ", ".join(
                filtro
                for filtro in (
                    f"texto='{texto}'" if texto else "",
                    f"categoria='{categoria}'" if categoria else "",
                    f"até {brl(preco_maximo)}" if preco_maximo else "",
                    f"a partir de {brl(preco_minimo)}" if preco_minimo else "",
                )
                if filtro
            )
            return (
                f"Nenhum produto disponível com esses critérios ({filtros}). "
                "Sugira ao cliente ampliar a faixa de preço ou outra categoria."
            )

        linhas = [p.linha() for p in produtos]
        if len(encontrados) > MAX_RESULTADOS:
            linhas.append(
                f"(+{len(encontrados) - MAX_RESULTADOS} outros produtos atendem ao "
                "filtro; estes são os mais baratos. Ofereça refinar a busca.)"
            )
        return "\n".join(linhas)

    @tool
    def consultar_preco(nome_produto: str) -> str:
        encontrados = repo.buscar_por_nome(nome_produto, limite=5)
        if not encontrados:
            return (
                f"Não encontrei '{nome_produto}' no catálogo. "
                "Confirme o nome com o cliente ou ofereça uma busca por categoria."
            )
        if len(encontrados) == 1:
            return encontrados[0].detalhe()

        principal, *alternativas = encontrados
        alternativas_txt = "\n".join(p.linha() for p in alternativas)
        return (
            f"{principal.detalhe()}\n\n"
            f"Outros parecidos no catálogo:\n{alternativas_txt}"
        )

    @tool
    def listar_promocoes() -> str:
        produtos = repo.promocoes_ativas()
        if not produtos:
            return "Não há promoções ativas no momento."
        return "\n".join(p.linha() for p in produtos)

    @tool
    def listar_categorias() -> str:
        categorias = repo.categorias()
        if not categorias:
            return "Catálogo sem categorias cadastradas."
        return "\n".join(f"- {nome}: {descricao}" for nome, descricao in categorias)

    return [buscar_produtos, consultar_preco, listar_promocoes, listar_categorias]
