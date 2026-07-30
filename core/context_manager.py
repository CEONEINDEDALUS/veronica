"""
This is what makes Veronica usable on small-context local models.

Local models via Ollama often run with modest context windows (many quantized
7B/8B models default to 2k-8k tokens). Naively stuffing top-k retrieved chunks
into the prompt causes silent truncation and broken answers. Instead:

  1. We compute a real token budget = context_window - output_reserve - system_reserve
     - chat_history_tokens.
  2. We greedily fit the highest-similarity chunks into that budget (cheap, fast path).
  3. If there are more *relevant* chunks than fit, and compression is enabled, we
     hierarchically summarize the overflow chunks (map -> reduce, recursively halving
     batches) with the same local LLM until the summarized content fits the remaining
     budget - so nothing highly relevant just gets dropped on the floor.
  4. As an absolute last resort (context window smaller than even one chunk),
     we truncate a single chunk to fit rather than failing.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Callable, Optional
from core.tokenizer import count_tokens, truncate_to_tokens


@dataclass
class Budget:
    context_window: int
    reserved_output: int
    reserved_system: int
    chat_history_tokens: int

    @property
    def available_for_context(self) -> int:
        return max(256, self.context_window - self.reserved_output - self.reserved_system
                   - self.chat_history_tokens)


def _formatted_chunk_text(chunk: Dict) -> str:
    src = chunk.get("metadata", {}).get("source", "unknown")
    return f"[Source: {src}]\n{chunk['text']}"


def fit_chunks_greedy(chunks: List[Dict], budget_tokens: int) -> (List[Dict], List[Dict]):
    """Sorted by similarity desc, greedily pack chunks under the budget.
    Counts each chunk's *formatted* token cost (including its source-label
    wrapper and the join separator) so the resulting context block never
    exceeds the real budget. Returns (fitted, overflow)."""
    ordered = sorted(chunks, key=lambda c: c.get("similarity", 0), reverse=True)
    separator_tokens = count_tokens("\n\n---\n\n")
    fitted, overflow = [], []
    used = 0
    for c in ordered:
        t = count_tokens(_formatted_chunk_text(c))
        cost = t + (separator_tokens if fitted else 0)
        if used + cost <= budget_tokens:
            fitted.append(c)
            used += cost
        else:
            overflow.append(c)
    return fitted, overflow


def hierarchical_summarize(chunks: List[Dict], target_tokens: int,
                            summarize_fn: Callable[[str], str],
                            batch_token_size: int = 1200) -> str:
    """Map-reduce style compression: batch overflow chunks into groups that fit
    the model's own context, summarize each batch, then recursively summarize
    the summaries until the combined result fits target_tokens (or we run out
    of rounds)."""
    texts = [f"[Source: {c['metadata'].get('source', 'unknown')}]\n{c['text']}" for c in chunks]

    def make_batches(items: List[str], max_tokens: int) -> List[str]:
        batches, buf, used = [], [], 0
        for t in items:
            tt = count_tokens(t)
            if used + tt > max_tokens and buf:
                batches.append("\n\n---\n\n".join(buf))
                buf, used = [], 0
            buf.append(t)
            used += tt
        if buf:
            batches.append("\n\n---\n\n".join(buf))
        return batches

    current = texts
    for _round in range(4):  # hard cap to avoid runaway recursion on pathological inputs
        combined_tokens = count_tokens("\n\n".join(current))
        if combined_tokens <= target_tokens or len(current) == 1:
            break
        batches = make_batches(current, batch_token_size)
        summarized = []
        for b in batches:
            prompt = (
                "Summarize the key facts, figures, and any information that could answer a "
                "user question, from the following document excerpt(s). Be concise but keep "
                "concrete details (names, numbers, dates). Do not add commentary.\n\n" + b
            )
            summarized.append(summarize_fn(prompt))
        current = summarized

    final_text = "\n\n".join(current)
    if count_tokens(final_text) > target_tokens:
        final_text = truncate_to_tokens(final_text, target_tokens)
    return final_text


def build_context_block(chunks: List[Dict]) -> str:
    parts = []
    for c in chunks:
        src = c.get("metadata", {}).get("source", "unknown")
        parts.append(f"[Source: {src}]\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def assemble_context(all_candidates: List[Dict], budget: Budget,
                      enable_compression: bool, compression_ratio: float,
                      summarize_fn: Optional[Callable[[str], str]]) -> Dict:
    """Returns {"context_text": str, "used_compression": bool, "chunks_used": int,
    "chunks_overflow": int}"""
    available = budget.available_for_context
    fitted, overflow = fit_chunks_greedy(all_candidates, available)

    used_compression = False
    context_text = build_context_block(fitted)
    remaining_budget = available - count_tokens(context_text)

    if overflow and enable_compression and summarize_fn is not None and remaining_budget > 150:
        target = int(remaining_budget * compression_ratio) if compression_ratio > 0 else remaining_budget
        target = max(target, 150)
        summary = hierarchical_summarize(overflow, target, summarize_fn)
        if summary.strip():
            context_text = (context_text + "\n\n---\n\n[Condensed summary of additional relevant "
                             "material]\n" + summary) if context_text else summary
            used_compression = True

    # Absolute last resort: nothing fit at all (context window smaller than one chunk)
    if not fitted and not used_compression and all_candidates:
        best = max(all_candidates, key=lambda c: c.get("similarity", 0))
        context_text = truncate_to_tokens(best["text"], available)

    return {
        "context_text": context_text,
        "used_compression": used_compression,
        "chunks_used": len(fitted),
        "chunks_overflow": len(overflow),
    }
