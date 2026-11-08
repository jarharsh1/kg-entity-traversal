"""End-to-end CLI demo: load the clinical graph and answer via NL → traversal.

    python demo.py            # Ollama for prose if up, else offline
    KG_OFFLINE=1 python demo.py
"""

import json
from pathlib import Path

from clinq.core.pipeline import EntityTraversalQA

QUESTIONS = [
    "Which medications treat hypertension?",
    "Which patients are on metformin?",
    "What conditions does Patient 001 have?",
    "What did Dr. Rao prescribe?",
]


def main() -> None:
    data = json.loads(Path("data/clinical.json").read_text(encoding="utf-8"))
    qa = EntityTraversalQA()
    n = qa.load(data)
    print(f"Loaded graph with {n} nodes (backend: {type(qa.llm).__name__})\n")

    for q in QUESTIONS:
        result = qa.ask(q)
        names = ", ".join(r["name"] for r in result["results"]) or "(none)"
        print(f"Q: {q}")
        print(f"   intent : {result['intent']}")
        print(f"   matched: {result['matched']}")
        print(f"   results: {names}")
        print(f"   answer : {result['answer']}")
        print()


if __name__ == "__main__":
    main()
