from __future__ import annotations

from dataclasses import dataclass, field

from emporio.repo.loaders import (
    Row,
    normalize_text,
    to_bool,
    to_float,
    to_int,
    to_json,
)

# Sinônimos que o cliente (e o LLM) usam vs. nome da categoria no CSV.
CATEGORIA_SINONIMOS = {
    "violao": "Violões",
    "violoes": "Violões",
    "guitarra": "Guitarras",
    "guitarras": "Guitarras",
    "baixo": "Baixos",
    "baixos": "Baixos",
    "contrabaixo": "Baixos",
    "bateria": "Baterias e Percussão",
    "baterias": "Baterias e Percussão",
    "percussao": "Baterias e Percussão",
    "teclado": "Teclados e Pianos",
    "teclados": "Teclados e Pianos",
    "piano": "Teclados e Pianos",
    "sintetizador": "Teclados e Pianos",
    "ukulele": "Ukuleles",
    "ukuleles": "Ukuleles",
    "violino": "Cordas Orquestrais",
    "viola": "Cordas Orquestrais",
    "violoncelo": "Cordas Orquestrais",
    "cello": "Cordas Orquestrais",
    "sax": "Instrumentos de Sopro (Madeiras)",
    "saxofone": "Instrumentos de Sopro (Madeiras)",
    "flauta": "Instrumentos de Sopro (Madeiras)",
    "clarinete": "Instrumentos de Sopro (Madeiras)",
    "trompete": "Instrumentos de Sopro (Metais)",
    "trombone": "Instrumentos de Sopro (Metais)",
    "tuba": "Instrumentos de Sopro (Metais)",
}


def brl(valor: float) -> str:
    """1299.9 -> 'R$ 1.299,90' (formato brasileiro)."""
    inteiro, _, centavos = f"{valor:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


# --- Entidades ------------------------------------------------------------


@dataclass(frozen=True)
class Produto:
    id: int
    nome: str
    marca: str
    categoria: str
    preco: float
    estoque: int
    status: str
    descricao: str = ""
    specs: dict = field(default_factory=dict)
    desconto_percent: float = 0.0
    promocao: str = ""

    @property
    def disponivel(self) -> bool:
        return self.status == "active" and self.estoque > 0

    @property
    def preco_final(self) -> float:
        return round(self.preco * (1 - self.desconto_percent / 100), 2)

    @property
    def em_promocao(self) -> bool:
        return self.desconto_percent > 0

    def linha(self) -> str:
        """Uma linha compacta para o LLM montar a resposta."""
        if self.em_promocao:
            preco = (
                f"{brl(self.preco_final)} "
                f"(de {brl(self.preco)}, -{self.desconto_percent:.0f}% "
                f"na promoção {self.promocao})"
            )
        else:
            preco = brl(self.preco)

        if self.disponivel:
            estoque = f"em estoque ({self.estoque} un.)"
        elif self.status != "active":
            estoque = self.status  # ex.: "coming_soon", "discontinued"
        else:
            estoque = "sem estoque no momento"

        return f"[#{self.id}] {self.nome} — {self.categoria} — {preco} — {estoque}"

    def detalhe(self) -> str:
        """Ficha completa, para perguntas sobre UM produto."""
        partes = [self.linha()]
        if self.descricao:
            partes.append(f"Descrição: {self.descricao}")
        if self.specs:
            specs = ", ".join(f"{k}: {v}" for k, v in self.specs.items())
            partes.append(f"Especificações: {specs}")
        return "\n".join(partes)


@dataclass(frozen=True)
class ItemPedido:
    produto_id: int
    produto_nome: str
    quantidade: int


@dataclass(frozen=True)
class Pedido:
    id: int
    cliente: str
    cidade: str
    data: str
    status: str
    total: float
    pagamento: str
    codigo_rastreio: str
    previsao_entrega: str
    observacoes: str
    itens: list[ItemPedido] = field(default_factory=list)

    def resumo(self) -> str:
        linhas = [
            f"Pedido #{self.id} — cliente: {self.cliente}",
            f"Status: {self.status}",  # raw do CSV: "pending", "shipped", ...
            f"Data do pedido: {self.data}",
            f"Itens: "
            + ("; ".join(f"{i.quantidade}x {i.produto_nome}" for i in self.itens)
               or "não informados"),
            f"Total: {brl(self.total)} ({self.pagamento or 'forma não informada'})",
        ]
        if self.codigo_rastreio:
            linhas.append(f"Código de rastreio: {self.codigo_rastreio}")
        if self.previsao_entrega:
            rotulo = "Entregue em" if self.status == "delivered" else "Previsão de entrega"
            linhas.append(f"{rotulo}: {self.previsao_entrega}")
        elif self.status not in {"cancelled", "delivered"}:
            linhas.append("Previsão de entrega: ainda não definida")
        if self.observacoes:
            linhas.append(f"Observação interna: {self.observacoes}")
        return "\n".join(linhas)


