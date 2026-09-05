from __future__ import annotations
import logging
from typing import List,Tuple,Optional
from core.llm_client import BaseLLMClient,LLMError
logger=logging.getLogger(__name__)
def rewrite_standalone(c:BaseLLMClient,m:str,pq:str,pa:str,fq:str,ctx:int|None=None)->str:
 pr=f"Rewrite follow-up as standalone question concisely. If already standalone return unchanged.\n\nPrev Q: {pq}\nPrev A: {pa}\nFollow-up: {fq}\nStandalone:"
 cw=ctx or 4096
 try:
  o=[]
  for p in c.chat_stream(m,[{"role":"user","content":pr}],temperature=0.0,context_window=cw):o.append(p)
  r="".join(o).strip()
  return r if r else fq
 except Exception as e:
  logger.warning(f"rewrite fail {e}")
  return fq
def summarize_incremental(c:BaseLLMClient,m:str,es:str,oq:str,oa:str,ctx:int|None=None)->str:
 pr=f"Fold exchange into summary 3-6 sentences keep key topics. If trivial keep unchanged.\n\nExisting: {es or '(none)'}\nQ: {oq}\nA: {oa}"
 cw=ctx or 4096
 try:
  o=[]
  for p in c.chat_stream(m,[{"role":"user","content":pr}],temperature=0.2,context_window=cw):o.append(p)
  return "".join(o).strip()
 except Exception as e:
  logger.warning(f"summary fail {e}")
  return es
class ConversationState:
 def __init__(self,mx:int=3):self.recent_turns:List[Tuple[str,str]]=[];self.rolling_summary="";self.max_recent=mx
 def add_turn(self,q:str,a:str,cl:BaseLLMClient,mdl:str,ctx:int|None=None):
  self.recent_turns.append((q,a))
  while len(self.recent_turns)>self.max_recent:
   old=self.recent_turns.pop(0)
   self.rolling_summary=summarize_incremental(cl,mdl,self.rolling_summary,old[0],old[1],ctx)
 def build_prompt_context(self)->str:
  p=[]
  if self.rolling_summary:p.append(f"[Earlier]\n{self.rolling_summary}")
  for i,(q,a) in enumerate(self.recent_turns):
   lb="Most recent" if i==len(self.recent_turns)-1 else f"Recent {i+1}"
   p.append(f"[{lb}]\nQ: {q}\nA: {a}")
  return "\n\n".join(p)
 def last_exchange(self)->Optional[Tuple[str,str]]:return self.recent_turns[-1] if self.recent_turns else None
 def clear(self):self.recent_turns=[];self.rolling_summary=""
 def get_standalone_query(self,cl:BaseLLMClient,mdl:str,fq:str,ctx:int|None=None)->str:
  last=self.last_exchange()
  if last is None:return fq
  return rewrite_standalone(cl,mdl,last[0],last[1],fq,ctx)
