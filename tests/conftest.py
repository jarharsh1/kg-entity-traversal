"""Force the offline backend for the whole test session (no Ollama in CI)."""

import os

os.environ.setdefault("KG_OFFLINE", "1")
