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


def test_entity_lookup_fallback_hides_encounter_ids():
    # Encounters have no name; their raw ids ("enc:1001") must not leak as result
    # names in the fallback list.
    r = traversal.answer(GRAPH, "Tell me about Lisinopril")
    assert all(not name.startswith("enc:") for name in _names(r))
    assert all(res["type"] != "Encounter" for res in r["results"])


def test_patients_prescribed_medication_not_hijacked_by_provider_intent():
    # "which patients are prescribed <med>" must route to patients_on_medication
    # (not prescribed_by_provider, which previously hijacked any "prescrib").
    r = traversal.answer(GRAPH, "Which patients are prescribed metformin?")
    assert r["intent"] == "patients_on_medication"
    assert r["matched"] == "Metformin"
    assert _names(r) == {"Patient 002"}


def test_who_is_prescribed_medication_routes_to_patients():
    r = traversal.answer(GRAPH, "Who is prescribed lisinopril?")
    assert r["intent"] == "patients_on_medication"
    assert r["matched"] == "Lisinopril"
    assert _names(r) == {"Patient 001"}


def test_what_did_provider_prescribe_still_routes_to_provider():
    # The provider intent must still win for "what did <provider> prescribe".
    r = traversal.answer(GRAPH, "What did Dr. Rao prescribe?")
    assert r["intent"] == "prescribed_by_provider"
    assert r["matched"] == "Dr. Rao"
    assert _names(r) == {"Metformin", "Amlodipine"}


def test_no_match_returns_empty():
    r = traversal.answer(GRAPH, "Which medications treat scurvy?")
    assert r["intent"] == "medications_treating_condition"
    assert r["matched"] is None
    assert r["results"] == []


def test_medications_of_patient():
    # Patient-centric medications question: Patient -> encounters -> prescribed meds.
    r = traversal.answer(GRAPH, "What medications is Patient 001 taking?")
    assert r["intent"] == "medications_of_patient"
    assert r["matched"] == "Patient 001"
    assert _names(r) == {"Lisinopril"}
    assert all(res["type"] == "Medication" for res in r["results"])


def test_medications_of_patient_002():
    r = traversal.answer(GRAPH, "What medications does Patient 002 take?")
    assert r["intent"] == "medications_of_patient"
    assert r["matched"] == "Patient 002"
    assert _names(r) == {"Metformin", "Amlodipine"}


def test_non_medication_on_question_falls_through_to_fallback():
    # A bare-"on" question about something unrelated must NOT return an empty
    # patients_on_medication result; it falls through to the entity lookup.
    r = traversal.answer(GRAPH, "Who is on call today?")
    assert r["intent"] == "entity_lookup"
    assert r["matched"] is None
    assert r["results"] == []


def test_patients_on_real_medication_still_routes():
    # The genuine "patients on <med>" case must still resolve.
    r = traversal.answer(GRAPH, "Which patients are on metformin?")
    assert r["intent"] == "patients_on_medication"
    assert r["matched"] == "Metformin"
    assert _names(r) == {"Patient 002"}


def test_entity_match_is_word_bounded():
    # A node name must not match inside an unrelated longer word.
    assert traversal._contains_word("who takes metformin", "metformin")
    assert not traversal._contains_word("metforminium tablets", "metformin")
