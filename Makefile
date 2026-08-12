VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help venv install freeze run cli cli-mock demo test clean

help:  ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv:  ## Cria o virtualenv
	python3 -m venv $(VENV)

install: venv  ## Instala as dependências
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

freeze:  ## Congela as versões instaladas
	$(PIP) freeze > requirements.txt

run:  ## Sobe a API + UI web (precisa de fastapi/uvicorn)
	$(VENV)/bin/uvicorn emporio.api.main:app --reload --host 0.0.0.0 --port 8000

cli:  ## Chat na CLI com o Gemini (precisa de GEMINI_API_KEY)
	$(PY) -m emporio.cli --provider gemini

cli-mock:  ## Chat na CLI com o provider offline (sem chave, sem rede)
	$(PY) -m emporio.cli --provider mock

demo:  ## Gera os exemplos de interação com o agente (entregável do desafio)
	$(PY) -m scripts.gerar_exemplos

clean:  ## Remove venv e caches
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} +
