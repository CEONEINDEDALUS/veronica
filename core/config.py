"""
Veronica - configuration model & persistence.
Settings are stored as JSON in the user's home directory so they survive restarts.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_DIR = Path.home() / ".veronica_rag"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"
PERSIST_DIR = str(APP_DIR / "vector_store")
LOG_PATH = APP_DIR / "veronica.log"


@dataclass
class Config:
    # --- Backend connection ---
    ollama_host: str = "http://localhost:11434"

    # --- Models ---
    chat_model: str = ""                     # populated at runtime from /api/tags
    embedding_backend: str = "ollama"        # "ollama" | "sentence_transformers"
    ollama_embedding_model: str = "nomic-embed-text"
    st_embedding_model: str = "all-MiniLM-L6-v2"

    # --- Context window handling (the "low context" problem) ---
    auto_detect_context: bool = True
    manual_context_window: int = 4096
    reserved_output_tokens: int = 768
    reserved_system_tokens: int = 300
    max_chat_history_turns: int = 6
    enable_context_compression: bool = True  # hierarchical summarization fallback
    compression_target_ratio: float = 0.5    # summarize until content is this fraction of budget

    # --- Retrieval / chunking ---
    chunk_size: int = 900
    chunk_overlap: int = 150
    top_k: int = 6
    candidate_multiplier: int = 3            # fetch top_k * multiplier candidates before budget-fitting
    similarity_floor: float = 0.0            # 0 = disabled; else min cosine similarity to keep a chunk

    # --- Generation ---
    temperature: float = 0.4
    system_prompt: str = (
        "You are Veronica, a precise and honest assistant that answers strictly using the "
        "provided context from the user's private documents. If the answer is not contained "
        "in the context, say so clearly instead of guessing. Cite source file names when relevant."
    )

    # --- Knowledge base ---
    active_kb: str = "default"

    # --- UI ---
    accent_color: str = "#8B5CF6"  # violet, nods to the Veronica flower

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                base = cls()
                for k, v in data.items():
                    if hasattr(base, k):
                        setattr(base, k, v)
                return base
            except Exception:
                pass
        return cls()


config = Config.load()
