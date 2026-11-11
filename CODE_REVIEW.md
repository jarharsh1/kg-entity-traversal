# Code Review — kg-entity-traversal

A reviewer-facing deep-dive on the correctness findings in the NL→graph
**traversal** engine and the fixes that landed for them. Each supported question
maps to an *intent* (a regex matcher + a hand-written typed walk); the review
focuses on **intent dispatch** and **entity matching**, where the real defects
were, and records what was traced and left unchanged.

Fixes reviewed here: commits `c16cc89` (traversal hardening) and `c20221c`
(dataset path). Everything below quotes the actual before/after from those
commits.

---

## Finding 1 — "on" over-triggers `patients_on_medication` (High)

**Where:** `src/clinq/core/traversal.py` — the `patients_on_medication` intent
regex and the dispatch loop in `answer` (`:279`–`:285`).

**Root cause.** The `patients_on_medication` matcher keys on the very common
word **"on"**:

```python
re.compile(r"\b(?:patients?|who)\b.*\b(?:on|take|takes|taking|prescribed|using|use)\b")
```

Dispatch was *first-regex-wins, unconditionally return*:

```python
# before
    for name, pattern, traversal in _INTENTS:
        if pattern.search(q):
            return traversal(graph, q)
```

So a question that merely contains "who … on …" but is **not** about medication
— e.g. *"who is on call today"* — matched the intent, ran the medication
traversal, found no `Medication` entity, and returned a confidently-empty
`patients_on_medication` result (`matched: null, results: []`). The user got a
wrong, authoritative-looking "no patients" answer instead of a graceful
"nothing matched" from the fallback.

The clean fix is **not** to enumerate every non-medical "on" phrase in the
regex (unwinnable) but to make a *weak-cue* intent step aside when it resolves
no entity.

**Fix.** Each intent carries a `fallthrough` flag; a `fallthrough` intent that
matches its regex but resolves **no** entity is skipped so dispatch continues to
the next intent / the entity-lookup fallback:

```python
# after
_INTENTS: list[tuple[str, re.Pattern, object, bool]] = [
    ("medications_treating_condition", ..., _medications_treating, False),
    ("medications_of_patient",         ..., _medications_of_patient, True),
    ("conditions_of_patient",          ..., _conditions_of_patient,  False),
    ("patients_on_medication",         ..., _patients_on_medication, True),
    ("prescribed_by_provider",         ..., _prescribed_by_provider, False),
]

    for name, pattern, traversal, fallthrough in _INTENTS:
        if not pattern.search(q):
            continue
        result = traversal(graph, q)
        if fallthrough and result["matched"] is None:
            continue  # weak cue fired but no entity resolved — try the next rule
        return result
```

Now *"who is on call today"* falls through to `entity_lookup`
(`matched: null`), while the genuine *"which patients are on metformin"* still
resolves `patients_on_medication → Patient 002`. Strong-cue intents keep
`fallthrough=False`, so e.g. *"what medications treat scurvy"* still returns the
intent's own empty result rather than silently masquerading as another intent.

**Regression tests.**
`tests/test_traversal.py::test_non_medication_on_question_falls_through_to_fallback`
(→ `entity_lookup`, empty) and `test_patients_on_real_medication_still_routes`
(→ `patients_on_medication`, Patient 002).

---

## Finding 2 — Patient-centric medication question had no intent (Medium)

**Where:** `src/clinq/core/traversal.py:166` — new `_medications_of_patient`.

