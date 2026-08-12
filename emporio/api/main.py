from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from emporio.agent.agent import EmporioAgent

app = FastAPI(title="Empório da Música — Agente de Atendimento")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Estado em memória.
_agent: EmporioAgent | None = None
_sessions: dict[str, list[BaseMessage]] = {}


#singleton
def _get_agent() -> EmporioAgent:
    """Inicializa o agente"""
    global _agent
    if _agent is None:
        _agent = EmporioAgent()
    return _agent


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = _get_agent()
    historico = _sessions.setdefault(req.session_id, [])
    resposta = agent.chat(req.message, historico)
    agent.append_turn(historico, req.message, resposta)
    return ChatResponse(reply=resposta)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
