from __future__ import annotations
from typing import List, Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QTextEdit,
    QPushButton, QComboBox, QSizePolicy, QSpacerItem
)
from PyQt6.QtGui import QKeyEvent

from core.config import config
from core.rag_engine import RagEngine
from ui.workers import QueryWorker, ModelListWorker


class ChatInput(QTextEdit):
    """A QTextEdit that sends on Enter and inserts a newline on Shift+Enter."""
    def __init__(self, on_send):
        super().__init__()
        self.on_send = on_send
        self.setPlaceholderText("Ask Veronica about your documents…   (Enter to send · Shift+Enter for a new line)")
        self.setFixedHeight(76)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.on_send()
            return
        super().keyPressEvent(e)


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str = ""):
        super().__init__()
        self.role = role
        self.setObjectName("userBubble" if role == "user" else "assistantBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        role_label = QLabel("You" if role == "user" else "Veronica")
        role_label.setObjectName("bubbleRole")
        layout.addWidget(role_label)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("bubbleText")
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setOpenExternalLinks(False)
        layout.addWidget(self.text_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("bubbleMeta")
        self.meta_label.setVisible(False)
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

    def set_text(self, text: str):
        self.text_label.setText(text)

    def set_meta(self, meta: str):
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))


def _repolish(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ChatPage(QWidget):
    def __init__(self, engine: RagEngine):
        super().__init__()
        self.engine = engine
        self.chat_history: List[Dict] = []
        self.current_worker: Optional[QueryWorker] = None
        self.current_bubble: Optional[MessageBubble] = None
        self._streamed_text = ""
        self._generating = False
        self._autoscroll = True
        self._bubbles: List[MessageBubble] = []
        self._model_gen = 0
        self._build_ui()
        self.refresh_models()
        self.refresh_kb_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Chat")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Ask questions grounded in your private knowledge base.")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding))

        kb_label = QLabel("Knowledge base")
        kb_label.setObjectName("fieldLabel")
        header.addWidget(kb_label)
        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(160)
        header.addWidget(self.kb_combo)

        model_label = QLabel("Model")
        model_label.setObjectName("fieldLabel")
        header.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        header.addWidget(self.model_combo)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setObjectName("iconButton")
        refresh_btn.setFixedWidth(38)
        refresh_btn.setToolTip("Refresh model list")
        refresh_btn.clicked.connect(self.refresh_models)
        header.addWidget(refresh_btn)

        root.addLayout(header)

        self.status_pill = QLabel("")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setVisible(False)
        root.addWidget(self.status_pill)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages_container = QWidget()
        self.messages_container.setObjectName("messagesContainer")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(4, 4, 10, 4)
        self.messages_layout.setSpacing(14)

        self.empty_state = QLabel(
            "🪄\n\nStart the conversation\n\nAsk anything about the documents in your "
            "knowledge base — answers cite their sources and never leave your machine."
        )
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.empty_state.setWordWrap(True)
        self.messages_layout.addWidget(self.empty_state)
        self.messages_layout.addStretch(1)

        self.scroll.setWidget(self.messages_container)
        root.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_moved)

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(33)
        self._flush_timer.timeout.connect(self._flush_stream)

        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self.input_box = ChatInput(self.send_message)
        input_row.addWidget(self.input_box, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setMinimumWidth(96)
        self.send_btn.clicked.connect(self.send_message)
        self.clear_btn = QPushButton("Clear chat")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self.clear_chat)
        btn_col.addWidget(self.send_btn)
        btn_col.addWidget(self.clear_btn)
        input_row.addLayout(btn_col)

        root.addLayout(input_row)

    # ---------- data population ----------
    def refresh_kb_list(self):
        current = self.kb_combo.currentText()
        self.kb_combo.blockSignals(True)
        self.kb_combo.clear()
        kbs = self.engine.store.list_knowledge_bases() or [config.active_kb]
        self.kb_combo.addItems(kbs)
        if current in kbs:
            self.kb_combo.setCurrentText(current)
        elif config.active_kb in kbs:
            self.kb_combo.setCurrentText(config.active_kb)
        self.kb_combo.blockSignals(False)

    def refresh_models(self):
        self._model_gen += 1
        gen = self._model_gen
        prev = getattr(self, "_model_worker", None)
        if prev is not None and prev.isRunning():
            self._retired_workers = [w for w in getattr(self, "_retired_workers", [])
                                     if w.isRunning()]
            self._retired_workers.append(prev)
        self.model_combo.clear()
        self.model_combo.addItem("Loading models...")
        worker = ModelListWorker(self.engine)
        self._model_worker = worker
        worker.finished_ok.connect(lambda models, g=gen: self._on_models_loaded(g, models))
        worker.failed.connect(lambda err, g=gen: self._on_models_failed(g, err))
        worker.start()

    def _on_models_loaded(self, gen: int, models: List[str]):
        if gen != self._model_gen:
            return
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem("No models found")
            return
        self.model_combo.addItems(models)
        if config.chat_model in models:
            self.model_combo.setCurrentText(config.chat_model)

    def _on_models_failed(self, gen: int, err: str):
        if gen != self._model_gen:
            return
        self.model_combo.clear()
        self.model_combo.addItem("⚠ Could not connect")
        self._show_status(f"Could not reach Ollama at {config.ollama_host} — is it running?", error=True)

    # ---------- chat flow ----------
    def _add_bubble(self, role: str, text: str = "") -> MessageBubble:
        self.empty_state.setVisible(False)
        bubble = MessageBubble(role, text)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble, 0)
        else:
            row.addWidget(bubble, 0)
            row.addStretch(1)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self._apply_bubble_width(bubble)
        self._bubbles.append(bubble)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, wrapper)
        self._scroll_to_bottom(force=True)
        return bubble

    def _apply_bubble_width(self, bubble: MessageBubble):
        width = max(340, int(self.scroll.viewport().width() * 0.74))
        bubble.setMaximumWidth(width)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        alive = []
        for b in self._bubbles:
            try:
                self._apply_bubble_width(b)
                alive.append(b)
            except RuntimeError:
                pass
        self._bubbles = alive

    def _on_scroll_moved(self, value: int):
        bar = self.scroll.verticalScrollBar()
        self._autoscroll = value >= bar.maximum() - 56

    def _scroll_to_bottom(self, force: bool = False):
        if force or self._autoscroll:
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _show_status(self, text: str, error: bool = False):
        self.status_pill.setText(text)
        self.status_pill.setProperty("error", error)
        _repolish(self.status_pill)
        self.status_pill.setVisible(bool(text))

    def clear_chat(self):
        if self._generating:
            return
        self.chat_history = []
        self.current_bubble = None
        self._streamed_text = ""
        while self.messages_layout.count() > 2:
            item = self.messages_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        self._bubbles.clear()
        self.empty_state.setVisible(True)

    def send_message(self):
        if self._generating:
            self._cancel_generation()
            return
        question = self.input_box.toPlainText().strip()
        if not question:
            return
        model = self.model_combo.currentText()
        kb = self.kb_combo.currentText()
        if not model or "⚠" in model or "Loading" in model or "No models" in model:
            self._show_status("Select a valid model first.", error=True)
            return
        if not kb:
            self._show_status("Create a knowledge base in the Documents tab first.", error=True)
            return

        self.input_box.clear()
        self._add_bubble("user", question)
        self.chat_history.append({"role": "user", "content": question})

        self.current_bubble = self._add_bubble("assistant", "▌")
        self._set_busy(True)
        self._show_status("Thinking…")

        config.chat_model = model
        config.active_kb = kb
        config.save()

        self._streamed_text = ""
        self.current_worker = QueryWorker(self.engine, question, kb, self.chat_history[:-1], model)
        self.current_worker.meta_ready.connect(self._on_meta)
        self.current_worker.token_received.connect(self._on_token)
        self.current_worker.finished_ok.connect(self._on_finished)
        self.current_worker.failed.connect(self._on_failed)
        self.current_worker.start()

    def _set_busy(self, busy: bool):
        self._generating = busy
        self.send_btn.setText("■ Stop" if busy else "Send")
        self.clear_btn.setEnabled(not busy)
        if not busy:
            self.send_btn.setEnabled(True)

    def _cancel_generation(self):
        if self.current_worker is not None:
            self.current_worker.stop()
        self.send_btn.setEnabled(False)
        self._show_status("Stopping…")

    def _on_meta(self, meta: dict):
        bits = []
        if meta.get("candidates_found", 0) == 0:
            bits.append("no matching documents in this knowledge base")
        else:
            bits.append(f"{meta.get('chunks_used', 0)} chunk(s) used")
            if meta.get("chunks_overflow"):
                bits.append(f"{meta['chunks_overflow']} overflow")
            if meta.get("used_compression"):
                bits.append("context compressed to fit model window")
            bits.append(f"ctx {meta.get('context_window', '?')} tok")
            sources = meta.get("sources") or []
            if sources:
                shown = ", ".join(sources[:3])
                extra = len(sources) - 3
                if extra > 0:
                    shown += f" +{extra} more"
                bits.append(f"src: {shown}")
        if self.current_bubble:
            self.current_bubble.set_meta("  •  ".join(bits))
        self._show_status("Generating answer…")

    def _on_token(self, text: str):
        self._streamed_text += text
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_stream(self):
        if self.current_bubble:
            try:
                self.current_bubble.set_text(self._streamed_text + " ▌")
            except RuntimeError:
                self._flush_timer.stop()
                return
        self._scroll_to_bottom()

    def _on_finished(self):
        self._flush_timer.stop()
        if self.current_bubble:
            try:
                self.current_bubble.set_text(self._streamed_text or "*(empty response)*")
            except RuntimeError:
                pass
        self.chat_history.append({"role": "assistant", "content": self._streamed_text})
        self.current_bubble = None
        self.current_worker = None
        self._set_busy(False)
        self._show_status("")

    def _on_failed(self, err: str):
        self._flush_timer.stop()
        if self.current_bubble:
            try:
                self.current_bubble.set_text(f"⚠ {err}")
            except RuntimeError:
                pass
        self.current_bubble = None
        self.current_worker = None
        self._set_busy(False)
        self._show_status(err, error=True)