# --- Repositórios ---------------------------------------------------------


class CatalogRepository:
    """Consultas ao catálogo: produtos, categorias e promoções."""

    def __init__(
        self,
        produtos: list[Row],
        categorias: list[Row],
        promocoes: list[Row] | None = None,
    ) -> None:
        self._categorias = {
            to_int(c.get("category_id")): (
                str(c.get("name", "")),
                str(c.get("description", "")),
            )
            for c in categorias
        }
        self._promocoes_brutas = promocoes or []
        # product_id -> (desconto, descrição) da promoção ativa mais vantajosa.
        self._descontos: dict[int, tuple[float, str]] = {}
        for promo in self._promocoes_brutas:
            if not to_bool(promo.get("is_active")):
                continue
            pid = to_int(promo.get("product_id"))
            desconto = to_float(promo.get("discount_percent"))
            atual = self._descontos.get(pid)
            if atual is None or desconto > atual[0]:
                self._descontos[pid] = (desconto, str(promo.get("description", "")))

        self._produtos = [self._to_produto(p) for p in produtos]
        self._por_id = {p.id: p for p in self._produtos}

    # -- construção -------------------------------------------------------

    def _to_produto(self, row: Row) -> Produto:
        pid = to_int(row.get("product_id"))
        nome = str(row.get("name", "")).strip()
        desconto, promo = self._descontos.get(pid, (0.0, ""))
        categoria, _ = self._categorias.get(
            to_int(row.get("category_id")), ("Outros", "")
        )
        return Produto(
            id=pid,
            nome=nome,
            marca=nome.split(" ")[0] if nome else "",
            categoria=categoria,
            preco=to_float(row.get("price_brl")),
            estoque=to_int(row.get("stock_quantity")),
            status=normalize_text(row.get("status")) or "active",
            descricao=str(row.get("description", "")).strip(),
            specs=to_json(row.get("specs")),
            desconto_percent=desconto,
            promocao=promo,
        )

    # -- consultas --------------------------------------------------------

    def categorias(self) -> list[tuple[str, str]]:
        """Categorias que realmente têm produtos no catálogo."""
        com_produtos = {p.categoria for p in self._produtos}
        return [
            (nome, descricao)
            for nome, descricao in self._categorias.values()
            if nome in com_produtos
        ]

    @staticmethod
    def resolver_categoria(termo: str | None) -> str | None:
        """'violão' -> 'Violões'. Devolve None se não reconhecer."""
        if not termo:
            return None
        alvo = normalize_text(termo)
        if alvo in CATEGORIA_SINONIMOS:
            return CATEGORIA_SINONIMOS[alvo]
        for sinonimo, categoria in CATEGORIA_SINONIMOS.items():
            if sinonimo in alvo:
                return categoria
        return None

    def search(
        self,
        texto: str | None = None,
        categoria: str | None = None,
        preco_max: float | None = None,
        preco_min: float | None = None,
        apenas_disponiveis: bool = True,
        limite: int | None = None,
    ) -> list[Produto]:
        """Busca produtos por texto livre, categoria e/ou faixa de preço.

        O preço comparado é o FINAL (com promoção): "até R$1000" precisa
        incluir o violão de R$1099 com 20% de desconto.
        """
        resultado = self._produtos

        if categoria:
            nome_cat = self.resolver_categoria(categoria) or categoria
            alvo = normalize_text(nome_cat)
            resultado = [
                p
                for p in resultado
                if alvo in normalize_text(p.categoria)
                or normalize_text(p.categoria) in alvo
            ]

        if texto:
            termos = [t for t in normalize_text(texto).split() if len(t) > 2]
            if termos:
                resultado = [
                    p
                    for p in resultado
                    if all(
                        t in normalize_text(f"{p.nome} {p.categoria} {p.descricao}")
                        for t in termos
                    )
                ]

        if preco_max is not None:
            resultado = [p for p in resultado if p.preco_final <= preco_max]
        if preco_min is not None:
            resultado = [p for p in resultado if p.preco_final >= preco_min]
        if apenas_disponiveis:
            resultado = [p for p in resultado if p.disponivel]

        ordenado = sorted(resultado, key=lambda p: p.preco_final)
        return ordenado[:limite] if limite else ordenado

    def get_by_id(self, produto_id: int | str) -> Produto | None:
        return self._por_id.get(to_int(produto_id))

    def buscar_por_nome(self, nome: str, limite: int = 5) -> list[Produto]:
        """Ranqueia produtos por semelhança de nome (busca tolerante).

        Pontuação: nome inteiro contido > nº de termos batendo. Assim
        "takamine gd20" acha "Takamine GD20 NS Natural", e "yamaha" devolve
        os Yamaha do catálogo em vez de nada.
        """
        alvo = normalize_text(nome)
        if not alvo:
            return []
        # Tokens de 1-2 caracteres ("o", "de", "um") casariam com meio
        # catálogo por substring e só sujariam o ranking.
        termos = [t for t in alvo.split() if len(t) > 2]
        if not termos:
            termos = [alvo]

        pontuados: list[tuple[float, Produto]] = []
        for p in self._produtos:
            nome_norm = normalize_text(p.nome)
            pontos = 0.0
            if alvo in nome_norm:
                pontos += 10
            pontos += sum(2 for t in termos if t in nome_norm.split())
            pontos += sum(1 for t in termos if t not in nome_norm.split() and t in nome_norm)
            if pontos:
                # Empate: mostra primeiro o que está disponível e mais barato.
                pontuados.append((pontos + (0.5 if p.disponivel else 0), p))

        pontuados.sort(key=lambda par: (-par[0], par[1].preco_final))
        return [p for _, p in pontuados[:limite]]

    def promocoes_ativas(self) -> list[Produto]:
        """Produtos com promoção vigente, do maior desconto para o menor."""
        promocionais = [p for p in self._produtos if p.em_promocao]
        return sorted(promocionais, key=lambda p: -p.desconto_percent)


