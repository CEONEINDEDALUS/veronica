from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QDialog,QScrollArea,QPushButton
from core.verifier import normalize
class PageViewerDialog(QDialog):
 def __init__(self,parent:Optional[QWidget]=None):
  super().__init__(parent);self.setWindowTitle("Source");self.resize(680,780);self._build_ui()
 def _build_ui(self):
  r=QVBoxLayout(self);r.setContentsMargins(12,12,12,12);r.setSpacing(10)
  self.title_label=QLabel();self.title_label.setObjectName("pageViewerTitle");r.addWidget(self.title_label)
  self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.content=QLabel();self.content.setAlignment(Qt.AlignmentFlag.AlignCenter);self.content.setTextFormat(Qt.TextFormat.PlainText);self.scroll.setWidget(self.content);r.addWidget(self.scroll,1)
  br=QHBoxLayout();br.addStretch(1);self.close_btn=QPushButton("Close");self.close_btn.clicked.connect(self.close);br.addWidget(self.close_btn);br.addStretch(1);r.addLayout(br)
 def set_pdf_page(self,ttl:str,page:int,png:bytes,quote:Optional[str]=None):
  self.title_label.setText(f"{ttl} p{page}");px=QPixmap();px.loadFromData(png);self.content.setPixmap(px);self.content.setAlignment(Qt.AlignmentFlag.AlignCenter)
 def set_epub_chapter(self,ttl:str,ch:str,text:str,quote:Optional[str]=None):
  self.title_label.setText(f"{ttl} {ch}");self.content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);self.content.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop);self.content.setTextFormat(Qt.TextFormat.PlainText);d=text if text.strip() else "(empty)";self.content.setText(d)
  if quote:self._highlight_quote(text,quote)
 def _highlight_quote(self,full:str,quote:str):
  nf,nq=normalize(full),normalize(quote)
  idx=nf.find(nq)
  if idx==-1:return
  esc=lambda s:s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
  before=esc(full[:idx]);m=esc(full[idx:idx+len(nq)]);after=esc(full[idx+len(nq):])
  h=f'<div style="font-size:12px">{before}<span style="background:#B83A2D;color:#DCC9A9;padding:1px 2px;border-radius:3px">{m}</span>{after}</div>'
  self.content.setTextFormat(Qt.TextFormat.HtmlFormat);self.content.setText(h)
def show_page_viewer(parent:Optional[QWidget],source:str,page_or_chapter,quote:Optional[str]=None,title:str=""):
 import os
 if not os.path.exists(source):return
 ext=os.path.splitext(source)[1].lower()
 dlg=PageViewerDialog(parent)
 try:
  if ext==".pdf":
   import fitz
   pn=int(page_or_chapter);doc=fitz.open(source)
   try:
    if pn<1 or pn>len(doc):pn=1
    pg=doc[pn-1];mat=fitz.Matrix(1.5,1.5);pix=pg.get_pixmap(matrix=mat);png=pix.tobytes("png")
    dlg.set_pdf_page(title or os.path.basename(source),pn,png,quote)
   finally:doc.close()
  elif ext==".epub":
   from ebooklib import epub
   from bs4 import BeautifulSoup
   ch=str(page_or_chapter);book=epub.read_epub(source);txt=""
   for it in book.get_items_of_type(9):
    if it.get_name()==ch:soup=BeautifulSoup(it.get_content(),"html.parser");txt=soup.get_text("\n").strip();break
   dlg.set_epub_chapter(title or os.path.basename(source),ch,txt,quote)
  else:dlg.title_label.setText(f"{title or source} {page_or_chapter}");dlg.content.setText(quote or "")
 except Exception as e:dlg.title_label.setText("Error");dlg.content.setText(f"fail {e}")
 dlg.exec()
