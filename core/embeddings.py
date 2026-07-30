"""
Embedding generation. Two backends:
  - Ollama: uses a pulled embedding model (e.g. nomic-embed-text, mxbai-embed-large)
  - sentence-transformers: pure-local, CPU-friendly, no server needed (lazy-imported
    so the app doesn't require torch unless you actually pick this backend)
"""
from __future__ import annotations
from typing import List
from core.llm_client import BaseLLMClient

_st_model_cache = {}


def embed_with_ollama(client: BaseLLMClient, model: str, texts: List[str]) -> List[List[float]]:
    return client.embed(model, texts)


def embed_with_sentence_transformers(model_name: str, texts: List[str]) -> List[List[float]]:
    if model_name not in _st_model_cache:
        from sentence_transformers import SentenceTransformer
        _st_model_cache[model_name] = SentenceTransformer(model_name)
    model = _st_model_cache[model_name]
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def embed_texts(backend: str, texts: List[str], ollama_client: BaseLLMClient = None,
                ollama_model: str = "nomic-embed-text", st_model: str = "all-MiniLM-L6-v2"
                ) -> List[List[float]]:
    if not texts:
        return []
    if backend == "sentence_transformers":
        return embed_with_sentence_transformers(st_model, texts)
    return embed_with_ollama(ollama_client, ollama_model, texts)
