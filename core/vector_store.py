"""
Thin wrapper around ChromaDB for persistent, per-knowledge-base vector storage.
Embeddings are computed by us (core.embeddings) so we can swap backends freely -
Chroma is used purely as a fast local vector index + metadata store.

Every chunk records the embedding identity ("backend:model") it was computed
with, so switching embedding models in Settings raises a clear error instead of
silently mixing incompatible vector spaces.
"""
from __future__ import annotations
import uuid
from typing import List, Dict, Optional
import chromadb
from core.config import PERSIST_DIR


class EmbeddingMismatchError(Exception):
    pass


class VectorStore:
    def __init__(self, persist_dir: str = PERSIST_DIR):
        self.client = chromadb.PersistentClient(path=persist_dir)

    def get_collection(self, name: str):
        return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def _check_embedding(self, collection, embedding_id: Optional[str]):
        if not embedding_id:
            return
        data = collection.get(include=["metadatas"], limit=1)
        metas = data.get("metadatas") or []
        if not metas:
            return
        stored = (metas[0] or {}).get("embedding")
        if stored and stored != embedding_id:
            raise EmbeddingMismatchError(
                f"Knowledge base '{collection.name}' was embedded with '{stored}' but "
                f"the current embedding setting is '{embedding_id}'. Re-ingest its "
                f"documents (old chunks are replaced) or switch back in Settings."
            )

    def list_knowledge_bases(self) -> List[str]:
        return sorted(c.name for c in self.client.list_collections())

    def delete_knowledge_base(self, name: str):
        try:
            self.client.delete_collection(name)
        except Exception:
            pass

    def add_chunks(self, kb_name: str, texts: List[str], embeddings: List[List[float]],
                    metadatas: List[Dict], embedding_id: Optional[str] = None):
        if not texts:
            return
        collection = self.get_collection(kb_name)
        self._check_embedding(collection, embedding_id)
        sources = {m.get("source") for m in metadatas if m.get("source")}
        for src in sources:
            try:
                collection.delete(where={"source": src})
            except Exception:
                pass
        stamped = []
        for m in metadatas:
            meta = dict(m)
            if embedding_id:
                meta["embedding"] = embedding_id
            stamped.append(meta)
        ids = [str(uuid.uuid4()) for _ in texts]
        collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=stamped)

    def remove_document(self, kb_name: str, source: str) -> bool:
        try:
            collection = self.get_collection(kb_name)
            before = collection.count()
            collection.delete(where={"source": source})
            return collection.count() < before
        except Exception:
            return False

    def query(self, kb_name: str, query_embedding: List[float], top_k: int,
              embedding_id: Optional[str] = None) -> List[Dict]:
        collection = self.get_collection(kb_name)
        self._check_embedding(collection, embedding_id)
        count = collection.count()
        if count == 0:
            return []
        n = min(top_k, count)
        result = collection.query(query_embeddings=[query_embedding], n_results=n,
                                   include=["documents", "metadatas", "distances"])
        out = []
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            similarity = 1.0 - dist  # cosine distance -> similarity
            out.append({"text": doc, "metadata": meta or {}, "similarity": similarity})
        return out

    def document_summary(self, kb_name: str) -> Dict[str, int]:
        """Returns {source_filename: chunk_count} for a knowledge base."""
        collection = self.get_collection(kb_name)
        count = collection.count()
        if count == 0:
            return {}
        data = collection.get(include=["metadatas"], limit=count)
        summary: Dict[str, int] = {}
        for meta in data.get("metadatas", []):
            src = (meta or {}).get("source", "unknown")
            summary[src] = summary.get(src, 0) + 1
        return summary
