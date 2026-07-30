"""
Recursive, boundary-aware text splitter. Tries to split on paragraph, then
line, then sentence, then word boundaries before falling back to hard
character cuts - keeps chunks semantically coherent, which matters a lot
when the reader (a small local model) only gets to see a handful of them.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]


@dataclass
class Chunk:
    text: str
    index: int
    start_char: int


def _split_on(text: str, sep: str) -> List[str]:
    if sep == "":
        return list(text)
    return text.split(sep)


def _recursive_split(text: str, separators: List[str], chunk_size: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    if not separators:
        # Hard cut fallback
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep, rest = separators[0], separators[1:]
    pieces = _split_on(text, sep)
    if len(pieces) == 1:
        return _recursive_split(text, rest, chunk_size)

    results: List[str] = []
    buffer = ""
    joiner = sep
    for piece in pieces:
        candidate = (buffer + joiner + piece) if buffer else piece
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                results.append(buffer)
            if len(piece) > chunk_size:
                results.extend(_recursive_split(piece, rest, chunk_size))
                buffer = ""
            else:
                buffer = piece
    if buffer:
        results.append(buffer)
    return results


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[Chunk]:
    text = text.strip()
    if not text:
        return []

    raw_chunks = _recursive_split(text, _SEPARATORS, chunk_size)

    # Apply overlap by stitching a tail of the previous chunk onto the next one.
    overlapped: List[str] = []
    for i, c in enumerate(raw_chunks):
        if i == 0 or overlap <= 0:
            overlapped.append(c)
        else:
            prev_tail = overlapped[-1][-overlap:] if overlapped else ""
            overlapped.append((prev_tail + " " + c).strip())

    chunks: List[Chunk] = []
    cursor = 0
    for i, c in enumerate(overlapped):
        c = c.strip()
        if not c:
            continue
        chunks.append(Chunk(text=c, index=i, start_char=cursor))
        cursor += max(1, len(c) - overlap)
    return chunks
