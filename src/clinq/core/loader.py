"""Build the clinical knowledge graph from structured records.

Input is a dict with `patients`, `providers`, `conditions`, `medications`, and
`encounters`. Each encounter links a patient, a provider, the conditions
diagnosed, and the medications prescribed, producing the relations:

    Patient    -HAS_ENCOUNTER-> Encounter
    Encounter  -SEEN_BY->       Provider
    Encounter  -DIAGNOSED->     Condition
    Encounter  -PRESCRIBED->    Medication
    Medication -TREATS->        Condition   (drug knowledge, from `medications`)
    Patient    -HAS_CONDITION-> Condition   (rolled up for convenience)

This structured build keeps the graph trustworthy; GraphRAG's value is in
graph-aware retrieval and synthesis over it (e.g. drug/condition neighborhoods),
not in brittle entity extraction. The sample data is synthetic — no real PHI.
"""

from __future__ import annotations

from clinq.core.graph import PropertyGraph


def build_graph(data: dict) -> PropertyGraph:
    g = PropertyGraph()

    for p in data.get("providers", []):
        g.add_node(p["id"], "Provider", name=p.get("name", p["id"]),
                   specialty=p.get("specialty"))

    for c in data.get("conditions", []):
        g.add_node(c["id"], "Condition", name=c.get("name", c["id"]),
                   icd10=c.get("icd10"))

    for m in data.get("medications", []):
        g.add_node(m["id"], "Medication", name=m.get("name", m["id"]),
                   drug_class=m.get("drug_class"))
        for cond in m.get("treats", []):
            if cond in g.nodes:
                g.add_edge(m["id"], cond, "TREATS")

    for pt in data.get("patients", []):
        g.add_node(pt["id"], "Patient", name=pt.get("name", pt["id"]),
                   age=pt.get("age"), sex=pt.get("sex"))

    for enc in data.get("encounters", []):
        eid = enc["id"]
        g.add_node(eid, "Encounter", date=enc.get("date"), reason=enc.get("reason"))
        if enc.get("patient"):
            g.add_edge(enc["patient"], eid, "HAS_ENCOUNTER")
        if enc.get("provider"):
            g.add_edge(eid, enc["provider"], "SEEN_BY")
        for cond in enc.get("diagnoses", []):
            if cond in g.nodes:
                g.add_edge(eid, cond, "DIAGNOSED")
                if enc.get("patient"):
                    g.add_edge(enc["patient"], cond, "HAS_CONDITION")
        for med in enc.get("medications", []):
            if med in g.nodes:
                g.add_edge(eid, med, "PRESCRIBED")

    return g
