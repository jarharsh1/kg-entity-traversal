"""Runtime configuration (env with local defaults).

The traversal engine needs no model — answers are structured. The optional LLM
only prettifies them into prose (Ollama-first, deterministic offline fallback),
so all settings here are for that optional phrasing step. Env prefix is KG_.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    data_file: str = os.getenv("KG_DATA", "data/clinical.json")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("KG_LLM_MODEL", "llama3.2")
    offline: bool = os.getenv("KG_OFFLINE", "0") == "1"


settings = Settings()
