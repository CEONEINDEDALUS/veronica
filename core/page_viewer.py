from __future__ import annotations
import os
from typing import Optional
def render_page_image(pdf:str,page:int,zoom:float=1.5)->bytes:
 import fitz
 doc=fitz.open(pdf)
 try:
  if page<1 or page>len(doc):raise ValueError(f"page {page} oob {len(doc)}")
  pg=doc[page-1]
  mat=fitz.Matrix(zoom,zoom)
  pix=pg.get_pixmap(matrix=mat)
  return pix.tobytes("png")
 finally:doc.close()
def extract_page_text(pdf:str,page:int)->str:
 import fitz
 doc=fitz.open(pdf)
 try:
  if page<1 or page>len(doc):raise ValueError("oob")
  return doc[page-1].get_text("text")
 finally:doc.close()
def find_quote_in_text(text:str,quote:str)->tuple[int,int]:
 from core.verifier import normalize
 nt,nq=normalize(text),normalize(quote)
 idx=nt.find(nq)
 if idx==-1:
  from rapidfuzz import fuzz
  if fuzz.partial_ratio(nq,nt)<90:return -1,-1
  idx=nt.find(nq[:min(len(nq),40)])
  if idx==-1:return -1,-1
 return idx,idx+len(nq)
def build_page_text_lookup(recs:list)->dict:
 d={}
 for r in recs:
  k=r.page if r.page is not None else r.chapter
  if k is not None:d[(r.book_id,k)]=r.text
 return d
def resolve_book_filepath(kb:str,bid:str,store)->Optional[str]:
 col=store.get_collection(kb)
 try:
  data=col.get(where={"book_id":bid},include=["metadatas"],limit=1)
  metas=data.get("metadatas",[])
  if metas:return metas[0].get("source_path") or metas[0].get("source")
 except:pass
 return None
