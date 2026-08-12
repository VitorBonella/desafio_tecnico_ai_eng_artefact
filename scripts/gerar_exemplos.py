from __future__ import annotations

import time
from pathlib import Path

from emporio.agent.agent import EmporioAgent
from emporio.settings import get_settings

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# O free tier do Gemini limita ~5 requisições/minuto, e cada turno pode gerar
# mais de uma (decisão de tool call + resposta final). Espaçar os turnos e
# tentar de novo com backoff evita abortar a geração inteira por causa disso.
ESPERA_ENTRE_TURNOS = 20
MAX_TENTATIVAS = 4

# (slug do arquivo, título da conversa, turnos do cliente)
CENARIOS: list[tuple[str, str, list[str]]] = [
    (
        "01_catalogo_violoes",
        "Consulta ao catálogo por categoria e faixa de preço",
        [
            "Oi! Tudo bem?",
            "Quais opções de violões disponíveis custando até R$1000?",
            "Qual opção voce me recomenda? Quero tocar casualmente para amigos"
        ],
    ),
    (
        "02_informacoes_da_loja",
        "Informações gerais da loja (endereço, horário e o que ela vende)",
        [
            "Qual o endereço da loja e o horário de funcionamento?",
            "Vocês vendem palhetas e cabos?",
            "Que pena, obrigado, sabe dizer se vao estar disponiveis?"
        ],
    ),
    (
        "03_consulta_preco",
        "Consulta de preço e promoção de um produto específico",
        [
            "Quanto custa o Takamine GD20?",
            "Tem alguma promoção nele?",
        ],
    ),
    (
        "04_devolucao_com_pedido",
        "Cenário não trivial: consulta o pedido e aplica a política de devolução",
        [
            "Me arrependi da minha compra, pedido 5, posso devolver?",
        ],
    ),
    (
        "05_fora_de_escopo",
        "Pergunta fora do escopo da loja",
        [
            "Me escreve um script em Python pra ordenar uma lista?",
        ],
    ),
]


def _chat_com_retentativa(agent: EmporioAgent, pergunta: str, historico: list) -> str:
    ultimo_erro: Exception | None = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return agent.chat(pergunta, historico)
        except Exception as erro:  # cota da API, rede instável, etc.
            ultimo_erro = erro
            espera = ESPERA_ENTRE_TURNOS * tentativa
            print(f"    ! falhou ({erro}); tentativa {tentativa}/{MAX_TENTATIVAS}, aguardando {espera}s...")
            time.sleep(espera)
    raise RuntimeError(f"Falha ao gerar resposta para '{pergunta}'") from ultimo_erro


def _gerar_conversa(agent: EmporioAgent, perguntas: list[str]) -> list[tuple[str, str]]:
    historico: list = []
    turnos = []
    for pergunta in perguntas:
        resposta = _chat_com_retentativa(agent, pergunta, historico)
        agent.append_turn(historico, pergunta, resposta)
        turnos.append((pergunta, resposta))
        time.sleep(ESPERA_ENTRE_TURNOS)
    return turnos


def _salvar_markdown(slug: str, titulo: str, turnos: list[tuple[str, str]]) -> Path:
    linhas = [f"# {titulo}", ""]
    for pergunta, resposta in turnos:
        linhas.append(f"**você:** {pergunta}")
        linhas.append("")
        linhas.append(f"**maestro:** {resposta}")
        linhas.append("")
    caminho = EXAMPLES_DIR / f"{slug}.md"
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


def main() -> int:
    EXAMPLES_DIR.mkdir(exist_ok=True)
    settings = get_settings()
    agent = EmporioAgent(settings)
    print(
        f"provider: {settings.llm_provider} · gerando {len(CENARIOS)} "
        f"exemplos em {EXAMPLES_DIR}/\n"
    )

    for slug, titulo, perguntas in CENARIOS:
        turnos = _gerar_conversa(agent, perguntas)
        caminho = _salvar_markdown(slug, titulo, turnos)
        print(f"  ✓ {caminho.name} — {titulo}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
