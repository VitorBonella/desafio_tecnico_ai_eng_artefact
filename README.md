# Empório da Música — Customer Support Agent

A prototype text-message support agent for **Empório da Música**, a fictional
musical instrument store in Campo Grande/MS, Brazil. The agent answers
questions about **products** (price, availability, promotions), **orders**
(status, tracking, delivery estimate) and **store policies** (exchanges,
returns, opening hours, payment methods), and politely declines anything
outside that scope.

### A note on language

**This README is written in English; the chatbot speaks Brazilian Portuguese.**
That split is deliberate, not an inconsistency. The store is in Campo
Grande/MS, Brazil, and its customers write in Portuguese, so anything the
customer sees or that the model reasons over in that context stays in pt-BR:
the persona and system prompt, the tool descriptions the router reads, the
tool outputs, the currency format (`R$ 1.299,90`) and the sample conversations
in `examples/`. Answering a Brazilian customer in English would be the actual
bug. The documentation, on the other hand, is written for whoever reviews the
code, so it's in English.

---

## Running the project

Requirements: Python 3.10+ and a Google AI Studio API key (the free tier is
enough).

```bash
# 1. Virtualenv + dependencies
make install

# 2. Configuration — copy the template and paste your key into GEMINI_API_KEY
cp .env.example .env

# 3a. Web UI (recommended)
make run          # http://localhost:8000

# 3b. ...or the terminal
make cli

# 3c. ...or with no API key at all (offline stub provider)
make cli-mock
```

