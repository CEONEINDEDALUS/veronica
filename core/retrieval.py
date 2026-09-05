from __future__ import annotations
import logging
from typing import List,Dict,Optional,Tuple
from core.vector_store import VectorStore
logger=logging.getLogger(__name__)
DEFAULT_MAX_DISTANCE=0.45
_R=None
def _get_reranker():
 global _R
 if _R is None:
  try:
   from sentence_transformers import CrossEncoder
   _R=CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2",device="cpu",max_length=256)
  except Exception as e:
   logger.warning(f"reranker load fail {e}")
   _R=False
 return _R if _R else None
def rerank(q:str,hits:List[Tuple[str,Dict,float]],top_n:int=5)->List[Tuple[str,Dict,float]]:
 if not hits:return []
 try:
  rr=_get_reranker()
  if not rr:return hits[:top_n]
  pairs=[(q,t) for t,_,_ in hits]
  scores=rr.predict(pairs,show_progress_bar=False,batch_size=16)
  ranked=sorted(zip(hits,scores),key=lambda x:-x[1])
  return [h for h,_ in ranked[:top_n]]
 except Exception as e:
  logger.warning(f"rerank fail {e}")
  return hits[:top_n]
def retrieve(store:VectorStore,kb:str,qemb:List[float],top_k:int=20,max_distance:float=DEFAULT_MAX_DISTANCE,book_id:Optional[str]=None,query_text:Optional[str]=None,rerank_top_n:Optional[int]=None)->List[Tuple[str,Dict,float]]:
 w={"book_id":book_id} if book_id else None
 hits=store.query(kb,qemb,top_k=top_k,where=w)
 kept=[h for h in hits if h.get("distance",0.0)<=max_distance]
 if not kept:return []
 kept.sort(key=lambda h:h.get("distance",1.0))
 if query_text and rerank_top_n and rerank_top_n>0 and len(kept)>1:
  kept=rerank(query_text,[(h["text"],h["metadata"],h["distance"]) for h in kept],top_n=rerank_top_n)
  return kept
 return [(h["text"],h["metadata"],h["distance"]) for h in kept]
