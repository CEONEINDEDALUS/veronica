from __future__ import annotations
from typing import Optional,Literal
from pydantic import BaseModel,Field
class Citation(BaseModel):
 book_id:str=Field(description="id")
 title:str=Field(description="title")
 page:Optional[int]=Field(default=None)
 chapter:Optional[str]=Field(default=None)
 quote:str=Field(description="verbatim")
class Answer(BaseModel):
 answer:str
 citations:list[Citation]=Field(default_factory=list)
 confidence:Literal["high","medium","low","not_found"]=Field(default="medium")
