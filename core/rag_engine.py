"""
Orchestrates ingestion (load -> chunk -> embed -> store) and query
(embed query -> retrieve -> budget-fit/compress -> generate).
Supports both Ollama and local GGUF (llama.cpp) backends.
"""
from __future__ import annotations
from typing import List, Dict, Generator, Callable, Optional
import os

from core.config import Config
from core.document_loader import load_file
from core.chunker import chunk_text
from core.embeddings import embed_texts
from core.vector_store import VectorStore
from core.llm_client import get_client, get_client_for_config, BaseLLMClient
from core.context_manager import Budget, assemble_context
from core.tokenizer import count_tokens


class RagEngine:
    def __init__(self, config: Config):
        self.config = config
        self.store = VectorStore()

    # ---------- backend helpers ----------
    def get_llm_client(self) -> BaseLLMClient:
        c = self.config
        if c.llm_backend == "gguf":
            return get_client(backend="gguf", gguf_model_path=c.gguf_model_path, n_ctx=c.gguf_n_ctx, n_threads=c.gguf_n_threads, n_gpu_layers=c.gguf_n_gpu_layers, embedding_path=c.gguf_embedding_model_path or c.gguf_model_path)
        return get_client(ollama_host=c.ollama_host)

    def get_embedding_client(self) -> Optional[BaseLLMClient]:
        c = self.config
        if c.embedding_backend == "gguf":
            p = c.gguf_embedding_model_path or c.gguf_model_path
            if p:
                return get_client(backend="gguf", gguf_model_path=p, n_ctx=c.gguf_n_ctx, n_threads=c.gguf_n_threads, n_gpu_layers=c.gguf_n_gpu_layers, embedding_path=p)
            return get_client(backend="gguf", gguf_model_path=c.gguf_model_path, n_ctx=c.gguf_n_ctx, n_threads=c.gguf_n_threads, n_gpu_layers=c.gguf_n_gpu_layers)
        if c.embedding_backend == "ollama":
            return get_client(ollama_host=c.ollama_host)
        return None

    # ---------- ingestion ----------
    def ingest_files(self, file_paths: List[str], kb_name: str,
                      progress_cb: Optional[Callable[[str, int, int], None]] = None
                      ) -> Dict[str, int]:
        """Returns {"files": n, "chunks": n, "errors": [...]}"""
        c = self.config
        embed_client = self.get_embedding_client()
        total = len(file_paths)
        total_chunks = 0
        errors = []

        for i, path in enumerate(file_paths, start=1):
            fname = os.path.basename(path)
            if progress_cb:
                progress_cb(f"Reading {fname}...", i, total)
            try:
                text = load_file(path)
                if not text.strip():
                    errors.append(f"{fname}: no extractable text")
                    continue
                chunks = chunk_text(text, chunk_size=c.chunk_size, overlap=c.chunk_overlap)
                if not chunks:
                    errors.append(f"{fname}: produced no chunks")
                    continue

                if progress_cb:
                    progress_cb(f"Embedding {fname} ({len(chunks)} chunks)...", i, total)

                texts = [ch.text for ch in chunks]
                # Adaptive batch: larger batches = fewer round-trips = faster ingestion
                # GGUF local is CPU-bound, Ollama benefits from bigger batches
                if c.embedding_backend == "gguf":
                    batch_size = 32 if c.gguf_n_ctx >= 16384 else 16
                    # If using GPU offload, can go larger
                    if c.gguf_n_gpu_layers > 0:
                        batch_size = 64
                else:
                    batch_size = 64
                all_vectors: List[List[float]] = []
                for b in range(0, len(texts), batch_size):
                    batch = texts[b:b + batch_size]
                    vectors = embed_texts(
                        c.embedding_backend, batch,
                        ollama_client=embed_client,
                        ollama_model=c.ollama_embedding_model,
                        st_model=c.st_embedding_model,
                        gguf_model_path=c.gguf_embedding_model_path or c.gguf_model_path,
                        gguf_n_ctx=c.gguf_n_ctx,
                        gguf_n_threads=c.gguf_n_threads,
                        gguf_n_gpu=c.gguf_n_gpu_layers,
                    )
                    all_vectors.extend(vectors)

                metadatas = [{"source": fname, "chunk_index": ch.index} for ch in chunks]
                # embedding identity for mismatch detection
                if c.embedding_backend == "gguf":
                    emb_id = f"gguf:{os.path.basename(c.gguf_embedding_model_path or c.gguf_model_path)}"
                elif c.embedding_backend == "ollama":
                    emb_id = f"ollama:{c.ollama_embedding_model}"
                else:
                    emb_id = f"st:{c.st_embedding_model}"
                self.store.add_chunks(kb_name, texts, all_vectors, metadatas, embedding_id=emb_id)
                total_chunks += len(chunks)
            except Exception as e:
                errors.append(f"{fname}: {e}")

        if progress_cb:
            progress_cb("Done.", total, total)
        return {"files": total, "chunks": total_chunks, "errors": errors}

    # ---------- query ----------
    def _embed_query(self, query: str) -> List[float]:
        c = self.config
        client = self.get_embedding_client()
        vecs = embed_texts(c.embedding_backend, [query], ollama_client=client,
                            ollama_model=c.ollama_embedding_model, st_model=c.st_embedding_model,
                            gguf_model_path=c.gguf_embedding_model_path or c.gguf_model_path,
                            gguf_n_ctx=c.gguf_n_ctx, gguf_n_threads=c.gguf_n_threads, gguf_n_gpu=c.gguf_n_gpu_layers)
        return vecs[0] if vecs else []

    def _resolve_context_window(self, llm_client: BaseLLMClient, model: str) -> int:
        c = self.config
        if not c.auto_detect_context:
            if c.llm_backend == "gguf":
                return c.gguf_n_ctx
            return c.manual_context_window
        try:
            return llm_client.get_context_window(model)
        except Exception:
            if c.llm_backend == "gguf":
                return c.gguf_n_ctx
            return c.manual_context_window

    def _effective_model(self, cfg_model: str) -> str:
        c = self.config
        if c.llm_backend == "gguf":
            return c.gguf_model_path or cfg_model
        return cfg_model or c.chat_model

    def build_messages(self, question: str, kb_name: str, chat_history: List[Dict],
                        model: str, llm_client: BaseLLMClient) -> Dict:
        """Retrieves, budget-fits/compresses context, and returns the final
        messages list plus retrieval diagnostics."""
        c = self.config
        model = self._effective_model(model)

        query_embedding = self._embed_query(question)
        candidates = []
        if query_embedding:
            n_candidates = max(c.top_k * c.candidate_multiplier, c.top_k)
            if c.embedding_backend == "gguf":
                emb_id = f"gguf:{os.path.basename(c.gguf_embedding_model_path or c.gguf_model_path)}"
            elif c.embedding_backend == "ollama":
                emb_id = f"ollama:{c.ollama_embedding_model}"
            else:
                emb_id = f"st:{c.st_embedding_model}"
            try:
                candidates = self.store.query(kb_name, query_embedding, n_candidates, embedding_id=emb_id)
            except:
                candidates = self.store.query(kb_name, query_embedding, n_candidates)
            if c.similarity_floor > 0:
                candidates = [x for x in candidates if x["similarity"] >= c.similarity_floor]
            candidates = candidates[: max(n_candidates, c.top_k)]

        context_window = self._resolve_context_window(llm_client, model)

        # token cost of chat history we plan to include
        recent_history = chat_history[-(c.max_chat_history_turns * 2):] if chat_history else []
        history_tokens = sum(count_tokens(m["content"]) for m in recent_history)

        budget = Budget(
            context_window=context_window,
            reserved_output=c.reserved_output_tokens,
            reserved_system=c.reserved_system_tokens + count_tokens(c.system_prompt),
            chat_history_tokens=history_tokens,
        )

        def summarize_fn(prompt: str) -> str:
            # Small, deterministic-ish summarization call using the same model.
            out = []
            for piece in llm_client.chat_stream(
                model, [{"role": "user", "content": prompt}], temperature=0.2,
                context_window=context_window,
            ):
                out.append(piece)
            return "".join(out).strip()

        assembly = assemble_context(
            candidates, budget,
            enable_compression=c.enable_context_compression,
            compression_ratio=c.compression_target_ratio,
            summarize_fn=summarize_fn if candidates else None,
        )

        user_content = (
            f"Context from private documents:\n{assembly['context_text']}\n\n"
            f"Question: {question}"
        ) if assembly["context_text"] else question

        messages = [{"role": "system", "content": c.system_prompt}]
        messages.extend(recent_history)
        messages.append({"role": "user", "content": user_content})

        return {
            "messages": messages,
            "context_window": context_window,
            "chunks_used": assembly["chunks_used"],
            "chunks_overflow": assembly["chunks_overflow"],
            "used_compression": assembly["used_compression"],
            "candidates_found": len(candidates),
            "sources": sorted({c_["metadata"].get("source", "unknown") for c_ in candidates}),
        }

    def stream_answer(self, question: str, kb_name: str, chat_history: List[Dict], model: str
                       ) -> Generator[Dict, None, None]:
        """Yields dicts: {"type": "meta", ...} once, then {"type": "token", "text": ...}
        repeatedly, then {"type": "done"}."""
        llm_client = self.get_llm_client()
        model = self._effective_model(model)
        built = self.build_messages(question, kb_name, chat_history, model, llm_client)
        yield {"type": "meta", **{k: v for k, v in built.items() if k != "messages"}}

        try:
            for piece in llm_client.chat_stream(model, built["messages"], temperature=self.config.temperature,
                                                 context_window=built["context_window"]):
                yield {"type": "token", "text": piece}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
            return
        yield {"type": "done"}
