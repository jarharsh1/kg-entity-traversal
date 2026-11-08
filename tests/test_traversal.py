"""Unit-test each NL → graph traversal intent against the clinical sample."""

import json
from pathlib import Path

from clinq.core import traversal
from clinq.core.loader import build_graph

DATA = json.loads(Path("data/clinical.json").read_text(encoding="utf-8"))
GRAPH = build_graph(DATA)


def _names(result):
    return {r["name"] for r in result["results"]}


def test_medications_treating_hypertension():
    r = traversal.answer(GRAPH, "Which medications treat hypertension?")
    assert r["intent"] == "medications_treating_condition"
    assert r["matched"] == "Hypertension"
    assert _names(r) == {"Lisinopril", "Amlodipine"}
    assert all(res["type"] == "Medication" for res in r["results"])


def test_patients_on_metformin():
    r = traversal.answer(GRAPH, "Which patients are on metformin?")
    assert r["intent"] == "patients_on_medication"
    assert r["matched"] == "Metformin"
    # Metformin was prescribed only at Patient 002's encounter.
    assert _names(r) == {"Patient 002"}


def test_conditions_for_patient_001():
    r = traversal.answer(GRAPH, "What conditions does Patient 001 have?")
    assert r["intent"] == "conditions_of_patient"
    assert r["matched"] == "Patient 001"
    assert _names(r) == {"Hypertension", "Chronic Kidney Disease"}


def test_prescribed_by_provider():
    r = traversal.answer(GRAPH, "What did Dr. Rao prescribe?")
    assert r["intent"] == "prescribed_by_provider"
    assert r["matched"] == "Dr. Rao"
    # Dr. Rao's encounter prescribed metformin and amlodipine.
    assert _names(r) == {"Metformin", "Amlodipine"}


def test_entity_lookup_fallback():
    r = traversal.answer(GRAPH, "Tell me about Lisinopril")
    assert r["intent"] == "entity_lookup"
    assert r["matched"] == "Lisinopril"
    # Lisinopril's direct relations include the conditions it treats.
    assert "Hypertension" in _names(r)


def test_no_match_returns_empty():
    r = traversal.answer(GRAPH, "Which medications treat scurvy?")
    assert r["intent"] == "medications_treating_condition"
    assert r["matched"] is None
    assert r["results"] == []
