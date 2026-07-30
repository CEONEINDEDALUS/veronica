from __future__ import annotations
from typing import List, Dict, Optional

from PyQt6.QtCore import Qt
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
        self.setPlaceholderText("Ask Veronica about your documents... (Enter to send, Shift+Enter for newline)")
        self.setFixedHeight(64)

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
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("bubbleText")
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.text_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("bubbleMeta")
        self.meta_label.setVisible(False)
        layout.addWidget(self.meta_label)

    def set_text(self, text: str):
        self.text_label.setText(text)

    def append_text(self, piece: str):
        current = self.text_label.text()
        self.text_label.setText(current + piece)

    def set_meta(self, meta: str):
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))


class ChatPage(QWidget):
    def __init__(self, engine: RagEngine):
        super().__init__()
        self.engine = engine
        self.chat_history: List[Dict] = []
        self.current_worker: Optional[QueryWorker] = None
        self.current_bubble: Optional[MessageBubble] = None
        self._build_ui()
        self.refresh_models()
        self.refresh_kb_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
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

        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(160)
        header.addWidget(QLabel("Knowledge base:"))
        header.addWidget(self.kb_combo)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        header.addWidget(QLabel("Model:"))
        header.addWidget(self.model_combo)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedWidth(36)
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
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch(1)
        self.messages_layout.setSpacing(10)
        self.scroll.setWidget(self.messages_container)
        root.addWidget(self.scroll, 1)

        input_row = QHBoxLayout()
        self.input_box = ChatInput(self.send_message)
        input_row.addWidget(self.input_box, 1)

        btn_col = QVBoxLayout()
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.clicked.connect(self.send_message)
        self.clear_btn = QPushButton("Clear chat")
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
        self.model_combo.clear()
        self.model_combo.addItem("Loading models...")
        self._model_worker = ModelListWorker(self.engine)
        self._model_worker.finished_ok.connect(self._on_models_loaded)
        self._model_worker.failed.connect(self._on_models_failed)
        self._model_worker.start()

    def _on_models_loaded(self, models: List[str]):
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem("No models found")
            return
        self.model_combo.addItems(models)
        if config.chat_model in models:
            self.model_combo.setCurrentText(config.chat_model)

    def _on_models_failed(self, err: str):
        self.model_combo.clear()
        self.model_combo.addItem("⚠ Could not connect")
        self._show_status(f"Could not reach backend: {err}", error=True)

    # ---------- chat flow ----------
    def _add_bubble(self, role: str, text: str = "") -> MessageBubble:
        bubble = MessageBubble(role, text)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble, 0)
        else:
            row.addWidget(bubble, 0)
            row.addStretch(1)
        bubble.setMaximumWidth(int(self.scroll.width() * 0.75) or 500)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, wrapper)
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _show_status(self, text: str, error: bool = False):
        self.status_pill.setText(text)
        self.status_pill.setVisible(bool(text))

    def clear_chat(self):
        self.chat_history = []
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def send_message(self):
        question = self.input_box.toPlainText().strip()
        if not question:
            return
        model = self.model_combo.currentText()
        kb = self.kb_combo.currentText()
        if not model or "⚠" in model or "Loading" in model or "No models" in model:
            self._show_status("Select a valid model first.", error=True)
            return

        self.input_box.clear()
        self._add_bubble("user", question)
        self.chat_history.append({"role": "user", "content": question})

        self.current_bubble = self._add_bubble("assistant", "▌")
        self.send_btn.setEnabled(False)
        self._show_status("Thinking...")

        config.chat_model = model
        config.active_kb = kb
        config.save()

        self.current_worker = QueryWorker(self.engine, question, kb, self.chat_history[:-1], model)
        self.current_worker.meta_ready.connect(self._on_meta)
        self.current_worker.token_received.connect(self._on_token)
        self.current_worker.finished_ok.connect(self._on_finished)
        self.current_worker.failed.connect(self._on_failed)
        self.current_worker.start()
        self._streamed_text = ""

    def _on_meta(self, meta: dict):
        bits = []
        if meta.get("candidates_found", 0) == 0:
            bits.append("no matching documents found in this knowledge base")
        else:
            bits.append(f"{meta['chunks_used']} chunk(s) used")
            if meta.get("chunks_overflow"):
                bits.append(f"{meta['chunks_overflow']} overflow")
            if meta.get("used_compression"):
                bits.append("context compressed to fit model window")
            bits.append(f"ctx window: {meta.get('context_window')} tok")
        if self.current_bubble:
            self.current_bubble.set_meta(" • ".join(bits))
        self._show_status("Generating answer...")

    def _on_token(self, text: str):
        self._streamed_text += text
        if self.current_bubble:
            self.current_bubble.set_text(self._streamed_text + " ▌")
        self._scroll_to_bottom()

    def _on_finished(self):
        if self.current_bubble:
            self.current_bubble.set_text(self._streamed_text or "*(empty response)*")
        self.chat_history.append({"role": "assistant", "content": self._streamed_text})
        self.send_btn.setEnabled(True)
        self._show_status("")

    def _on_failed(self, err: str):
        if self.current_bubble:
            self.current_bubble.set_text(f"⚠ Error: {err}")
        self.send_btn.setEnabled(True)
        self._show_status(f"Error: {err}", error=True)
