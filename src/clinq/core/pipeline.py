"""EntityTraversalQA pipeline: load the graph, then answer via NL → traversal.

The answer comes entirely from `traversal.answer` (deterministic, structured).
The LLM backend only adds an optional prose phrasing on top; the structured
intent / matched / results are always returned regardless of backend.
"""

from __future__ import annotations

from clinq.core import traversal
from clinq.core.backends import get_llm
from clinq.core.graph import PropertyGraph
from clinq.core.loader import build_graph


class EntityTraversalQA:
    def __init__(self, graph: PropertyGraph | None = None):
        self.llm = get_llm()
        self.graph = graph if graph is not None else PropertyGraph()

    def load(self, data: dict) -> int:
        """(Re)build the graph from structured records. Returns node count."""
        self.graph = build_graph(data)
        return len(self.graph)

    def ask(self, question: str) -> dict:
        """Run the NL → graph traversal and phrase the structured result."""
        result = traversal.answer(self.graph, question)
        answer = self.llm.generate(result)
        return {
            "answer": answer,
            "intent": result["intent"],
            "matched": result["matched"],
            "results": result["results"],
            "explanation": result["explanation"],
        }
