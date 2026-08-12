from __future__ import annotations

import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStoreRetriever

from emporio.repo.loaders import find_policy_file
from emporio.settings import Settings

# "3. Formas de Pagamento" / "6.1 Prazo para Troca" em linha própria.
_TITULO_SECAO = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s+([^\d].{2,70})$")


def _extrair_texto(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8")

    from pypdf import PdfReader

    paginas = [pagina.extract_text() or "" for pagina in PdfReader(str(path)).pages]
    # Rodapés "Página 3" só poluem o índice.
    texto = "\n".join(paginas)
    return re.sub(r"(?m)^\s*P[áa]gina\s+\d+\s*$", "", texto)


def _limpar(texto: str) -> str:
    """O extrator do PDF quebra palavras em linhas e dobra espaços."""
    return re.sub(r"\s+", " ", texto).strip()


def _secoes(texto: str) -> list[tuple[str, str]]:
    """Quebra o manual em (título da seção, conteúdo)."""
    secoes: list[tuple[str, list[str]]] = [("Capa e identificação da loja", [])]
    for linha in texto.splitlines():
        match = _TITULO_SECAO.match(linha.strip())
        if match and len(linha.strip()) < 80:
            numero, titulo = match.group(1), _limpar(match.group(2))
            secoes.append((f"{numero} {titulo}", []))
        else:
            secoes[-1][1].append(linha)
    return [
        (titulo, _limpar(" ".join(corpo)))
        for titulo, corpo in secoes
        if _limpar(" ".join(corpo))
    ]


def _fatiar(titulo: str, conteudo: str, tamanho: int, overlap: int) -> list[str]:
    """Corta uma seção grande em pedaços, sem partir palavras."""
    if len(conteudo) <= tamanho:
        return [conteudo]

    palavras = conteudo.split(" ")
    pedacos: list[str] = []
    atual: list[str] = []
    for palavra in palavras:
        atual.append(palavra)
        if sum(len(p) + 1 for p in atual) >= tamanho:
            pedacos.append(" ".join(atual))
            # Overlap por palavras, para não cortar uma regra no meio.
            recuo: list[str] = []
            for anterior in reversed(atual):
                if sum(len(p) + 1 for p in recuo) >= overlap:
                    break
                recuo.insert(0, anterior)
            atual = recuo
    if atual:
        pedacos.append(" ".join(atual))
    return pedacos


def build_policy_documents(settings: Settings) -> list[Document]:
    """Carrega o manual e devolve os chunks já rotulados por seção."""
    caminho = find_policy_file(settings.data_dir)
    texto = _extrair_texto(caminho)

    documentos: list[Document] = []
    for titulo, conteudo in _secoes(texto):
        pedacos = _fatiar(titulo, conteudo, settings.chunk_size, settings.chunk_overlap)
        for indice, pedaco in enumerate(pedacos):
            documentos.append(
                Document(
                    # O título entra no conteúdo: ajuda o embedding e permite
                    # que o agente cite a seção na resposta.
                    page_content=f"[{titulo}] {pedaco}",
                    metadata={
                        "secao": titulo,
                        "parte": indice + 1,
                        "fonte": caminho.name,
                    },
                )
            )
    return documentos


def build_policy_retriever(
    settings: Settings, embeddings: Embeddings
) -> VectorStoreRetriever:
    """Carrega, fatia, indexa o manual de políticas e devolve um retriever."""
    documentos = build_policy_documents(settings)
    vectorstore = InMemoryVectorStore.from_documents(documentos, embeddings)
    return vectorstore.as_retriever(search_kwargs={"k": settings.retrieval_k})
