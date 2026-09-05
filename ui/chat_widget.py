from __future__ import annotations
from typing import List,Dict,Optional
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QFrame,QScrollArea,QTextEdit,QPushButton,QComboBox,QSizePolicy,QSpacerItem,QFileDialog,QMessageBox
from PyQt6.QtGui import QKeyEvent
from core.config import config
from core.rag_engine import RagEngine
from ui.workers import QueryWorker,ModelListWorker
import os
class ChatInput(QTextEdit):
 def __init__(self,cb):
  super().__init__();self.on_send=cb;self.setPlaceholderText("Ask... (Enter send Shift+Enter newline)");self.setFixedHeight(64)
 def keyPressEvent(self,e:QKeyEvent):
  if e.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not (e.modifiers()&Qt.KeyboardModifier.ShiftModifier):self.on_send();return
  super().keyPressEvent(e)
class MessageBubble(QFrame):
 def __init__(self,role:str,text:str=""):
  super().__init__();self.role=role;self.setObjectName("userBubble" if role=="user" else "assistantBubble")
  l=QVBoxLayout(self);l.setContentsMargins(14,10,14,10);l.setSpacing(4)
  rl=QLabel("You" if role=="user" else "Veronica");rl.setObjectName("bubbleRole");l.addWidget(rl)
  self.text_label=QLabel(text);self.text_label.setObjectName("bubbleText");self.text_label.setWordWrap(True);self.text_label.setTextFormat(Qt.TextFormat.MarkdownText);self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);l.addWidget(self.text_label)
  self.meta_label=QLabel("");self.meta_label.setObjectName("bubbleMeta");self.meta_label.setVisible(False);self.meta_label.setWordWrap(True);l.addWidget(self.meta_label)
 def set_text(self,t:str):self.text_label.setText(t)
 def set_meta(self,m:str):self.meta_label.setText(m);self.meta_label.setVisible(bool(m))
