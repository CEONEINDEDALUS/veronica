"""
Best-effort token counting. Uses tiktoken if available (good approximation for
most modern tokenizers), otherwise falls back to a character-based heuristic.
Exact token counts differ per model family, but this is accurate enough to
budget context safely with a small safety margin baked into the caller.
"""
from __future__ import annotations

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENC = None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENC is not None:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    # Heuristic fallback: ~4 chars per token for English-like text.
    return max(1, int(len(text) / 4))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if _ENC is not None:
        try:
            tokens = _ENC.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return _ENC.decode(tokens[:max_tokens])
        except Exception:
            pass
    # Heuristic fallback
    approx_chars = max_tokens * 4
    return text[:approx_chars]