**Root cause.** The engine answered *"which patients are on <med>"* (med →
patients) but had **no** intent for the inverse, patient-centric question
*"what medications is Patient 001 taking?"* — a question the clinical demo set
obviously invites. It fell through to `entity_lookup`, which just lists a node's
direct neighbors (including the patient's encounters), not the prescribed
medications.

**Fix.** Add an intent that walks the correct two hops,
`Patient → HAS_ENCOUNTER(out) → Encounter → PRESCRIBED(out) → Medication`:

```python
def _medications_of_patient(graph, phrase):
    pt = _find_entity(graph, phrase, types=("Patient",))
    if pt is None:
        return _result("medications_of_patient", None, [], "...")
    encounters = [dst for (edge, direction, dst) in graph.neighbors(pt.id)
                  if direction == "out" and edge.rel == "HAS_ENCOUNTER"]
    meds = []
    for enc in encounters:
        meds += [dst for (edge, direction, dst) in graph.neighbors(enc)
                 if direction == "out" and edge.rel == "PRESCRIBED"]
    return _result("medications_of_patient", _name(pt), _results(graph, meds), "...")
```

It is ordered **after** `medications_treating_condition` (so "what medications
treat hypertension" still routes to treatment) and marked `fallthrough=True`
(so a medication/patient-shaped question that resolves no patient steps aside).
*"What medications is Patient 001 taking?"* → `Lisinopril`;
*"…Patient 002 take"* → `Metformin, Amlodipine`.

**Regression tests.** `test_medications_of_patient` and
`test_medications_of_patient_002`.

---

## Finding 3 — Raw-substring entity matching (Low)

**Where:** `src/clinq/core/traversal.py:49` — `_find_entity`, now via the new
`_contains_word` helper (`:36`).

**Root cause.** Entity matching tested raw substring containment:

```python
# before
        if name_l in phrase_l or id_l in phrase_l:
            score = max(len(name_l) if name_l in phrase_l else 0,
                        len(id_l) if id_l in phrase_l else 0)
```

A node name/id could match **inside an unrelated longer word**: a medication
"Amlo" matches "amlodipinefree", "metformin" matches "metforminium". On the
clinical sample the names are distinct enough to be safe, but this is a
retargeting footgun — point the loader at another domain with short names and
spurious matches appear.

**Fix.** Match on word boundaries:

```python
# after
def _contains_word(haystack, needle):
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle.lower())}(?!\w)", haystack.lower()) is not None

        name_hit = _contains_word(phrase_l, name_l)
        id_hit = _contains_word(phrase_l, id_l)
        if name_hit or id_hit:
            score = max(len(name_l) if name_hit else 0, len(id_l) if id_hit else 0)
```

The longest-match preference ("patient 001" beats "patient") is preserved — only
the containment test changed from substring to word-bounded.

**Regression test.** `test_entity_match_is_word_bounded` asserts
`_contains_word("who takes metformin", "metformin")` is true and
`_contains_word("metforminium tablets", "metformin")` is false.

---

## Finding 4 — CWD-relative sample path (Low)

**Where:** `src/clinq/api/main.py:41` — `_SAMPLE`.

**Root cause.** Startup loaded the dataset from a CWD-relative path:

```python
# before
_SAMPLE = Path("data/clinical.json")
```

Started from anywhere but the repo root, `_SAMPLE.exists()` was false and the
graph **silently** stayed empty — `/health` then reports zero nodes with no
error. `_WEB_DIR` was already `__file__`-relative, so the two were inconsistent.

**Fix.** Resolve from the package via a shared `_REPO_ROOT`:

```python
# after
_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEB_DIR = _REPO_ROOT / "web"
...
_SAMPLE = _REPO_ROOT / "data" / "clinical.json"
```

**Regression test.** `tests/test_api_e2e.py::test_sample_path_is_cwd_independent`
asserts `_SAMPLE` is absolute and exists.

---

## Verified correct, not changed

Traced during review and found correct; left unchanged to keep the diff scoped.

- **Every intent's hop direction (`core/traversal.py`).** `medications_treating`
  (Condition → incoming `TREATS` → Medication), `conditions_of_patient`
  (Patient → outgoing `HAS_CONDITION` → Condition), `prescribed_by_provider`
  (Provider → incoming `SEEN_BY` → Encounter → outgoing `PRESCRIBED` →
  Medication), and `patients_on_medication` (Medication → incoming `PRESCRIBED`
  → Encounter → incoming `HAS_ENCOUNTER` → Patient) all walk the loader's schema
  directions. No reversed hop — the class of bug that returns plausible-but-wrong
  answers.
- **Graph engine (`core/graph.py`).** `neighbors` in/out tagging and `expand`'s
  k-hop BFS (edge dedup, `seen` guard, `hops=0` and missing-seed handling) are
  correct — identical engine to the sibling repos.
- **Loader (`core/loader.py`).** Nodes added before the edges that reference
  them; all relations built in schema direction.
- **The `prescribed_by_provider` provider-cue regex** (from an earlier round)
  requires `did … prescrib` / `prescribed by` rather than any "prescrib", so it
  no longer hijacks patient-subject "prescribed" questions — re-verified here and
  left as is.
