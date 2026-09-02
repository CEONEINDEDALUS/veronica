from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QFrame, QScrollArea, QPlainTextEdit,
    QGridLayout, QMessageBox
)

from core.config import Config, config
from core.llm_client import normalize_host


def _section(title: str, subtitle: str = "") -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    t = QLabel(title)
    t.setObjectName("cardTitle")
    layout.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("pageSubtitle")
        s.setWordWrap(True)
        layout.addWidget(s)
    return frame


class SettingsPage(QWidget):
    def __init__(self, on_saved=None):
        super().__init__()
        self.on_saved = on_saved
        self._build_ui()
        self._load_from_config(config)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        header = QVBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Tune connection, retrieval, and context behavior. Changes apply after saving.")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # --- Connection ---
        conn = _section("Ollama connection", "Where Veronica sends chat and embedding requests. Runs fully local.")
        g = QGridLayout()
        g.addWidget(QLabel("Ollama host:"), 0, 0)
        self.ollama_host_edit = QLineEdit()
        self.ollama_host_edit.setPlaceholderText("http://localhost:11434")
        g.addWidget(self.ollama_host_edit, 0, 1)
        conn.layout().addLayout(g)
        layout.addWidget(conn)

        # --- Embeddings ---
        emb = _section(
            "Embeddings",
            "How document chunks are turned into vectors for retrieval. Changing the "
            "backend or model requires re-ingesting existing knowledge bases."
        )
        g2 = QGridLayout()
        g2.addWidget(QLabel("Embedding backend:"), 0, 0)
        self.embed_backend_combo = QComboBox()
        self.embed_backend_combo.addItems(["ollama", "sentence_transformers"])
        g2.addWidget(self.embed_backend_combo, 0, 1)

        g2.addWidget(QLabel("Ollama embedding model:"), 1, 0)
        self.ollama_embed_model_edit = QLineEdit()
        self.ollama_embed_model_edit.setPlaceholderText("e.g. nomic-embed-text, mxbai-embed-large")
        g2.addWidget(self.ollama_embed_model_edit, 1, 1)

        g2.addWidget(QLabel("sentence-transformers model:"), 2, 0)
        self.st_embed_model_edit = QLineEdit()
        self.st_embed_model_edit.setPlaceholderText("e.g. all-MiniLM-L6-v2")
        g2.addWidget(self.st_embed_model_edit, 2, 1)
        emb.layout().addLayout(g2)
        layout.addWidget(emb)

        # --- Context window handling ---
        ctx = _section(
            "Context window handling",
            "This is what keeps answers coherent even on small-context local models: "
            "Veronica computes a real token budget, greedily fits the best chunks, and "
            "summarizes overflow content instead of silently dropping it."
        )
        g3 = QGridLayout()
        self.auto_ctx_check = QCheckBox("Auto-detect model context window (recommended)")
        g3.addWidget(self.auto_ctx_check, 0, 0, 1, 2)

        g3.addWidget(QLabel("Manual context window (tokens):"), 1, 0)
        self.manual_ctx_spin = QSpinBox()
        self.manual_ctx_spin.setRange(512, 2_000_000)
        self.manual_ctx_spin.setSingleStep(512)
        g3.addWidget(self.manual_ctx_spin, 1, 1)

        g3.addWidget(QLabel("Reserved tokens for output:"), 2, 0)
        self.reserved_output_spin = QSpinBox()
        self.reserved_output_spin.setRange(64, 8192)
        g3.addWidget(self.reserved_output_spin, 2, 1)

        g3.addWidget(QLabel("Reserved tokens for system prompt:"), 3, 0)
        self.reserved_system_spin = QSpinBox()
        self.reserved_system_spin.setRange(0, 4096)
        g3.addWidget(self.reserved_system_spin, 3, 1)

        g3.addWidget(QLabel("Max chat history turns kept:"), 4, 0)
        self.history_turns_spin = QSpinBox()
        self.history_turns_spin.setRange(0, 50)
        g3.addWidget(self.history_turns_spin, 4, 1)

        self.compression_check = QCheckBox("Compress overflow context via hierarchical summarization")
        g3.addWidget(self.compression_check, 5, 0, 1, 2)

        g3.addWidget(QLabel("Compression target (fraction of remaining budget):"), 6, 0)
        self.compression_ratio_spin = QDoubleSpinBox()
        self.compression_ratio_spin.setRange(0.1, 1.0)
        self.compression_ratio_spin.setSingleStep(0.05)
        g3.addWidget(self.compression_ratio_spin, 6, 1)
        ctx.layout().addLayout(g3)
        layout.addWidget(ctx)

        # --- Retrieval / chunking ---
        ret = _section("Retrieval & chunking", "How documents are split and how many chunks are retrieved.")
        g4 = QGridLayout()
        g4.addWidget(QLabel("Chunk size (characters):"), 0, 0)
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(100, 8000)
        self.chunk_size_spin.setSingleStep(50)
        g4.addWidget(self.chunk_size_spin, 0, 1)

        g4.addWidget(QLabel("Chunk overlap (characters):"), 1, 0)
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 2000)
        g4.addWidget(self.chunk_overlap_spin, 1, 1)

        g4.addWidget(QLabel("Top-K chunks to use:"), 2, 0)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 50)
        g4.addWidget(self.top_k_spin, 2, 1)

        g4.addWidget(QLabel("Candidate multiplier:"), 3, 0)
        self.candidate_mult_spin = QSpinBox()
        self.candidate_mult_spin.setRange(1, 10)
        g4.addWidget(self.candidate_mult_spin, 3, 1)

        g4.addWidget(QLabel("Similarity floor (0 = off):"), 4, 0)
        self.similarity_floor_spin = QDoubleSpinBox()
        self.similarity_floor_spin.setRange(0.0, 1.0)
        self.similarity_floor_spin.setSingleStep(0.05)
        g4.addWidget(self.similarity_floor_spin, 4, 1)
        ret.layout().addLayout(g4)
        layout.addWidget(ret)

        # --- Generation ---
        gen = _section("Generation", "How Veronica writes her answers.")
        g5 = QGridLayout()
        g5.addWidget(QLabel("Temperature:"), 0, 0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.05)
        g5.addWidget(self.temperature_spin, 0, 1)
        gen.layout().addLayout(g5)

        gen.layout().addWidget(QLabel("System prompt:"))
        self.system_prompt_edit = QPlainTextEdit()
        self.system_prompt_edit.setFixedHeight(96)
        gen.layout().addWidget(self.system_prompt_edit)
        layout.addWidget(gen)

        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        save_row = QHBoxLayout()
        restore_btn = QPushButton("Restore defaults")
        restore_btn.setToolTip("Loads default values into this page; press Save settings to keep them.")
        restore_btn.clicked.connect(self._restore_defaults)
        save_row.addWidget(restore_btn)
        save_row.addStretch(1)
        save_btn = QPushButton("Save settings")
        save_btn.setObjectName("primaryButton")
        save_btn.setMinimumWidth(140)
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        outer.addLayout(save_row)

    def _load_from_config(self, c: Config):
        self.ollama_host_edit.setText(c.ollama_host)

        self.embed_backend_combo.setCurrentText(c.embedding_backend)
        self.ollama_embed_model_edit.setText(c.ollama_embedding_model)
        self.st_embed_model_edit.setText(c.st_embedding_model)

        self.auto_ctx_check.setChecked(c.auto_detect_context)
        self.manual_ctx_spin.setValue(c.manual_context_window)
        self.reserved_output_spin.setValue(c.reserved_output_tokens)
        self.reserved_system_spin.setValue(c.reserved_system_tokens)
        self.history_turns_spin.setValue(c.max_chat_history_turns)
        self.compression_check.setChecked(c.enable_context_compression)
        self.compression_ratio_spin.setValue(c.compression_target_ratio)

        self.chunk_size_spin.setValue(c.chunk_size)
        self.chunk_overlap_spin.setValue(c.chunk_overlap)
        self.top_k_spin.setValue(c.top_k)
        self.candidate_mult_spin.setValue(c.candidate_multiplier)
        self.similarity_floor_spin.setValue(c.similarity_floor)

        self.temperature_spin.setValue(c.temperature)
        self.system_prompt_edit.setPlainText(c.system_prompt)

    def _restore_defaults(self):
        self._load_from_config(Config())

    def _save(self):
        c = config
        try:
            c.ollama_host = normalize_host(self.ollama_host_edit.text().strip()) or c.ollama_host
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Ollama host", str(e))
            self.ollama_host_edit.setText(c.ollama_host)
            return

        new_backend = self.embed_backend_combo.currentText()
        new_ollama_model = self.ollama_embed_model_edit.text().strip() or c.ollama_embedding_model
        new_st_model = self.st_embed_model_edit.text().strip() or c.st_embedding_model
        embedding_changed = (
            (new_backend, new_ollama_model, new_st_model)
            != (c.embedding_backend, c.ollama_embedding_model, c.st_embedding_model)
        )

        chunk_size = self.chunk_size_spin.value()
        overlap = self.chunk_overlap_spin.value()
        if overlap >= chunk_size:
            overlap = max(0, chunk_size // 5)
            self.chunk_overlap_spin.setValue(overlap)
            QMessageBox.information(
                self, "Chunk overlap adjusted",
                f"Overlap must be smaller than chunk size; it was set to {overlap}.",
            )

        c.embedding_backend = new_backend
        c.ollama_embedding_model = new_ollama_model
        c.st_embedding_model = new_st_model

        c.auto_detect_context = self.auto_ctx_check.isChecked()
        c.manual_context_window = self.manual_ctx_spin.value()
        c.reserved_output_tokens = self.reserved_output_spin.value()
        c.reserved_system_tokens = self.reserved_system_spin.value()
        c.max_chat_history_turns = self.history_turns_spin.value()
        c.enable_context_compression = self.compression_check.isChecked()
        c.compression_target_ratio = self.compression_ratio_spin.value()

        c.chunk_size = chunk_size
        c.chunk_overlap = overlap
        c.top_k = self.top_k_spin.value()
        c.candidate_multiplier = self.candidate_mult_spin.value()
        c.similarity_floor = self.similarity_floor_spin.value()

        c.temperature = self.temperature_spin.value()
        c.system_prompt = self.system_prompt_edit.toPlainText().strip() or c.system_prompt

        c.save()
        msg = "Settings saved."
        if embedding_changed:
            msg += ("\n\nNote: the embedding model changed. Existing knowledge bases were "
                    "built with the previous model and must be re-ingested before queries "
                    "can use them.")
        QMessageBox.information(self, "Saved", msg)
        if self.on_saved:
            self.on_saved()
