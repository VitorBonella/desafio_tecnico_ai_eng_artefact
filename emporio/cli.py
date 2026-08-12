from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emporio.agent.agent import EmporioAgent
from emporio.llm.provider import PROVIDERS
from emporio.settings import get_settings

BANNER = """
╭──────────────────────────────────────────────╮
│  Empório da Música — Maestro 🎼              │
│  Sua música começa aqui.                     │
╰──────────────────────────────────────────────╯
"""

AJUDA = (
    "Comandos: 'sair' encerra · '/limpar' esquece o histórico · "
    "'/ajuda' mostra isto"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m emporio.cli",
        description="Chat de atendimento da Empório da Música.",
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=None,
        help="Provedor do LLM (default: LLM_PROVIDER do ambiente, ou 'gemini'). "
        "'mock' roda offline, sem chave de API.",
    )
    parser.add_argument("--model", default=None, help="Sobrescreve o modelo.")
    parser.add_argument(
        "--data-dir", default=None, help="Diretório com os CSVs e o PDF de políticas."
    )
    parser.add_argument(
        "--perguntas",
        type=Path,
        default=None,
        help="Arquivo com uma pergunta por linha: roda em lote e sai "
        "(útil para gerar exemplos de conversa).",
    )
    return parser.parse_args(argv)


def _build_agent(args: argparse.Namespace) -> EmporioAgent:
    settings = get_settings(
        llm_provider=args.provider,
        model_name=args.model,
        data_dir=Path(args.data_dir) if args.data_dir else None,
    )
    agent = EmporioAgent(settings)
    print(
        f"provider: {settings.llm_provider}"
        + (f" · modelo: {settings.model_name}" if settings.llm_provider != "mock" else "")
        + f" · {len(agent.tools)} ferramentas carregadas"
    )
    return agent


def _responder(agent: EmporioAgent, historico: list, pergunta: str) -> None:
    resposta = agent.chat(pergunta, historico)
    agent.append_turn(historico, pergunta, resposta)
    print(f"\nmaestro> {resposta}\n")


def _modo_lote(agent: EmporioAgent, arquivo: Path) -> None:
    perguntas = [
        linha.strip()
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.startswith("#")
    ]
    historico: list = []
    for pergunta in perguntas:
        print(f"você> {pergunta}")
        _responder(agent, historico, pergunta)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(BANNER)

    try:
        agent = _build_agent(args)
    except (ValueError, FileNotFoundError) as erro:
        print(f"\n❌ {erro}\n", file=sys.stderr)
        return 1

    if args.perguntas:
        _modo_lote(agent, args.perguntas)
        return 0

    print(AJUDA + "\n")
    historico: list = []
    while True:
        try:
            pergunta = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if pergunta.lower() in {"sair", "exit", "quit"}:
            break
        if not pergunta:
            continue
        if pergunta == "/limpar":
            historico.clear()
            print("(histórico esquecido)\n")
            continue
        if pergunta == "/ajuda":
            print(AJUDA + "\n")
            continue

        try:
            _responder(agent, historico, pergunta)
        except Exception as erro:  # rede caiu, cota estourou, etc.
            print(f"\n⚠️  Falha ao responder: {erro}\n", file=sys.stderr)

    print("Até a próxima! 🎶")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
