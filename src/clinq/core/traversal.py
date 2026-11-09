"""Natural-language → graph TRAVERSAL (the distinctive engine).

This is NOT neighborhood serialization. Each supported question maps to a small,
explicit *intent pattern*: a keyword/regex detector plus a hand-written traversal
over the property graph that walks specific typed edges and returns the nodes at
the end of that walk. The result is structured (not prose), deterministic, and
unit-testable.

Adding a new capability = adding one intent (a matcher + a traversal). The engine
is domain-agnostic: it only assumes the relation names used by the loader
(HAS_CONDITION, TREATS, SEEN_BY, PRESCRIBED, HAS_ENCOUNTER). Point the loader at a
different domain's records and rename the relations in one place to retarget it.

    answer(graph, question) -> {
        "intent":      "<intent name>",
        "matched":     "<entity id/name>" | None,
        "results":     [{"type": ..., "name": ...}, ...],
        "explanation": "<which traversal ran, in words>",
    }
"""

from __future__ import annotations

import re

from clinq.core.graph import Node, PropertyGraph


# --------------------------------------------------------------------------- #
# Entity matching helpers
# --------------------------------------------------------------------------- #
def _name(node: Node) -> str:
    return str(node.attrs.get("name", node.id))


def _contains_word(haystack: str, needle: str) -> bool:
    """True if `needle` occurs in `haystack` on word boundaries (case-insensitive).

    Word-boundary (rather than raw-substring) matching prevents a short node
    name/id from matching inside an unrelated longer word — e.g. a medication
    "Amlo" would not spuriously match "amlodipinefree". Reduces the retargeting
    footgun while keeping ordinary name matches intact.
    """
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle.lower())}(?!\w)", haystack.lower()) is not None


def _find_entity(graph: PropertyGraph, phrase: str, types: tuple[str, ...] | None = None):
    """Word-boundary match of node names/ids against `phrase`.

    Prefers the longest name/id that appears in the phrase (so "patient 001"
    beats "patient"). Restrict to `types` when the intent expects a kind of node.
    """
    phrase_l = phrase.lower()
    best: Node | None = None
    best_len = -1
    for node in graph.nodes.values():
        if types and node.type not in types:
            continue
        name_l = _name(node).lower()
        id_l = node.id.lower()
        name_hit = _contains_word(phrase_l, name_l)
        id_hit = _contains_word(phrase_l, id_l)
        if name_hit or id_hit:
            score = max(len(name_l) if name_hit else 0,
                        len(id_l) if id_hit else 0)
            if score > best_len:
                best, best_len = node, score
    return best


def _results(graph: PropertyGraph, ids) -> list[dict]:
    """Turn an ordered, de-duplicated id iterable into result dicts."""
    out: list[dict] = []
    seen: set[str] = set()
    for nid in ids:
        if nid in seen or nid not in graph.nodes:
            continue
        seen.add(nid)
        node = graph.nodes[nid]
        out.append({"type": node.type, "name": _name(node)})
    return out


def _result(intent, matched, results, explanation) -> dict:
    return {
        "intent": intent,
        "matched": matched,
        "results": results,
        "explanation": explanation,
    }


# --------------------------------------------------------------------------- #
# Individual intent traversals
# --------------------------------------------------------------------------- #
def _medications_treating(graph: PropertyGraph, phrase: str) -> dict:
    """Condition (by name) → incoming TREATS edges → Medication nodes."""
    cond = _find_entity(graph, phrase, types=("Condition",))
    if cond is None:
        return _result("medications_treating_condition", None, [],
                       "No condition in the question matched a node in the graph.")
    meds = [src for (edge, direction, src) in graph.neighbors(cond.id)
            if direction == "in" and edge.rel == "TREATS"]
    return _result(
        "medications_treating_condition", _name(cond), _results(graph, meds),
        f"Matched Condition '{_name(cond)}', then walked incoming TREATS edges to "
        f"the Medication nodes that treat it.",
    )