class OrderRepository:
    """Consultas a pedidos, já com cliente e itens resolvidos."""

    def __init__(
        self,
        pedidos: list[Row],
        itens: list[Row],
        clientes: list[Row],
        catalogo: CatalogRepository | None = None,
    ) -> None:
        self._clientes = {
            to_int(c.get("customer_id")): (
                str(c.get("name", "")),
                str(c.get("city", "")),
                normalize_text(c.get("phone")),
            )
            for c in clientes
        }

        itens_por_pedido: dict[int, list[ItemPedido]] = {}
        for item in itens:
            pedido_id = to_int(item.get("order_id"))
            produto_id = to_int(item.get("product_id"))
            produto = catalogo.get_by_id(produto_id) if catalogo else None
            itens_por_pedido.setdefault(pedido_id, []).append(
                ItemPedido(
                    produto_id=produto_id,
                    produto_nome=produto.nome if produto else f"produto #{produto_id}",
                    quantidade=to_int(item.get("quantity"), 1),
                )
            )

        self._pedidos: dict[int, Pedido] = {}
        for row in pedidos:
            pedido_id = to_int(row.get("order_id"))
            nome, cidade, _ = self._clientes.get(
                to_int(row.get("customer_id")), ("cliente não identificado", "", "")
            )
            self._pedidos[pedido_id] = Pedido(
                id=pedido_id,
                cliente=nome,
                cidade=cidade,
                data=str(row.get("order_date", "")),
                status=normalize_text(row.get("status")),
                total=to_float(row.get("total_brl")),
                pagamento=normalize_text(row.get("payment_method")),
                codigo_rastreio=str(row.get("tracking_code", "")).strip(),
                previsao_entrega=str(row.get("estimated_delivery", "")).strip(),
                observacoes=str(row.get("notes", "")).strip(),
                itens=itens_por_pedido.get(pedido_id, []),
            )

    def get(self, pedido_id: str | int) -> Pedido | None:
        """Retorna o pedido, ou None se não existir."""
        return self._pedidos.get(to_int(pedido_id, -1))

    def ids_conhecidos(self) -> list[int]:
        return sorted(self._pedidos)

    def por_cliente(self, nome_ou_telefone: str, limite: int = 5) -> list[Pedido]:
        """Pedidos de um cliente, por nome (parcial) ou telefone.

        Só devolve dados do PEDIDO — nunca e-mail/telefone do cadastro. É um
        agente de atendimento, não uma consulta à base de clientes.
        """
        alvo = normalize_text(nome_ou_telefone)
        if len(alvo) < 3:
            return []
        somente_digitos = "".join(c for c in alvo if c.isdigit())

        encontrados = [
            pedido
            for pedido in self._pedidos.values()
            if alvo in normalize_text(pedido.cliente)
            or (
                len(somente_digitos) >= 8
                and somente_digitos
                in "".join(
                    c
                    for c in next(
                        (
                            tel
                            for nome, _, tel in self._clientes.values()
                            if nome == pedido.cliente
                        ),
                        "",
                    )
                    if c.isdigit()
                )
            )
        ]
        return sorted(encontrados, key=lambda p: p.data, reverse=True)[:limite]
