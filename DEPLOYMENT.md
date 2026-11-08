# Deployment guide

This service is a **natural-language → knowledge-graph traversal QA API** with a
bundled browser UI. The traversal engine produces structured answers with **no
model**, so it is always runnable. An optional Ollama backend only prettifies the
structured result into prose; without it, phrasing is deterministic and offline.

It runs three ways: local Python, a single Docker container, or the full
`docker compose` stack (API + Ollama).

## Architecture

```
                 ┌──────────────────────────────────────────────┐
  browser ──────►│  FastAPI app (clinq.api.main)                 │
  (web/ UI)      │   GET  /         static chat UI               │
                 │   GET  /health   backend + graph size          │
                 │   POST /ask      NL → graph traversal          │
                 │   POST /load     rebuild graph                 │
                 │        │                                       │
                 │        ▼                                       │
                 │  EntityTraversalQA pipeline                    │
                 │   • PropertyGraph (in-memory, pure-Python)     │
                 │   • traversal.py: intent patterns → traversals │
                 │   • LLM (OPTIONAL, prose only): Ollama/offline  │
                 └───────────────┬────────────────────────────────┘
                                 │ HTTP (prose phrasing only)
                                 ▼
                          Ollama model server
```

Data flows in at startup from `data/clinical.json` (synthetic; no PHI) and can
be replaced at runtime via `POST /load`.

## 1. Local (Python)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Offline (no Ollama) — instant, deterministic:
KG_OFFLINE=1 uvicorn clinq.api.main:app --reload

# With Ollama for natural-language prose:
ollama pull llama3.2
uvicorn clinq.api.main:app --reload
```

Open <http://localhost:8000> for the UI, or <http://localhost:8000/docs> for the
API. For uvicorn either `pip install -e .` (recommended) or run with `PYTHONPATH=src`.

## 2. Single Docker container

```bash
docker build -t kg-entity-traversal .
# offline backend, no external Ollama:
docker run -p 8000:8000 -e KG_OFFLINE=1 kg-entity-traversal
# or point at a host Ollama:
docker run -p 8000:8000 -e OLLAMA_HOST=http://host.docker.internal:11434 kg-entity-traversal
```

## 3. Full stack (docker compose) — API + Ollama

```bash
cp .env.example .env            # optional; defaults are fine
docker compose up --build
# `ollama-init` pulls the model on first run; then open http://localhost:8000
```

To run the stack without Ollama (offline backend): `KG_OFFLINE=1 docker compose up --build`.

## 4. Cloud notes

- The container is stateless; the graph is rebuilt from `data/clinical.json` at
  startup, so it scales horizontally behind a load balancer.
- Set `OLLAMA_HOST` to a managed/hosted Ollama (or a sidecar) only if you want
  prose phrasing; the structured answer is identical without it.
- Health check: `GET /health` returns `{"status":"ok", ...}` — wire it to your
  platform's liveness/readiness probe.
- No secrets are required.

## Configuration

| Var | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (prose only) |
| `KG_LLM_MODEL` | `llama3.2` | model used for prose phrasing |
| `KG_OFFLINE` | `0` | `1` forces deterministic offline phrasing |
| `KG_DATA` | `data/clinical.json` | records loaded at startup |