def _conditions_of_patient(graph: PropertyGraph, phrase: str) -> dict:
    """Patient (by name) → outgoing HAS_CONDITION edges → Condition nodes."""
    pt = _find_entity(graph, phrase, types=("Patient",))
    if pt is None:
        return _result("conditions_of_patient", None, [],
                       "No patient in the question matched a node in the graph.")
    conds = [dst for (edge, direction, dst) in graph.neighbors(pt.id)
             if direction == "out" and edge.rel == "HAS_CONDITION"]
    return _result(
        "conditions_of_patient", _name(pt), _results(graph, conds),
        f"Matched Patient '{_name(pt)}', then walked outgoing HAS_CONDITION edges "
        f"to the Condition nodes.",
    )


def _prescribed_by_provider(graph: PropertyGraph, phrase: str) -> dict:
    """Provider → incoming SEEN_BY → Encounter → outgoing PRESCRIBED → Medication."""
    prov = _find_entity(graph, phrase, types=("Provider",))
    if prov is None:
        return _result("prescribed_by_provider", None, [],
                       "No provider in the question matched a node in the graph.")
    encounters = [src for (edge, direction, src) in graph.neighbors(prov.id)
                  if direction == "in" and edge.rel == "SEEN_BY"]
    meds: list[str] = []
    for enc in encounters:
        meds += [dst for (edge, direction, dst) in graph.neighbors(enc)
                 if direction == "out" and edge.rel == "PRESCRIBED"]
    return _result(
        "prescribed_by_provider", _name(prov), _results(graph, meds),
        f"Matched Provider '{_name(prov)}', walked incoming SEEN_BY to their "
        f"Encounters, then outgoing PRESCRIBED to the Medication nodes.",
    )


def _patients_on_medication(graph: PropertyGraph, phrase: str) -> dict:
    """Medication → incoming PRESCRIBED → Encounter → incoming HAS_ENCOUNTER → Patient."""
    med = _find_entity(graph, phrase, types=("Medication",))
    if med is None:
        return _result("patients_on_medication", None, [],
                       "No medication in the question matched a node in the graph.")
    encounters = [src for (edge, direction, src) in graph.neighbors(med.id)
                  if direction == "in" and edge.rel == "PRESCRIBED"]
    patients: list[str] = []
    for enc in encounters:
        patients += [src for (edge, direction, src) in graph.neighbors(enc)
                     if direction == "in" and edge.rel == "HAS_ENCOUNTER"]
    return _result(
        "patients_on_medication", _name(med), _results(graph, patients),
        f"Matched Medication '{_name(med)}', walked incoming PRESCRIBED to the "
        f"Encounters, then incoming HAS_ENCOUNTER to the Patient nodes.",
    )


def _medications_of_patient(graph: PropertyGraph, phrase: str) -> dict:
    """Patient → outgoing HAS_ENCOUNTER → Encounter → outgoing PRESCRIBED → Medication."""
    pt = _find_entity(graph, phrase, types=("Patient",))
    if pt is None:
        return _result("medications_of_patient", None, [],
                       "No patient in the question matched a node in the graph.")
    encounters = [dst for (edge, direction, dst) in graph.neighbors(pt.id)
                  if direction == "out" and edge.rel == "HAS_ENCOUNTER"]
    meds: list[str] = []
    for enc in encounters:
        meds += [dst for (edge, direction, dst) in graph.neighbors(enc)
                 if direction == "out" and edge.rel == "PRESCRIBED"]
    return _result(
        "medications_of_patient", _name(pt), _results(graph, meds),
        f"Matched Patient '{_name(pt)}', walked outgoing HAS_ENCOUNTER to their "
        f"Encounters, then outgoing PRESCRIBED to the Medication nodes.",
    )


