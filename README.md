# Knowledge-Graph Traversal QA Engine

A **domain-agnostic** engine that answers questions by mapping natural language
to a **graph traversal** — *pattern-based intent matching* over a property graph,
**not** neighborhood serialization. Each supported question is an explicit
*intent*: a keyword/regex detector plus a hand-written walk over specific typed
edges that returns the nodes at the end of that walk. Answers are **structured**
(intent + matched entity + result nodes + a plain-language explanation of which
traversal ran), deterministic, and unit-testable.

**Why traversal, not serialization.** Text RAG retrieves disconnected passages;
"serialize-the-neighborhood" GraphRAG dumps a k-hop subgraph and hopes the LLM
reads it right. This engine instead *walks the exact relations the question is
about* and returns precisely the answer nodes — so "which medications treat
hypertension?" becomes `Condition → (incoming TREATS) → Medication`, and the
result is exact, explainable, and needs no model.

**Ships with a worked example: a clinical knowledge graph** — patients,
encounters, conditions (ICD-10), medications (drug classes), and providers — so
the engine runs end to end out of the box. The graph, traversal intents, and
pipeline are **domain-agnostic**: to target a different domain you swap the
records fed to the loader ([see use cases](#use-cases)) and, if needed, the
relation names the intents walk — you do not change the engine.

> The shipped sample data is **synthetic** — no real patient data / PHI.

## Intents (NL → traversal)

Each question is matched to one intent and its traversal:

| Question shape | Traversal |
|----------------|-----------|
| "what medications treat *&lt;condition&gt;*" | `Condition` → incoming `TREATS` → `Medication` |
| "what conditions does *&lt;patient&gt;* have" | `Patient` → `HAS_CONDITION` → `Condition` |
| "what did *&lt;provider&gt;* prescribe" | `Provider` → incoming `SEEN_BY` → `Encounter` → `PRESCRIBED` → `Medication` |
| "which patients are on / take *&lt;medication&gt;*" | `Medication` → incoming `PRESCRIBED` → `Encounter` → incoming `HAS_ENCOUNTER` → `Patient` |
| *(fallback)* entity lookup | match any node by name → list its direct relations |

Intent detection is regex/keyword based; entities are matched by case-insensitive
substring against node names. `answer(graph, question)` returns
`{"intent", "matched", "results": [{type, name}], "explanation"}`.

Adding a capability = adding one intent (a matcher + a traversal) in
`core/traversal.py`.

## Use cases

The engine is the same; only the records you feed the loader (and the relation
names the intents walk) change. The `PropertyGraph` + pattern-based traversals
are domain-agnostic.

| Domain | Graph (nodes — relations) | Example question → traversal |
|--------|---------------------------|------------------------------|
| **Healthcare** *(shipped example)* | patients — conditions — medications — providers | "Which drugs treat hypertension?" → Condition → TREATS → Medication |
| **Enterprise / HR** | employees — teams — projects | "Who works on project X?" → Project → incoming ASSIGNED → Employee |
| **E-commerce** | customers — orders — products | "What did this customer buy?" → Customer → PLACED → Order → CONTAINS → Product |
| **Supply chain** | suppliers — parts — plants | "Which suppliers provide part Y?" → Part → incoming SUPPLIES → Supplier |
| **Research** | papers — authors — topics | "Who co-authored on topic Z?" → Topic → incoming ABOUT → Paper → AUTHORED_BY → Author |
| **Fraud / finance** | accounts — transactions — entities | "Which accounts funnel into entity W?" → Entity → incoming TRANSFERS_TO → Account |

Only the loader's **input records** and the relation names in the intents change
— the property graph, the traversal mechanism, and the structured result are
identical across all of these.

## Stack

- **Backend:** FastAPI (serves the HTTP API and auto-generates interactive docs
  at `/docs`).
- **Frontend:** a lightweight browser chat UI (`web/`, plain HTML + JS) served by
  FastAPI at `/`, with a details panel showing the intent, matched entity, and
  result nodes for each answer.
- **Model:** *optional* Ollama (local LLM) for prose phrasing only, with a
  deterministic offline fallback. The traversal and structured answer need no
  model — CI-safe.
- **Deploy:** single Docker image, or `docker compose` (API + Ollama). See
  [DEPLOYMENT.md](DEPLOYMENT.md).

Open **<http://localhost:8000>** for the UI once running.

## How it works

```
question ──intent match (regex/keywords)──► intent
                                              │
entity match (substring on node names) ──► seed node
                                              │
                           hand-written traversal over typed edges
                                              │
                                     ▼  structured result
                   {intent, matched, results:[{type,name}], explanation}
                                              │
                        optional LLM ──► one-sentence prose (Ollama / offline)
```

- **Graph** (`core/graph.py`) — dependency-free directed property graph with
  typed nodes/edges and `neighbors(id) -> [(edge, direction, other_id)]`.
- **Loader** (`core/loader.py`) — builds the graph from structured records.
  **This is the domain-specific piece** — point it at your own entity/relation
  records to retarget the engine.
- **Traversal** (`core/traversal.py`) — **the distinctive engine**: intent
  patterns map a question to a specific walk over typed edges and return the
  answer nodes. No LLM.
- **Backend** (`core/backends.py`) — optional LLM, prose phrasing only (Ollama,
  or deterministic offline passthrough that joins result names into a sentence).

## Graph schema (shipped clinical example)

This is the schema of the bundled clinical example (`data/clinical.json`). Any
graph with its own node/relation types works the same way.

| Relation | Meaning |
|----------|---------|
| `Patient -HAS_ENCOUNTER-> Encounter` | a visit |
| `Encounter -SEEN_BY-> Provider` | attending provider |
| `Encounter -DIAGNOSED-> Condition` | diagnosis at the visit |
| `Encounter -PRESCRIBED-> Medication` | prescription at the visit |
| `Medication -TREATS-> Condition` | drug knowledge |
| `Patient -HAS_CONDITION-> Condition` | rolled up for convenience |

## Quickstart

```bash
pip install -r requirements.txt

python demo.py                           # or KG_OFFLINE=1 python demo.py
uvicorn clinq.api.main:app --reload      # API at /docs (loads data/clinical.json)
```

### Example

```bash
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which medications treat hypertension?"}'
```

```json
{
  "answer": "For 'Hypertension': Lisinopril and Amlodipine.",
  "intent": "medications_treating_condition",
  "matched": "Hypertension",
  "results": [
    {"type": "Medication", "name": "Lisinopril"},
    {"type": "Medication", "name": "Amlodipine"}
  ],
  "explanation": "Matched Condition 'Hypertension', then walked incoming TREATS edges to the Medication nodes that treat it."
}
```

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (prose only) |
| `KG_LLM_MODEL` | `llama3.2` | model used for prose phrasing |
| `KG_OFFLINE` | `0` | `1` forces deterministic offline phrasing |
| `KG_DATA` | `data/clinical.json` | records loaded at startup |

## Tests

```bash
pytest -q          # offline; no Ollama needed
```

CI lints, runs tests + the demo offline, and builds the Docker image.