def _repolish(w:QWidget):w.style().unpolish(w);w.style().polish(w)
class ChatPage(QWidget):
 def __init__(self,engine:RagEngine):
  super().__init__();self.engine=engine;self.chat_history:List[Dict]=[];self.current_worker:Optional[QueryWorker]=None;self.current_bubble:Optional[MessageBubble]=None;self._streamed_text="";self._generating=False;self._autoscroll=True;self._bubbles:List[MessageBubble]=[];self._model_gen=0;self._build_ui();self.refresh_models();self.refresh_kb_list()
 def _build_ui(self):
  root=QVBoxLayout(self);root.setContentsMargins(20,16,20,16);root.setSpacing(10)
  header=QHBoxLayout()
  tb=QVBoxLayout();t=QLabel("Chat");t.setObjectName("pageTitle");s=QLabel("Ask your docs");s.setObjectName("pageSubtitle");tb.addWidget(t);tb.addWidget(s);header.addLayout(tb);header.addItem(QSpacerItem(20,20,QSizePolicy.Policy.Expanding))
  kl=QLabel("KB");kl.setObjectName("fieldLabel");header.addWidget(kl)
  self.kb_combo=QComboBox();self.kb_combo.setMinimumWidth(150);header.addWidget(self.kb_combo)
  ml=QLabel("Model");ml.setObjectName("fieldLabel");header.addWidget(ml)
  self.model_combo=QComboBox();self.model_combo.setMinimumWidth(180);header.addWidget(self.model_combo)
  self.gguf_btn=QPushButton("📁");self.gguf_btn.setObjectName("iconButton");self.gguf_btn.setFixedWidth(34);self.gguf_btn.setToolTip("Pick GGUF file (validates header, switches to GGUF backend if needed)");self.gguf_btn.clicked.connect(self._pick_gguf);header.addWidget(self.gguf_btn)
  rb=QPushButton("⟳");rb.setObjectName("iconButton");rb.setFixedWidth(34);rb.clicked.connect(self.refresh_models);header.addWidget(rb)
  root.addLayout(header)
  self.status_pill=QLabel("");self.status_pill.setObjectName("statusPill");self.status_pill.setVisible(False);root.addWidget(self.status_pill)
  self.scroll=QScrollArea();self.scroll.setWidgetResizable(True)
  self.messages_container=QWidget();self.messages_container.setObjectName("messagesContainer")
  self.messages_layout=QVBoxLayout(self.messages_container);self.messages_layout.setContentsMargins(4,4,6,4);self.messages_layout.setSpacing(12)
  self.empty_state=QLabel("Start conversation\nAsk anything about your documents");self.empty_state.setObjectName("emptyState");self.empty_state.setAlignment(Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop);self.empty_state.setWordWrap(True);self.messages_layout.addWidget(self.empty_state);self.messages_layout.addStretch(1)
  self.scroll.setWidget(self.messages_container);root.addWidget(self.scroll,1)
  self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_moved)
  self._flush_timer=QTimer(self);self._flush_timer.setInterval(80);self._flush_timer.timeout.connect(self._flush_stream)
  ir=QHBoxLayout();ir.setSpacing(10)
  self.input_box=ChatInput(self.send_message);ir.addWidget(self.input_box,1)
  bc=QVBoxLayout();bc.setSpacing(6)
  self.send_btn=QPushButton("Send");self.send_btn.setObjectName("primaryButton");self.send_btn.setMinimumWidth(90);self.send_btn.clicked.connect(self.send_message)
  self.clear_btn=QPushButton("Clear");self.clear_btn.setEnabled(False);self.clear_btn.clicked.connect(self.clear_chat)
  bc.addWidget(self.send_btn);bc.addWidget(self.clear_btn);ir.addLayout(bc)
  root.addLayout(ir)
 def _pick_gguf(self):
  # Allow picking even when backend=ollama - will offer to switch
  start = ""
  if config.gguf_model_path:
   d = os.path.dirname(config.gguf_model_path)
   if os.path.isdir(d):
    start = d
  f,_=QFileDialog.getOpenFileName(self,"Pick GGUF model", start, "GGUF Files (*.gguf);;All Files (*)")
  if not f:
   return
   # Validate header before accepting (including SSTI check)
   try:
    from core.gguf_validator import validate_gguf_file
    validate_gguf_file(f)
   except Exception as e:
    msg = str(e)
    is_ssti = "SSTI" in msg or "chat_template" in msg
    if is_ssti:
        # reuse helper from settings to avoid duplication
        try:
            from ui.settings_widget import _prompt_trust_for_ssti
            if _prompt_trust_for_ssti(self, f, msg):
                # re-validate after trust
                from core.gguf_validator import validate_gguf_file as _vf
                _vf(f)
            else:
                return
        except Exception as e2:
            # fallback to inline dialog if helper fails
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("GGUF validation – potentially unsafe template")
            box.setText(f"Selected file failed safety check:\n{e}")
            box.setInformativeText(
                "This GGUF's chat_template could execute code on vulnerable\n"
                "llama-cpp-python (<0.2.72). Only load it if you trust the source.\n\n"
                "• Trust Once – load for this session\n"
                "• Trust Always – remember this template (stored in config)\n"
                "• Cancel – block the file"
            )
            btn_once = box.addButton("Trust Once", QMessageBox.ButtonRole.AcceptRole)
            btn_always = box.addButton("Trust Always", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(btn_cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == btn_once:
                try:
                    from core.gguf_validator import trust_template_for_session, get_chat_template, validate_gguf_file as _vf2
                    tmpl = get_chat_template(f)
                    trust_template_for_session(tmpl, f)
                    _vf2(f)
                except Exception as e3:
                    QMessageBox.warning(self, "GGUF validation", f"Still failed even after trusting:\n{e3}")
                    return
            elif clicked == btn_always:
                try:
                    import hashlib
                    from core.gguf_validator import trust_template_for_session, get_chat_template, get_chat_template_hash, validate_gguf_file as _vf2
                    from core.config import config as _cfg
                    tmpl = get_chat_template(f)
                    h = get_chat_template_hash(f)
                    if not h and tmpl:
                        h = hashlib.sha256(tmpl.encode("utf-8", errors="replace")).hexdigest()
                    if tmpl:
                        trust_template_for_session(tmpl, f)
                    if h:
                        _cfg.trust_gguf_template(h)
                        _cfg.save()
                    _vf2(f)
                except Exception as e3:
                    QMessageBox.warning(self, "GGUF validation", f"Still failed even after trusting:\n{e3}")
                    return
            else:
                return
    else:
        QMessageBox.warning(self, "GGUF validation", f"Selected file failed validation and was not loaded:\n{e}")
        return
  # Offer to switch backend if currently ollama
  if config.llm_backend != "gguf":
   ret = QMessageBox.question(self, "Switch backend?", "Switch LLM backend to GGUF and use selected file?\n(You can change this in Settings)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
   if ret == QMessageBox.StandardButton.Yes:
    config.llm_backend = "gguf"
   else:
    # still set path but keep backend ollama - user may intend to use for embeddings
    pass
  config.gguf_model_path = f
  # Also set chat_model to full path for GGUF mode
  config.chat_model = f
  config.save()
  self.refresh_models()
  self._show_status(f"Picked {os.path.basename(f)}", error=False)
 def refresh_kb_list(self):
  cur=self.kb_combo.currentText()
  self.kb_combo.blockSignals(True);self.kb_combo.clear()
  kbs=self.engine.store.list_knowledge_bases() or [config.active_kb]
  self.kb_combo.addItems(kbs)
  if cur in kbs:self.kb_combo.setCurrentText(cur)
  elif config.active_kb in kbs:self.kb_combo.setCurrentText(config.active_kb)
  self.kb_combo.blockSignals(False)
 def refresh_models(self):
  # Always show GGUF button (user may want to pick even when on ollama)
  self.gguf_btn.setVisible(True)
  # Tooltip update
  if config.llm_backend=="gguf":
   self.gguf_btn.setToolTip("Pick GGUF file")
  else:
   self.gguf_btn.setToolTip("Pick GGUF file (will offer to switch backend to GGUF)")
  self._model_gen+=1;g=self._model_gen
  prev=getattr(self,"_model_worker",None)
  if prev and prev.isRunning():
   self._retired_workers=[w for w in getattr(self,"_retired_workers",[]) if w.isRunning()];self._retired_workers.append(prev)
  self.model_combo.clear();self.model_combo.addItem("Loading...")
  w=ModelListWorker(self.engine);self._model_worker=w
  w.finished_ok.connect(lambda m,gen=g:self._on_models_loaded(gen,m))
  w.failed.connect(lambda e,gen=g:self._on_models_failed(gen,e))
  w.start()
 def _on_models_loaded(self,gen:int,models:List[str]):
  if gen!=self._model_gen:return
  self.model_combo.clear()
  if not models:
   if config.llm_backend=="gguf":
    if not config.gguf_model_path:self.model_combo.addItem("No GGUF set (Settings or 📁)")
    else:
     # Ensure the single file is shown even if list empty due to validation filtering
     # If validation filtered it, show basename anyway but mark
     bn = os.path.basename(config.gguf_model_path)
     # Check if file still valid
     try:
      from core.gguf_validator import validate_gguf_file
      validate_gguf_file(config.gguf_model_path)
      self.model_combo.addItem(bn)
     except Exception as e:
      self.model_combo.addItem(f"⚠ invalid GGUF: {bn}")
    if config.gguf_model_path:
     # Try to set current text to basename without validation filter
     bn = os.path.basename(config.gguf_model_path)
     # If combo contains bn, select it
     for i in range(self.model_combo.count()):
      if self.model_combo.itemText(i)==bn:
       self.model_combo.setCurrentIndex(i);break
   else:self.model_combo.addItem("No models")
   return
  self.model_combo.addItems(models)
  cur=config.chat_model
  if cur in models:self.model_combo.setCurrentText(cur)
  elif config.llm_backend=="gguf" and config.gguf_model_path:
   bn=os.path.basename(config.gguf_model_path)
   if bn in models:self.model_combo.setCurrentText(bn)
  elif cur and os.path.basename(cur) in models:self.model_combo.setCurrentText(os.path.basename(cur))
 def _on_models_failed(self,gen:int,err:str):
  if gen!=self._model_gen:return
  self.model_combo.clear();self.model_combo.addItem("⚠ offline")
  if config.llm_backend=="gguf":self._show_status(f"GGUF load fail: {err}",error=True)
  else:self._show_status(f"Ollama unreachable {config.ollama_host}",error=True)
 def _add_bubble(self,role:str,text:str="")->MessageBubble:
  self.empty_state.setVisible(False)
  b=MessageBubble(role,text)
  row=QHBoxLayout();row.setContentsMargins(0,0,0,0)
  if role=="user":row.addStretch(1);row.addWidget(b,0)
  else:row.addWidget(b,0);row.addStretch(1)
  wrap=QWidget();wrap.setLayout(row);self._apply_bubble_width(b);self._bubbles.append(b)
  self.messages_layout.insertWidget(self.messages_layout.count()-1,wrap);self._scroll_to_bottom(force=True)
  return b
 def _apply_bubble_width(self,b:MessageBubble):
  w=max(300,int(self.scroll.viewport().width()*0.72))
  b.setMaximumWidth(w)
 def resizeEvent(self,e):
  super().resizeEvent(e)
  alive=[]
  for b in self._bubbles:
   try:self._apply_bubble_width(b);alive.append(b)
   except:pass
  self._bubbles=alive
 def _on_scroll_moved(self,v:int):
  bar=self.scroll.verticalScrollBar();self._autoscroll=v>=bar.maximum()-60
 def _scroll_to_bottom(self,force:bool=False):
  if force or self._autoscroll:bar=self.scroll.verticalScrollBar();bar.setValue(bar.maximum())
 def _show_status(self,t:str,error:bool=False):self.status_pill.setText(t);self.status_pill.setProperty("error",error);_repolish(self.status_pill);self.status_pill.setVisible(bool(t))
 def clear_chat(self):
  if self._generating:return
  self.chat_history=[];self.current_bubble=None;self._streamed_text=""
  while self.messages_layout.count()>2:
   it=self.messages_layout.takeAt(1);w=it.widget()
   if w:w.deleteLater()
  self._bubbles.clear();self.empty_state.setVisible(True)
 def send_message(self):
  if self._generating:self._cancel_generation();return
  q=self.input_box.toPlainText().strip()
  if not q:return
  m=self.model_combo.currentText();kb=self.kb_combo.currentText()
  if not m or "⚠" in m or "Loading" in m or "No models" in m or "No GGUF" in m:self._show_status("pick model",True);return
  if not kb:self._show_status("create KB first",True);return
  self.input_box.clear();self._add_bubble("user",q);self.chat_history.append({"role":"user","content":q})
  self.current_bubble=self._add_bubble("assistant","▌");self._set_busy(True);self._show_status("Thinking...")
  if config.llm_backend=="gguf":
   # Resolve m to full path securely. m is usually basename from combo.
   # Try to map basename -> full path via GGUFClient logic
   try:
    from core.llm_client import GGUFClient
    tmp_client = GGUFClient(config.gguf_model_path, n_ctx=config.gguf_n_ctx, n_threads=config.gguf_n_threads, n_gpu_layers=config.gguf_n_gpu_layers, embedding_path=config.gguf_embedding_model_path or config.gguf_model_path)
    resolved = tmp_client._resolve_path(m)
    if resolved and os.path.isfile(resolved):
     # Validate before committing
     from core.gguf_validator import validate_gguf_file
     try:
      validate_gguf_file(resolved)
      config.gguf_model_path = resolved
     except Exception as ve:
      self._show_status(f"GGUF invalid: {ve}", True)
      # keep previous path
      pass
    elif os.path.isfile(m):
     config.gguf_model_path = os.path.realpath(m)
    elif config.gguf_model_path and os.path.basename(config.gguf_model_path)==m:
     pass
    elif m and os.path.isfile(os.path.join(os.path.dirname(config.gguf_model_path or ""),m)):
     config.gguf_model_path=os.path.join(os.path.dirname(config.gguf_model_path),m)
   except Exception:
    # fallback old logic
    if os.path.isfile(m):config.gguf_model_path=m
    elif config.gguf_model_path and os.path.basename(config.gguf_model_path)==m:pass
    elif m and os.path.isfile(os.path.join(os.path.dirname(config.gguf_model_path or ""),m)):config.gguf_model_path=os.path.join(os.path.dirname(config.gguf_model_path),m)
   config.chat_model=config.gguf_model_path
  else:config.chat_model=m
  config.active_kb=kb;config.save()
  self._streamed_text=""
  self.current_worker=QueryWorker(self.engine,q,kb,self.chat_history[:-1],m)
  self.current_worker.meta_ready.connect(self._on_meta);self.current_worker.token_received.connect(self._on_token)
  self.current_worker.finished_ok.connect(self._on_finished);self.current_worker.failed.connect(self._on_failed)
  self.current_worker.start()
 def _set_busy(self,b:bool):
  self._generating=b;self.send_btn.setText("■ Stop" if b else "Send");self.clear_btn.setEnabled(not b)
  if not b:self.send_btn.setEnabled(True)
 def _cancel_generation(self):
  if self.current_worker:self.current_worker.stop()
  self.send_btn.setEnabled(False);self._show_status("Stopping...")
 def _on_meta(self,meta:dict):
  bits=[]
  if meta.get("candidates_found",0)==0:bits.append("no docs")
  else:
   bits.append(f"{meta.get('chunks_used',0)} chunks")
   if meta.get("chunks_overflow"):bits.append(f"{meta['chunks_overflow']} overflow")
   if meta.get("used_compression"):bits.append("compressed")
   bits.append(f"ctx {meta.get('context_window','?')}")
   src=meta.get("sources") or []
   if src:
    s=", ".join(src[:2])
    if len(src)>2:s+=f" +{len(src)-2}"
    bits.append(f"src: {s}")
  if self.current_bubble:self.current_bubble.set_meta(" • ".join(bits))
  self._show_status("Generating...")
 def _on_token(self,t:str):
  self._streamed_text+=t
  if not self._flush_timer.isActive():self._flush_timer.start()
 def _flush_stream(self):
  if self.current_bubble:
   try:self.current_bubble.set_text(self._streamed_text+" ▌")
   except:self._flush_timer.stop();return
  self._scroll_to_bottom()
 def _on_finished(self):
  self._flush_timer.stop()
  if self.current_bubble:
   try:self.current_bubble.set_text(self._streamed_text or "(empty)")
   except:pass
  self.chat_history.append({"role":"assistant","content":self._streamed_text})
  self.current_bubble=None;self.current_worker=None;self._set_busy(False);self._show_status("")
 def _on_failed(self,err:str):
  self._flush_timer.stop()
  if self.current_bubble:
   try:self.current_bubble.set_text(f"⚠ {err}")
   except:pass
  self.current_bubble=None;self.current_worker=None;self._set_busy(False);self._show_status(err,True)