def _entity_lookup(graph: PropertyGraph, phrase: str) -> dict:
    """Fallback: match any node by name and list its direct relations."""
    node = _find_entity(graph, phrase)
    if node is None:
        return _result("entity_lookup", None, [],
                       "No entity in the question matched a node in the graph.")
    # Skip Encounter nodes: they carry no name, so their raw ids ("enc:1001")
    # would otherwise leak into the user-facing result list as names.
    related: list[str] = []
    for edge, direction, other in graph.neighbors(node.id):
        other_node = graph.nodes.get(other)
        if other_node is not None and other_node.type == "Encounter":
            continue
        related.append(other)
    return _result(
        "entity_lookup", _name(node), _results(graph, related),
        f"No specific traversal matched; matched entity '{_name(node)}' "
        f"({node.type}) and listed its directly related nodes.",
    )


# --------------------------------------------------------------------------- #
# Intent detection + dispatch
# --------------------------------------------------------------------------- #
# Ordered (name, regex, traversal, fallthrough). First matching regex wins; the
# regexes are intentionally specific so the right traversal runs before the
# fallback.
#
# `patients_on_medication` is placed before `prescribed_by_provider` so a
# patient-subject question like "which patients are prescribed metformin" routes
# to the medication traversal. The provider intent requires a provider cue
# ("what did X prescribe" / "prescribed by X") rather than any occurrence of
# "prescrib", so it no longer hijacks patient-subject questions.
#
# `fallthrough` marks an intent whose matcher keys on a common word (e.g. bare
# "on") and may fire on unrelated questions ("who is on call today"). When such
# an intent matches its regex but resolves NO entity, dispatch continues to the
# next intent / the fallback instead of returning an empty, misleading result.
_INTENTS: list[tuple[str, re.Pattern, object, bool]] = [
    (
        "medications_treating_condition",
        re.compile(r"\b(what|which)\b.*\b(medication|drug|med|medicine)s?\b.*\btreat"),
        _medications_treating,
        False,
    ),
    (
        "medications_of_patient",
        re.compile(
            r"\b(?:medication|drug|med|medicine)s?\b.*\bpatients?\b"
            r".*\b(?:take|takes|taking|on|is on|prescribed|have|having)\b"
            r"|\b(?:medication|drug|med|medicine)s?\b.*\b(?:does|do|is|are)\b"
            r".*\bpatients?\b"
        ),
        _medications_of_patient,
        True,
    ),
    (
        "conditions_of_patient",
        re.compile(r"\b(condition|diagnos|disease|problem)s?\b.*\b(does|do|has|have|for)\b"),
        _conditions_of_patient,
        False,
    ),
    (
        "patients_on_medication",
        re.compile(
            r"\b(?:patients?|who)\b.*\b(?:on|take|takes|taking|prescribed|using|use)\b"
        ),
        _patients_on_medication,
        True,
    ),
    (
        "prescribed_by_provider",
        re.compile(r"\b(?:did\b.*\bprescrib|prescribed by\b)"),
        _prescribed_by_provider,
        False,
    ),
]


def answer(graph: PropertyGraph, question: str) -> dict:
    """Map a natural-language question to a graph traversal and return results.

    Deterministic: intent detection is regex/keyword based, entity matching is a
    word-boundary match against node names. No LLM involved.

    An intent marked ``fallthrough`` that matches its regex but resolves no
    entity is skipped (its matcher is only a weak cue), so dispatch continues to
    the next intent or the entity-lookup fallback rather than returning an empty
    result for an unrelated question.
    """
    if len(graph) == 0:
        return _result(None, None, [], "The knowledge graph is empty.")

    q = question.lower().strip()
    for name, pattern, traversal, fallthrough in _INTENTS:
        if not pattern.search(q):
            continue
        result = traversal(graph, q)
        if fallthrough and result["matched"] is None:
            continue  # weak cue fired but no entity resolved — try the next rule
        return result

    # No intent pattern matched — fall back to entity lookup.
    return _entity_lookup(graph, q)
