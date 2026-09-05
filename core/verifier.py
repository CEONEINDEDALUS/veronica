from __future__ import annotations
import re,logging
from rapidfuzz import fuzz
from core.schema import Answer,Citation
logger=logging.getLogger(__name__)
THR=92
def normalize(s:str)->str:return re.sub(r"\s+"," ",s).strip().lower()
def verify_citation(c:Citation,lookup:dict)->bool:
 k=c.page if c.page is not None else c.chapter
 key=(c.book_id,k)
 t=lookup.get(key)
 if not t:return False
 q,n=normalize(c.quote),normalize(t)
 if not q:return False
 if q in n:return True
 return fuzz.partial_ratio(q,n)>=THR
def verify_answer(a:Answer,lookup:dict)->tuple[Answer,list[Citation]]:
 v=[];d=[]
 for cit in a.citations:
  if verify_citation(cit,lookup):v.append(cit)
  else:d.append(cit);logger.warning(f"drop cit {cit.book_id} p={cit.page} c={cit.chapter} q={cit.quote[:80]}")
 a.citations=v
 return a,d
