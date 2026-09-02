"""
Best-effort token counting. Uses tiktoken if available (good approximation for
most modern tokenizers), otherwise falls back to a character-based heuristic.
The encoder is initialized lazily on first use so an offline machine with a
cold tiktoken cache can never block app startup.
Exact token counts differ per model family, but this is accurate enough to
budget context safely with a small safety margin baked into the caller.
"""
from __future__ import annotations

_ENC = None
_ENC_TRIED = False


def _get_encoder():
    global _ENC, _ENC_TRIED
    if not _ENC_TRIED:
        _ENC_TRIED = True
        try:
            import tiktoken
            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC = None
    return _ENC


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # Heuristic fallback: ~4 chars per token for English-like text.
    return max(1, int(len(text) / 4))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    enc = _get_encoder()
    if enc is not None:
        try:
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return enc.decode(tokens[:max_tokens])
        except Exception:
            pass
    # Heuristic fallback
    approx_chars = max_tokens * 4
    return text[:approx_chars]