Get a free key at <https://aistudio.google.com/apikey>. Every setting has a
default in `emporio/settings.py` and can be overridden by an environment
variable (`MODEL_NAME`, `EMBEDDING_MODEL`, `TEMPERATURE`, `DATA_DIR`,
`RETRIEVAL_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `API_HOST`, `API_PORT`).
`GOOGLE_API_KEY` is accepted as an alias for `GEMINI_API_KEY`.

`make help` lists every target. `make demo` regenerates the sample
conversations in `examples/`. Dependencies are pinned in `requirements.txt`;
`make freeze` regenerates it from the resolved versions.

### Data

Everything the agent knows comes from `data/`.

File discovery is by **logical name, not exact filename** — `find_table()`
matches any `*.csv` whose normalized stem ends with `products`, `orders`, etc.,
so the provided `desafio_tecnico_ai_eng - products.csv` works as-is without
renaming anything. `find_policy_file()` looks for a `polit*` file and prefers
`.pdf`, falling back to `.md`/`.txt`.

---

## Architecture

```
Interface (FastAPI web UI / CLI)
        │
   EmporioAgent  ── facade: persona + history + orchestration
        │
   LLM (function calling)  ── PICKS the route from the tool descriptions
        │
   ┌────┴───────────────┬──────────────────────┐
Data tools          Policy tool           Out of scope
(Repositories)      (RAG / vector)        (prompt guardrail)
   │                    │
 CSVs                 PDF
```

The central decision is to treat the problem as **routing** and delegate that
routing to **function calling** instead of writing a hand-rolled intent
classifier. The LLM picks a tool from its description, which means a new
capability is a new function, not a new branch in a growing `if/elif` chain
that I would have to maintain and test.

- **Structured data → deterministic query tools.** "Guitars up to R$1000"
  needs exact filtering and sorting (`WHERE final_price <= 1000 ORDER BY
  price`), which is precisely what semantic search is bad at. So the CSV data
  is queried by plain Python functions, never by RAG. No hallucinated prices.
- **Policies (prose) → RAG.** Rules and procedures are unstructured text where
  the answer is a paragraph, not a row. Semantic search over document sections
  is the right fit.
- **Out of scope → the prompt.** A guardrail in the persona is cheaper and
  simpler than a dedicated classification layer, and the sample conversation
  in `examples/05_fora_de_escopo.md` shows it holding.

### Layers and responsibilities

| Layer | Where | Responsibility |
|---|---|---|
| Interface | `emporio/api/main.py`, `emporio/cli.py` | Receive a message, keep the session |
| Facade | `emporio/agent/agent.py` | Wire LLM + tools + history |
| Persona | `emporio/agent/persona.py` | System prompt (content, not logic) |
| Tools | `emporio/tools/` | The function-calling surface (descriptions) |
| Data | `emporio/repo/repositories.py` | Business queries over the CSVs |
| Loading | `emporio/repo/loaders.py` | File discovery, parsing, normalization |
| Retrieval | `emporio/rag/policy_store.py` | Section-aware chunking + vector index |
| Provider | `emporio/llm/provider.py` | Isolate the LLM/embeddings vendor |

### Design patterns, and why each one earns its place

- **Repository Pattern** (`CatalogRepository`, `OrderRepository`): hides the
  fact that the data comes from CSV. Swapping in SQL tomorrow doesn't touch a
  single tool. The repositories also do the joins the CSVs don't have
  products get their category name and best active discount, orders get their
  customer name and resolved line items.
- **Adapter / Port** (`llm/provider.py`): no other module imports a vendor
  SDK. Changing model or provider is an isolated, reversible change and
  that boundary is what made the offline `mock` provider possible for free.
- **Factory + dependency injection** (`build_*_tools(repo)`): tools receive a
  ready repository, which keeps them thin and independently testable.
- **Facade** (`EmporioAgent`): both interfaces only ever call `chat()`.
- **Immutable value objects** (`frozen=True` dataclasses `Produto`, `Pedido`,
  `Settings`): business rules live as properties (`disponivel`, `preco_final`,
  `em_promocao`) next to the data they describe, not scattered across tools.

I deliberately did **not** use a multi-agent setup, or an external
vector database. For one small PDF and a handful of CSVs, that is dead weight:
more moving parts to configure, more failure modes to debug, and no better
answers. The simplicity here is a decision to fit the challenge, not a shortcut and the
boundaries above are exactly what make it cheap to reverse when the data
outgrows it.

---

## Technical decisions

Every choice below optimizes for the same two things: **staying simple** and
**fitting the time budget of a prototype**, without painting myself into a
corner.

| Decision | Choice | Justification |
|---|---|---|
| Agent framework | **LangChain v1** `create_agent` (tool-calling agent) | Mature function-calling and message abstractions; the whole orchestration is ~15 lines instead of a hand-written tool loop. Prior familiarity meant time went into tool design, which is what actually drives quality |
| Approach | **Hybrid**: deterministic tools for data + RAG for policies | Matches each question type to the technique that answers it correctly (see above). Avoids both hallucinated prices and a vector index for numbers |
| Model / provider | **Google Gemini** `gemini-3.5-flash-lite` via an adapter | Solid function calling, very low latency and cost, and a free tier so a reviewer can run this without paying. The `provider.py` boundary keeps the choice reversible |
| Temperature | **0.2** | Support answers should be consistent and boring; the creativity budget belongs to tone, not to facts |
| Retrieval | **`InMemoryVectorStore`** (langchain-core) | The manual is a single small document that becomes 16 chunks across 13 sections. FAISS/Chroma/pgvector would add infrastructure for an index that rebuilds in under a second. `k=4` |
| Chunking | **Section-aware**, then size-based | The PDF has numbered sections ("2. Horário de Funcionamento", "6.1 Prazo para Troca"). Splitting on those headings keeps a rule whole, and each chunk carries its section title in the text which improves both the embedding and the answer, since the agent can cite "per section 6.1". Blind fixed-size splitting would cut rules in half |
| Interface | **FastAPI** + a single static HTML/JS page, plus a CLI | One clear `POST /chat` endpoint and a lightweight UI: enough to demo, nothing to maintain. The CLI is what I actually developed against |
| History | **In memory**, keyed by `session_id` | Multi-turn is what makes it feel like support ("and is it on sale?" — see `examples/03_consulta_preco.md`). Swapping for Redis/SQLite is confined to the API layer |
| Data handling | **Normalization in the loaders** | Column names are accent- and case-folded, `R$ 1.299,90` and `1299.90` both parse, `specs` JSON is decoded defensively. Every CSV quirk is absorbed at one boundary instead of leaking into business logic |

### Details worth pointing out

These are the small decisions that separate "it demoed once" from "it holds up":

- **Discount-aware price filtering.** "Up to R$1000" compares against the
  *final* price, so a R$1099 guitar at 20% off is correctly included. Filtering
  on the list price would have silently hidden the best offer in the catalog.
- **Only genuinely active promotions.** `is_active` is respected and, when a
  product has several, the largest discount wins.
- **Tolerant product lookup.** `buscar_por_nome` scores candidates (full-name
  match > exact token match > substring), so "takamine gd20" finds the right
  guitar and a bare "yamaha" returns the Yamahas instead of nothing. Tokens of
  1–2 characters are dropped, since they would match half the catalog.
- **Data minimization.** Orders can be found by customer name or phone, but no
  tool ever returns a customer's email or phone. This is a support agent, not a
  query interface into the customer base so that data stays in the repository
  and off the function-calling surface.
- **Currency and status formatting.** Prices are rendered as `R$ 1.299,90` in
  code (not left to the model), while raw system values like `shipped` or
  `credit_12x` are passed through and the prompt handles the natural-language
  translation.
- **PDF cleanup.** `Página N` footers are stripped and the extractor's broken
  line wrapping is collapsed before chunking, so they don't pollute embeddings.
- **Offline `mock` provider.** A stub chat model plus deterministic
  hash-based embeddings let the whole pipeline loading, chunking, indexing,
  tool wiring run with no key and no network. It made iteration fast and lets
  a reviewer verify the plumbing for free via `make cli-mock`.
- **Rate-limit resilience in the demo script.** The Gemini free tier allows
  ~5 requests/minute and each turn can spend more than one, so
  `scripts/gerar_exemplos.py` paces turns and retries with backoff instead of
  losing the whole batch to a 429.

### Prompt strategy

The system prompt (`emporio/agent/persona.py`) is kept out of the
orchestration code the prompt is content, so changing the store's tone or its
scope rules means touching one file. It's organized into five explicit blocks:

1. **Tone and persona** — "Maestro", friendly and close, short answers, pt-BR,
   at most one emoji, and a hard rule: never invent a price, stock level,
   deadline or rule; those always come from a tool.
2. **When to use each tool** — reinforces the routing in prose, which matters
   most for the hard case: *mixed* questions. "I regret buying order 5, can I
   return it?" explicitly requires **both** an order lookup and a policy
   lookup. That is the non-trivial scenario in
   `examples/04_devolucao_com_pedido.md`.
3. **How to answer** — summarize the tool output instead of pasting it,
   translate raw system values, cap product lists at 5 cheapest-first and offer
   to refine, and attribute rules to their source ("per our exchange policy").
4. **Out of scope** — decline gracefully and redirect, without inventing
   services the store doesn't offer.
5. **When information is missing** — be honest, ask for the order number, or
   suggest the human team. Never fill gaps with assumptions.

Tool descriptions carry the other half of the prompt engineering. Since the
model routes by reading them, each docstring states what the tool returns *and*
when to reach for it, with concrete example questions. Tool outputs are also
written as instructions to the agent — a failed lookup returns "ask the
customer to confirm the number", turning a dead end into a useful turn.

---

## Assumptions

The challenge invited reasonable interpretation where the brief was silent.
Mine, all documented at the point they affect behavior:

- **Availability = `status == "active"` and `stock_quantity > 0`.** A product
  that is `coming_soon` or `discontinued` is never offered as available, and
  its raw status is surfaced so the agent can explain why.
- **Brand is the first token of the product name**, since the CSVs have no
  brand column. Good enough for "do you have Yamaha?" and cheap to replace if a
  real column appears.
- **A product's category comes from `category_id`**, defaulting to "Outros"
  when the id is unknown rather than dropping the product.
- **`listar_categorias` only shows categories that actually have products**, so
  the agent never advertises an empty shelf.
- **Order identity is the order number.** If the customer doesn't have it, the
  agent asks first and only falls back to name/phone lookup — no guessing which
  order they meant.
- **No authentication.** The prototype trusts the caller, which is why the
  order tools deliberately expose no personal data.
- **Policies come from the PDF.** The loader prefers `.pdf` and accepts
  `.md`/`.txt` as a fallback for a future plain-text manual.

---

## Known limitations

Honest inventory of what this prototype does not do:

- **No automated test suite is committed.** The deterministic layer
  (repositories, tools, chunking) was verified manually and by exercising every
  path through the CLI and the `mock` provider; that verification isn't
  reproducible from the repo yet. This is the gap I would close first.
- **Volatile history.** Restarting the API clears every conversation, and the
  full history is resent each turn with no windowin a long session will grow
  the prompt without bound.
- **Index rebuilt at every boot.** Fast today (16 chunks), wasteful once the
  manual grows.
- **No retrieval or routing evaluation.** I have no measured hit@k for the
  policy index, and no assertion that a given question triggers the intended
  tool. Quality is currently judged by reading answers.
- **Provider errors surface raw.** A 429 or a network failure becomes a 500 on
  the API (the CLI catches it and prints a warning). There is no friendly
  fallback message for the customer.
- **Single-tenant, unguarded API.** No auth, no rate limiting, no session TTL,
  and `session_id` is client-supplied fine for a local prototype, not for
  production.
- **No streaming.** The user waits for the complete answer, which is felt on
  multi-tool turns.
- **Purely lexical product search.** Deliberate — it's precise and predictable
  — but it won't answer "something warm-sounding for fingerstyle" the way
  semantic search over descriptions would.
- **`customers` data is used only to resolve orders**; the richer fields are
  intentionally left unused for privacy reasons.

## What I would do with more time

Roughly in the order I would tackle it:

1. **Commit the automated test suite** — pytest over the deterministic layer
   (repository filtering, discount math, tolerant lookup, section chunking) plus
   agent-level scenario tests running against the `mock` provider, so the whole
   graph is covered with no key and no network. Pin `pytest` in
   `requirements.txt` and add a `make test` target.
2. **Evaluation harness** — a golden set of question → expected section for
   retrieval (measuring hit@k) and question → expected tool for routing, so
   changes to a docstring or the prompt produce a number instead of a vibe. Add
   an LLM-as-judge pass over answer quality for the pt-BR tone rules.
3. **Robust error handling at the provider boundary** — typed exceptions,
   retry with backoff on 429, and a friendly customer-facing fallback
   ("our system is slow right now, want me to call a human?") instead of a 500.
4. **Persistent, bounded history** — SQLite or Redis keyed by `session_id`,
   with a sliding window plus a rolling summary so long conversations stay
   cheap and coherent.
5. **Cache the vector index on disk** and, when the document set grows past a
   handful, move to `sqlite-vec` or pgvector a swap confined to
   `policy_store.py`.
6. **Better retrieval** — hybrid BM25 + vector search with a reranker, which
   matters for policy questions that hinge on an exact term ("nota fiscal",
   "garantia estendida").
7. **Observability** — request tracing (LangSmith or OpenTelemetry), plus
   per-turn logging of tools called, latency and token cost. Without it, you
   can't debug a bad answer after the fact.
8. **Streaming responses** over SSE, and typing indicators in the UI — the
   cheapest perceived-latency win available.
9. **Move the CSVs into SQL** behind the existing repository interface, which
   is the change the Repository Pattern was chosen to make boring. That also
   opens the door to a narrowly-scoped, read-only SQL tool for ad-hoc questions
   the fixed tools don't cover.
10. **Semantic product search** as a complement, not a replacement: embed
    product descriptions for "recommend me something" questions while keeping
    the deterministic filters for anything numeric.
11. **Human handoff** — an escalation path that detects frustration or an
    unanswerable request and hands the thread to the store's team with a
    summary of what was already asked.
12. **Guardrails** — prompt-injection checks on retrieved text and PII
    redaction on inbound messages, both of which matter the moment this touches
    a real channel.
13. **Real channels and packaging** — a WhatsApp/Telegram adapter over the
    same `chat()` facade, Docker Compose, and CI running lint + tests on every
    push.
14. **Capability-aware provider boundary** — `provider.py` passes `temperature`
    unconditionally, but newer Gemini models use fixed sampling defaults and
    ignore it (`gemini-3.5-flash-lite` and `gemini-3.6-flash` today, and every
    model after them per Google's docs), so langchain-google-genai drops the
    parameter and emits a `UserWarning`. Harmless, but it means the documented
    temperature of 0.2 is silently not in effect on those models. The fix is to
    build the model kwargs from a small capability map instead of a fixed
    signature — the same place that would later carry per-model context limits
    and thinking-budget settings.

---

## Use of code assistants

I used two Anthropic tools, for two different kinds of work: **Claude Code**
for the code, and **Claude Chat** for the Portuguese copy. The division of
labor was deliberate: I owned the design, they accelerated the typing.

The workflow:

1. **I designed the architecture** — hybrid function calling over deterministic
   data tools plus RAG for the policy manual, the layer boundaries, the
   provider port, and which patterns actually justified themselves at this
   size. That reasoning is mine, and it's what the sections above document.
2. **I handed that architecture to Claude Code to generate the skeleton** —
   module layout, class and dataclass stubs, function signatures. Scaffolding
   from a design I had already settled is exactly the work worth delegating.
3. **I filled in and corrected the implementation.** The parts that decide
   whether this works the tool descriptions the router reads, section-aware
   chunking, discount-aware price filtering, the scoring in the tolerant name
   lookup, the Gemini schema sentinel workaround went through my own
   iteration against real data.
4. **I used Claude Chat to write the Portuguese copy** — the "Maestro" persona
   text in `emporio/agent/persona.py` and some of the user-facing strings
   (fallback messages, the CLI banner). Writing natural pt-BR customer-service
   prose is a drafting task, and an LLM is good at it. I decided *what* the
   persona had to enforce never invent a price, ask for the order number,
   one emoji maximum, decline out-of-scope politely — and then reviewed and
   tuned every line of the generated text against how the agent actually
   behaved.
5. **I used Claude Code to polish prose and to draft this README** from the
   decisions I had made, then edited it to match the code exactly.

**All code was tested and reviewed by me.** I ran every path the four routing
branches, the offline `mock` provider, the CLI, the API, the demo generator
and the sample conversations in `examples/` are real output from the committed
code. The assistants contributed speed; the architecture, the trade-offs and
the verification are mine.
