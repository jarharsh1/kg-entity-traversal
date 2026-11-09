"""End-to-end API tests: health, /ask traversal, and the served UI."""

from fastapi.testclient import TestClient

from clinq.api import main as api_main
from clinq.api.main import app

client = TestClient(app)


def test_sample_path_is_cwd_independent():
    # The bundled dataset must resolve from the package location, not the CWD.
    assert api_main._SAMPLE.is_absolute()
    assert api_main._SAMPLE.exists()


def test_health_offline():
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["backend"] == "offline"
    assert h.json()["graph_nodes"] > 0  # sample loaded at startup


def test_ask_drug_question():
    r = client.post("/ask", json={"question": "Which medications treat hypertension?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "medications_treating_condition"
    assert body["matched"] == "Hypertension"
    names = {res["name"] for res in body["results"]}
    assert names == {"Lisinopril", "Amlodipine"}
    assert body["answer"]


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Knowledge-Graph Traversal QA" in r.text


def test_static_js_served():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "/ask" in r.text  # the UI calls the ask endpoint
