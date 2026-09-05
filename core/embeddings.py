from __future__ import annotations
import os
import threading
from typing import List
from core.llm_client import BaseLLMClient

_cache = {}
_gguf_cache = {}
_gguf_lock = threading.RLock()


def embed_with_ollama(c: BaseLLMClient, m: str, txts: List[str]) -> List[List[float]]:
    return c.embed(m, txts)


def embed_with_sentence_transformers(mn: str, txts: List[str]) -> List[List[float]]:
    if mn not in _cache:
        from sentence_transformers import SentenceTransformer

        _cache[mn] = SentenceTransformer(mn, device="cpu")
    mdl = _cache[mn]
    vec = mdl.encode(txts, show_progress_bar=False, convert_to_numpy=True, batch_size=16)
    return [v.tolist() for v in vec]


def _resolve_gguf_for_embed(model_path: str) -> str:
    """Handle folder path by picking first valid GGUF inside, similar to GGUFClient."""
    import os, glob
    if not model_path:
        raise RuntimeError("gguf embed model missing (empty path)")
    # direct file
    if os.path.isfile(model_path):
        return model_path
    # realpath file
    rp = os.path.realpath(model_path)
    if os.path.isfile(rp):
        return rp
    # directory - pick first valid
    if os.path.isdir(rp) or os.path.isdir(model_path):
        d = rp if os.path.isdir(rp) else model_path
        g = sorted(glob.glob(os.path.join(d, "*.gguf")) + glob.glob(os.path.join(d, "*.GGUF")))
        for cand in g[:50]:
            if os.path.isfile(cand):
                try:
                    with open(cand, "rb") as fh:
                        if fh.read(4) == b"GGUF":
                            return cand
                except:
                    continue
        raise RuntimeError(f"gguf embed folder has no valid GGUF: {model_path}")
    raise RuntimeError(f"gguf embed model missing {model_path}")

def embed_with_gguf(model_path: str, txts: List[str], n_ctx: int = 4096, n_threads: int = 0, n_gpu: int = 0) -> List[List[float]]:
    import os

    if not model_path:
        raise RuntimeError(f"gguf embed model missing {model_path}")
    # Support folder path (user set folder in settings)
    model_path = _resolve_gguf_for_embed(model_path)

    # Reuse hardened loader from llm_client to get validation + caching + thread safety
    # Import here to avoid circular import at module load
    from core.llm_client import _validate_gguf_path, _get_llama, _gguf_threads

    real = _validate_gguf_path(model_path)
    # Normalize key to realpath to avoid duplicate cache entries for symlink / relative
    key = (os.path.realpath(real), int(n_ctx or 4096), int(n_threads or 0), int(n_gpu or 0))

    with _gguf_lock:
        if key not in _gguf_cache:
            # _get_llama handles full validation and will reuse global cache
            # but we keep a local cache for direct Llama object to avoid double lookup
            # Call _get_llama with embedding=True to ensure same instance
            llama = _get_llama(real, n_ctx=n_ctx, n_threads=n_threads, n_gpu=n_gpu, embedding=True)
            _gguf_cache[key] = llama
        m = _gguf_cache[key]

    out = []
    for t in txts:
        t = t[:8000]
        if hasattr(m, "embed"):
            v = m.embed(t)
            out.append(list(v) if isinstance(v, (list, tuple)) else v.tolist() if hasattr(v, "tolist") else list(v))
        elif hasattr(m, "create_embedding"):
            r = m.create_embedding(input=t)
            out.append(r["data"][0]["embedding"])
        else:
            raise RuntimeError("gguf embed unsupported")
    return out


def embed_texts(
    backend: str,
    txts: List[str],
    ollama_client: BaseLLMClient = None,
    ollama_model: str = "nomic-embed-text",
    st_model: str = "all-MiniLM-L6-v2",
    gguf_model_path: str = "",
    gguf_n_ctx: int = 4096,
    gguf_n_threads: int = 0,
    gguf_n_gpu: int = 0,
) -> List[List[float]]:
    if not txts:
        return []
    if backend == "sentence_transformers":
        return embed_with_sentence_transformers(st_model, txts)
    if backend == "gguf":
        return embed_with_gguf(gguf_model_path, txts, n_ctx=gguf_n_ctx, n_threads=gguf_n_threads, n_gpu=gguf_n_gpu)
    return embed_with_ollama(ollama_client, ollama_model, txts)


def clear_cache():
    with _gguf_lock:
        _cache.clear()
        _gguf_cache.clear()
    # also clear llm_client cache
    try:
        from core.llm_client import clear_gguf_cache

        clear_gguf_cache()
    except:
        pass
