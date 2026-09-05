from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
@dataclass(slots=True)
class PageRecord:
 book_id:str
 title:str
 author:Optional[str]
 source_format:str
 page:Optional[int]
 chapter:Optional[str]
 char_start:int
 char_end:int
 text:str
@dataclass(slots=True)
class Chunk:
 chunk_id:str
 book_id:str
 title:str
 page:Optional[int]
 chapter:Optional[str]
 text:str
 source:str=""
 chunk_index:int=0
