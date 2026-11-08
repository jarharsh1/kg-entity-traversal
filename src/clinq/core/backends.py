"""Optional LLM backend for PROSE PHRASING ONLY (Ollama-first, offline fallback).

The traversal engine already produces the structured answer; the LLM here is a
nicety that turns that structured result into one sentence. Offline (the default
for CI/tests, and whenever no Ollama is running) this is purely deterministic: it
joins the result names into a sentence — no model is contacted. Mirrors the
get_llm()/OllamaLLM shape of the sibling GraphRAG engine, kept minimal.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from clinq.config import settings


def phrase(result: dict) -> str:
    """Deterministically turn a traversal result into a sentence (no model)."""
    names = [r["name"] for r in result.get("results", [])]
    matched = result.get("matched")
    if not names:
        if matched is None:
            return "Nothing in the question matched an entity in the knowledge graph."
        return f"No results found for '{matched}'."
    joined = ", ".join(names[:-1]) + (f" and {names[-1]}" if len(names) > 1 else names[0])
    if matched:
        return f"For '{matched}': {joined}."
    return joined + "."


class LLM(Protocol):
    def generate(self, result: dict) -> str: ...


class OfflineLLM:
    """Deterministic passthrough — formats the structured result, no model call."""

    def generate(self, result: dict) -> str:
        return phrase(result)


class OllamaLLM:
    """Prettifies the structured result via a local Ollama model."""

    _PROMPT = (
        "Rephrase the following knowledge-graph lookup result as one natural "
        "sentence. Do not add facts. Result:\n{summary}\n"
    )

    def __init__(self, host: str, model: str):
        self.host, self.model = host.rstrip("/"), model

    def generate(self, result: dict) -> str:
        summary = phrase(result)
        try:
            with httpx.Client(timeout=120) as c:
                r = c.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": self._PROMPT.format(summary=summary),
                        "stream": False,
                    },
                )
                r.raise_for_status()
                return r.json()["response"].strip() or summary
        except Exception:
            return summary


def _ollama_up(host: str) -> bool:
    try:
        with httpx.Client(timeout=2) as c:
            return c.get(f"{host.rstrip('/')}/api/tags").status_code == 200
    except Exception:
        return False


def get_llm() -> LLM:
    if not settings.offline and _ollama_up(settings.ollama_host):
        return OllamaLLM(settings.ollama_host, settings.llm_model)
    return OfflineLLM()
