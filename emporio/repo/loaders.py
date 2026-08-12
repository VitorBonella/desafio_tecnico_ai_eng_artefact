from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path

Row = dict[str, object]

def _normalize_column(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(name))
    ascii_name = nfkd.encode("ascii", "ignore").decode("ascii").strip().lower()
    cleaned = "".join(c if c.isalnum() else "_" for c in ascii_name)
    return "_".join(part for part in cleaned.split("_") if part)


def normalize_text(valor: object) -> str:
    nfkd = unicodedata.normalize("NFKD", str(valor or ""))
    return nfkd.encode("ascii", "ignore").decode("ascii").lower().strip()


def to_float(valor: object, default: float = 0.0) -> float:
    if valor is None or valor == "":
        return default
    texto = str(valor).strip().replace("R$", "").strip()
    if "," in texto and "." in texto:  # 1.299,90 -> 1299.90
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return default


def to_int(valor: object, default: int = 0) -> int:
    return int(to_float(valor, default))


def to_bool(valor: object) -> bool:
    return normalize_text(valor) in {"1", "true", "sim", "yes", "y", "t"}


def to_json(valor: object) -> dict:
    if not valor:
        return {}
    try:
        dados = json.loads(str(valor))
    except (ValueError, TypeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def find_table(data_dir: Path, nome_logico: str) -> Path:
    candidatos = sorted(
        p
        for p in data_dir.glob("*.csv")
        if normalize_text(p.stem).replace(" ", "").endswith(nome_logico)
    )
    if not candidatos:
        raise FileNotFoundError(
            f"CSV da tabela '{nome_logico}' não encontrado em {data_dir}. "
            f"Esperado algo como '{nome_logico}.csv' "
            f"(veja o README, seção Dados)."
        )
    return candidatos[0]


def load_table(data_dir: Path, nome_logico: str) -> list[Row]:
    caminho = find_table(data_dir, nome_logico)
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        leitor = csv.DictReader(fh)
        return [
            {_normalize_column(k): (v.strip() if isinstance(v, str) else v)
             for k, v in linha.items() if k is not None}
            for linha in leitor
        ]


def find_policy_file(data_dir: Path) -> Path:
    for padrao in ("*.pdf", "*.md", "*.txt"):
        matches = sorted(
            p for p in data_dir.glob(padrao) if "polit" in normalize_text(p.stem)
        )
        if matches:
            return matches[0]
    raise FileNotFoundError(
        f"Nenhum arquivo de políticas encontrado em {data_dir} "
        "(esperado algo como 'políticas_da_loja.pdf')."
    )
