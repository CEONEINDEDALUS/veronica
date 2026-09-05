from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QFrame,
    QScrollArea,
    QPlainTextEdit,
    QGridLayout,
    QMessageBox,
    QFileDialog,
)
from core.config import Config, config
from core.llm_client import normalize_host
import os


def _section(t: str, s: str = "") -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    l = QVBoxLayout(f)
    l.setContentsMargins(16, 14, 16, 14)
    l.setSpacing(10)
    a = QLabel(t)
    a.setObjectName("cardTitle")
    l.addWidget(a)
    if s:
        b = QLabel(s)
        b.setObjectName("pageSubtitle")
        b.setWordWrap(True)
        l.addWidget(b)
    return f


def _validate_gguf_for_ui(path: str) -> tuple[bool, str]:
    """Return (ok, err). Handles file or directory."""
    if not path:
        return True, ""
    path = path.strip()
    if os.path.isfile(path):
        try:
            from core.gguf_validator import validate_gguf_file

            validate_gguf_file(path)
            return True, ""
        except Exception as e:
            return False, str(e)
    if os.path.isdir(path):
        import glob

        g = glob.glob(os.path.join(path, "*.gguf")) + glob.glob(
            os.path.join(path, "*.GGUF")
        )
        if not g:
            return False, "folder contains no .gguf files"
        # validate at least one file
        for cand in g[:5]:
            try:
                from core.gguf_validator import validate_gguf_file

                validate_gguf_file(cand)
                return True, ""
            except:
                continue
        return False, "folder has no valid GGUF (all failed header check)"
    return False, "path not found"


def _prompt_trust_for_ssti(parent, path: str, err: str) -> bool:
    """Show Trust dialog for SSTI-blocked GGUF. Returns True if user trusted (once or always) and file now validates."""
    if "SSTI" not in err and "chat_template" not in err:
        return False
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("GGUF validation – potentially unsafe template")
    box.setText(f"Selected file failed safety check:\n{err}")
    box.setInformativeText(
        "This GGUF's chat_template could execute code on vulnerable\n"
        "llama-cpp-python (<0.2.72). Only load it if you trust the source.\n\n"
        "• Trust Once – allow for this session only\n"
        "• Trust Always – remember this template (stored in config)\n"
        "• Cancel – keep blocked (recommended for untrusted models)"
    )
    btn_once = box.addButton("Trust Once", QMessageBox.ButtonRole.AcceptRole)
    btn_always = box.addButton("Trust Always", QMessageBox.ButtonRole.AcceptRole)
    btn_cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(btn_cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked == btn_once:
        try:
            from core.gguf_validator import (
                trust_template_for_session,
                get_chat_template,
                validate_gguf_file as _vf,
            )

            tmpl = get_chat_template(path) if os.path.isfile(path) else None
            # for folder, pick first template
            if tmpl is None and os.path.isdir(path):
                import glob

                for cand in glob.glob(os.path.join(path, "*.gguf"))[:3]:
                    tmpl = get_chat_template(cand)
                    if tmpl:
                        path = cand
                        break
            trust_template_for_session(tmpl, path)
            _vf(path)
            return True
        except Exception as e2:
            QMessageBox.warning(
                parent, "GGUF validation", f"Still failed after trusting:\n{e2}"
            )
            return False
    elif clicked == btn_always:
        try:
            import hashlib
            from core.gguf_validator import (
                trust_template_for_session,
                get_chat_template,
                get_chat_template_hash,
                validate_gguf_file as _vf,
            )
            from core.config import config as _cfg

            tmpl = get_chat_template(path) if os.path.isfile(path) else None
            cand_path = path
            if tmpl is None and os.path.isdir(path):
                import glob

                for cand in glob.glob(os.path.join(path, "*.gguf"))[:3]:
                    t = get_chat_template(cand)
                    if t:
                        tmpl = t
                        cand_path = cand
                        break
            h = get_chat_template_hash(cand_path) if os.path.isfile(cand_path) else None
            if not h and tmpl:
                h = hashlib.sha256(tmpl.encode("utf-8", errors="replace")).hexdigest()
            if tmpl:
                trust_template_for_session(tmpl, cand_path)
            if h:
                _cfg.trust_gguf_template(h)
                _cfg.save()
            _vf(cand_path)
            return True
        except Exception as e2:
            QMessageBox.warning(
                parent, "GGUF validation", f"Still failed after trusting:\n{e2}"
            )
            return False
    return False


class SettingsPage(QWidget):
    def __init__(self, on_saved=None):
        super().__init__()
        self.on_saved = on_saved
        self._build_ui()
        self._load_from_config(config)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)
        h = QVBoxLayout()
        a = QLabel("Settings")
        a.setObjectName("pageTitle")
        b = QLabel("Tune backends, retrieval & context")
        b.setObjectName("pageSubtitle")
        h.addWidget(a)
        h.addWidget(b)
        outer.addLayout(h)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        llm = _section("LLM backend", "Choose Ollama server or raw GGUF local model")
        g0 = QGridLayout()
        g0.addWidget(QLabel("Backend:"), 0, 0)
        self.llm_backend_combo = QComboBox()
        self.llm_backend_combo.addItems(["ollama", "gguf"])
        self.llm_backend_combo.currentTextChanged.connect(self._toggle_gguf)
        g0.addWidget(self.llm_backend_combo, 0, 1)
        g0.addWidget(QLabel("GGUF model (.gguf):"), 1, 0)
        self.gguf_path_edit = QLineEdit()
        self.gguf_path_edit.setPlaceholderText("/path/to/model.gguf or folder")
        g0.addWidget(self.gguf_path_edit, 1, 1)
        self.gguf_pick_btn = QPushButton("Browse")
        self.gguf_pick_btn.clicked.connect(self._pick_gguf)
        g0.addWidget(self.gguf_pick_btn, 1, 2)
        g0.addWidget(QLabel("GGUF n_ctx:"), 2, 0)
        self.gguf_n_ctx_spin = QSpinBox()
        self.gguf_n_ctx_spin.setRange(512, 262144)
        self.gguf_n_ctx_spin.setSingleStep(1024)
        g0.addWidget(self.gguf_n_ctx_spin, 2, 1)
        g0.addWidget(QLabel("Threads (0=auto):"), 3, 0)
        self.gguf_threads_spin = QSpinBox()
        self.gguf_threads_spin.setRange(0, 64)
        g0.addWidget(self.gguf_threads_spin, 3, 1)
        g0.addWidget(QLabel("GPU layers (0=CPU):"), 4, 0)
        self.gguf_gpu_spin = QSpinBox()
        self.gguf_gpu_spin.setRange(0, 100)
        g0.addWidget(self.gguf_gpu_spin, 4, 1)
        llm.layout().addLayout(g0)
        lay.addWidget(llm)
        conn = _section("Ollama", "local host when backend=ollama")
        g = QGridLayout()
        g.addWidget(QLabel("Host:"), 0, 0)
        self.ollama_host_edit = QLineEdit()
        self.ollama_host_edit.setPlaceholderText("http://localhost:11434")
        g.addWidget(self.ollama_host_edit, 0, 1)
        conn.layout().addLayout(g)
        lay.addWidget(conn)
        emb = _section("Embeddings", "vectors - ollama / sentence_transformers / gguf")
        g2 = QGridLayout()
        g2.addWidget(QLabel("Backend:"), 0, 0)
        self.embed_backend_combo = QComboBox()
        self.embed_backend_combo.addItems(["ollama", "sentence_transformers", "gguf"])
        self.embed_backend_combo.currentTextChanged.connect(self._toggle_emb)
        g2.addWidget(self.embed_backend_combo, 0, 1)
        g2.addWidget(QLabel("Ollama model:"), 1, 0)
        self.ollama_embed_model_edit = QLineEdit()
        g2.addWidget(self.ollama_embed_model_edit, 1, 1)
        g2.addWidget(QLabel("ST model:"), 2, 0)
        self.st_embed_model_edit = QLineEdit()
        g2.addWidget(self.st_embed_model_edit, 2, 1)
        g2.addWidget(QLabel("GGUF embed (.gguf):"), 3, 0)
        self.gguf_emb_path_edit = QLineEdit()
        self.gguf_emb_path_edit.setPlaceholderText(
            "/path/to/embed.gguf (optional, falls back to LLM GGUF)"
        )
        g2.addWidget(self.gguf_emb_path_edit, 3, 1)
        self.gguf_emb_pick_btn = QPushButton("Browse")
        self.gguf_emb_pick_btn.clicked.connect(self._pick_gguf_emb)
        g2.addWidget(self.gguf_emb_pick_btn, 3, 2)
        emb.layout().addLayout(g2)
        lay.addWidget(emb)
        trust = _section(
            "Trusted templates",
            "Allow SSTI-flagged chat_templates you explicitly trust",
        )
        gh = QHBoxLayout()
        self.trust_label = QLabel()
        self.trust_label.setObjectName("pageSubtitle")
        self.trust_label.setWordWrap(True)
        gh.addWidget(self.trust_label, 1)
        self.trust_clear_btn = QPushButton("Clear trusted")
        self.trust_clear_btn.setToolTip(
            "Forget all trusted templates (re-enable blocking)"
        )
        self.trust_clear_btn.clicked.connect(self._clear_trusted)
        gh.addWidget(self.trust_clear_btn)
        trust.layout().addLayout(gh)
        lay.addWidget(trust)
        self._refresh_trust_label()
        ctx = _section("Context window", "budget & compression")
        g3 = QGridLayout()
        self.auto_ctx_check = QCheckBox("Auto-detect")
        g3.addWidget(self.auto_ctx_check, 0, 0, 1, 2)
        g3.addWidget(QLabel("Manual ctx:"), 1, 0)
        self.manual_ctx_spin = QSpinBox()
        self.manual_ctx_spin.setRange(512, 262144)
        self.manual_ctx_spin.setSingleStep(1024)
        g3.addWidget(self.manual_ctx_spin, 1, 1)
        g3.addWidget(QLabel("Reserved out:"), 2, 0)
        self.reserved_output_spin = QSpinBox()
        self.reserved_output_spin.setRange(64, 4096)
        g3.addWidget(self.reserved_output_spin, 2, 1)
        g3.addWidget(QLabel("Reserved sys:"), 3, 0)
        self.reserved_system_spin = QSpinBox()
        self.reserved_system_spin.setRange(0, 2048)
        g3.addWidget(self.reserved_system_spin, 3, 1)
        g3.addWidget(QLabel("History turns:"), 4, 0)
        self.history_turns_spin = QSpinBox()
        self.history_turns_spin.setRange(0, 20)
        g3.addWidget(self.history_turns_spin, 4, 1)
        self.compression_check = QCheckBox("Compress overflow")
        g3.addWidget(self.compression_check, 5, 0, 1, 2)
        g3.addWidget(QLabel("Ratio:"), 6, 0)
        self.compression_ratio_spin = QDoubleSpinBox()
        self.compression_ratio_spin.setRange(0.1, 1.0)
        self.compression_ratio_spin.setSingleStep(0.05)
        g3.addWidget(self.compression_ratio_spin, 6, 1)
        ctx.layout().addLayout(g3)
        lay.addWidget(ctx)
        ret = _section("Retrieval & chunking")
        g4 = QGridLayout()
        g4.addWidget(QLabel("Chunk size:"), 0, 0)
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(200, 4000)
        self.chunk_size_spin.setSingleStep(50)
        g4.addWidget(self.chunk_size_spin, 0, 1)
        g4.addWidget(QLabel("Overlap:"), 1, 0)
        self.chunk_overlap_spin = QSpinBox()
        self.chunk_overlap_spin.setRange(0, 1000)
        g4.addWidget(self.chunk_overlap_spin, 1, 1)
        g4.addWidget(QLabel("Top-K:"), 2, 0)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 20)
        g4.addWidget(self.top_k_spin, 2, 1)
        g4.addWidget(QLabel("Candidate mult:"), 3, 0)
        self.candidate_mult_spin = QSpinBox()
        self.candidate_mult_spin.setRange(1, 5)
        g4.addWidget(self.candidate_mult_spin, 3, 1)
        g4.addWidget(QLabel("Sim floor:"), 4, 0)
        self.similarity_floor_spin = QDoubleSpinBox()
        self.similarity_floor_spin.setRange(0.0, 1.0)
        self.similarity_floor_spin.setSingleStep(0.05)
        g4.addWidget(self.similarity_floor_spin, 4, 1)
        ret.layout().addLayout(g4)
        lay.addWidget(ret)
        gate = _section("Confidence", "distance gate")
        g4b = QGridLayout()
        g4b.addWidget(QLabel("Max distance:"), 0, 0)
        self.max_distance_spin = QDoubleSpinBox()
        self.max_distance_spin.setRange(0.0, 1.0)
        self.max_distance_spin.setSingleStep(0.05)
        g4b.addWidget(self.max_distance_spin, 0, 1)
        self.use_reranker_check = QCheckBox("Use reranker (CPU heavy)")
        g4b.addWidget(self.use_reranker_check, 1, 0, 1, 2)
        g4b.addWidget(QLabel("Rerank N:"), 2, 0)
        self.rerank_top_n_spin = QSpinBox()
        self.rerank_top_n_spin.setRange(1, 10)
        g4b.addWidget(self.rerank_top_n_spin, 2, 1)
        gate.layout().addLayout(g4b)
        lay.addWidget(gate)
        conv = _section("Conversation")
        g5b = QGridLayout()
        g5b.addWidget(QLabel("Recent turns:"), 0, 0)
        self.recent_turns_spin = QSpinBox()
        self.recent_turns_spin.setRange(0, 10)
        g5b.addWidget(self.recent_turns_spin, 0, 1)
        conv.layout().addLayout(g5b)
        lay.addWidget(conv)
        gen = _section("Generation")
        g5 = QGridLayout()
        g5.addWidget(QLabel("Temp:"), 0, 0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.05)
        g5.addWidget(self.temperature_spin, 0, 1)
        gen.layout().addLayout(g5)
        gen.layout().addWidget(QLabel("System prompt:"))
        self.system_prompt_edit = QPlainTextEdit()
        self.system_prompt_edit.setFixedHeight(80)
        gen.layout().addWidget(self.system_prompt_edit)
        lay.addWidget(gen)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        sr = QHBoxLayout()
        rb = QPushButton("Restore")
        rb.clicked.connect(self._restore_defaults)
        sr.addWidget(rb)
        sr.addStretch(1)
        sb = QPushButton("Save")
        sb.setObjectName("primaryButton")
        sb.setMinimumWidth(120)
        sb.clicked.connect(self._save)
        sr.addWidget(sb)
        outer.addLayout(sr)

    def _toggle_gguf(self, txt):
        is_g = txt == "gguf"

        self.gguf_path_edit.setEnabled(is_g)
        self.gguf_pick_btn.setEnabled(is_g)
        self.gguf_n_ctx_spin.setEnabled(is_g)
        self.gguf_threads_spin.setEnabled(is_g)
        self.gguf_gpu_spin.setEnabled(is_g)

    def _toggle_emb(self, txt):
        is_g = txt == "gguf"

        self.gguf_emb_path_edit.setEnabled(is_g)
        self.gguf_emb_pick_btn.setEnabled(is_g)

    def _pick_gguf(self):
        start = (
            os.path.dirname(self.gguf_path_edit.text().strip())
            if self.gguf_path_edit.text().strip()
            else ""
        )
        if start and not os.path.isdir(start):
            start = ""
        f, _ = QFileDialog.getOpenFileName(
            self, "Pick GGUF model", start, "GGUF Files (*.gguf);;All Files (*)"
        )
        if not f:
            return
        ok, err = _validate_gguf_for_ui(f)
        if not ok:
            is_ssti = "SSTI" in err or "chat_template" in err
            if is_ssti and _prompt_trust_for_ssti(self, f, err):
                ok, err = _validate_gguf_for_ui(f)
                if not ok:
                    QMessageBox.warning(
                        self,
                        "GGUF validation",
                        f"Selected file still failed:\n{err}",
                    )
                    return
            else:
                if not is_ssti:
                    QMessageBox.warning(
                        self,
                        "GGUF validation",
                        f"Selected file failed validation:\n{err}",
                    )
                return
        self.gguf_path_edit.setText(f)
        self._refresh_trust_label()

    def _pick_gguf_emb(self):
        start = (
            os.path.dirname(self.gguf_emb_path_edit.text().strip())
            if self.gguf_emb_path_edit.text().strip()
            else ""
        )
        if start and not os.path.isdir(start):
            start = ""
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Pick GGUF Embedding model",
            start,
            "GGUF Files (*.gguf);;All Files (*)",
        )
        if not f:
            return
        ok, err = _validate_gguf_for_ui(f)
        if not ok:
            is_ssti = "SSTI" in err or "chat_template" in err
            if is_ssti and _prompt_trust_for_ssti(self, f, err):
                ok, err = _validate_gguf_for_ui(f)
                if not ok:
                    QMessageBox.warning(
                        self,
                        "GGUF validation",
                        f"Selected file still failed:\n{err}",
                    )
                    return
            else:
                if not is_ssti:
                    QMessageBox.warning(
                        self,
                        "GGUF validation",
                        f"Selected file failed validation:\n{err}",
                    )
                return
        self.gguf_emb_path_edit.setText(f)
        self._refresh_trust_label()

    def _load_from_config(self, c: Config):
        self.llm_backend_combo.setCurrentText(c.llm_backend)
        self.gguf_path_edit.setText(c.gguf_model_path)
        self.gguf_n_ctx_spin.setValue(c.gguf_n_ctx)
        self.gguf_threads_spin.setValue(c.gguf_n_threads)
        self.gguf_gpu_spin.setValue(c.gguf_n_gpu_layers)
        self.ollama_host_edit.setText(c.ollama_host)
        self.embed_backend_combo.setCurrentText(c.embedding_backend)
        self.ollama_embed_model_edit.setText(c.ollama_embedding_model)
        self.st_embed_model_edit.setText(c.st_embedding_model)
        self.gguf_emb_path_edit.setText(c.gguf_embedding_model_path)
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
        self.max_distance_spin.setValue(c.max_distance)
        self.use_reranker_check.setChecked(c.use_reranker)
        self.rerank_top_n_spin.setValue(c.rerank_top_n)
        self.recent_turns_spin.setValue(c.max_recent_turns)
        self.temperature_spin.setValue(c.temperature)
        self.system_prompt_edit.setPlainText(c.system_prompt)
        self._toggle_gguf(c.llm_backend)
        self._toggle_emb(c.embedding_backend)
        try:
            self._refresh_trust_label()
        except:
            pass

    def _refresh_trust_label(self):
        try:
            n = len(config.trusted_gguf_template_hashes or [])
        except:
            n = 0
        self.trust_label.setText(
            f"{n} template(s) trusted — SSTI check bypassed for these. Only trust models from sources you trust."
        )
        self.trust_clear_btn.setEnabled(n > 0)

    def _clear_trusted(self):
        n = len(config.trusted_gguf_template_hashes or [])
        if n == 0:
            QMessageBox.information(self, "Trusted", "No trusted templates to clear.")
            return
        if (
            QMessageBox.question(
                self,
                "Clear trusted?",
                f"Forget {n} trusted chat_template(s)?\nThey will be blocked again on next load.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        config.trusted_gguf_template_hashes = []
        try:
            from core.gguf_validator import _SESSION_TRUSTED_HASHES

            _SESSION_TRUSTED_HASHES.clear()
        except:
            pass
        config.save()
        self._refresh_trust_label()
        QMessageBox.information(self, "Cleared", "Trusted templates cleared.")

    def _restore_defaults(self):
        # keep trusted list when restoring defaults? clear or keep - keep for safety
        self._load_from_config(Config())
        # restore trusted from current config
        try:
            tmp = Config()
            tmp.trusted_gguf_template_hashes = list(
                config.trusted_gguf_template_hashes or []
            )
            # _load_from_config will overwrite, so patch back
            config.trusted_gguf_template_hashes = tmp.trusted_gguf_template_hashes
        except:
            pass
        self._refresh_trust_label()

    def _save(self):
        c = config
        c.llm_backend = self.llm_backend_combo.currentText()
        gp = self.gguf_path_edit.text().strip()
        if c.llm_backend == "gguf":
            if not gp:
                QMessageBox.warning(
                    self, "GGUF", "Chat GGUF path required when backend=gguf"
                )
                return
            ok, err = _validate_gguf_for_ui(gp)
            if not ok:
                is_ssti = "SSTI" in err or "chat_template" in err
                if is_ssti and _prompt_trust_for_ssti(self, gp, err):
                    ok, err = _validate_gguf_for_ui(gp)
                    if not ok:
                        QMessageBox.warning(
                            self, "GGUF", f"Chat GGUF still invalid:\n{err}"
                        )
                        return
                else:
                    if not is_ssti:
                        QMessageBox.warning(self, "GGUF", f"Chat GGUF invalid:\n{err}")
                    return
        elif gp:
            ok, err = _validate_gguf_for_ui(gp)
            if not ok:
                is_ssti = "SSTI" in err or "chat_template" in err
                if is_ssti and _prompt_trust_for_ssti(self, gp, err):
                    ok, err = _validate_gguf_for_ui(gp)
                    if not ok:
                        QMessageBox.warning(
                            self, "GGUF", f"Chat GGUF still invalid:\n{err}"
                        )
                        pass
                else:
                    QMessageBox.warning(
                        self,
                        "GGUF",
                        f"Chat GGUF invalid (will be ignored until backend=gguf):\n{err}",
                    )
                # don't block save, just warn
                pass
        c.gguf_model_path = gp
        c.gguf_n_ctx = self.gguf_n_ctx_spin.value()
        c.gguf_n_threads = self.gguf_threads_spin.value()
        c.gguf_n_gpu_layers = self.gguf_gpu_spin.value()
        try:
            c.ollama_host = (
                normalize_host(self.ollama_host_edit.text().strip()) or c.ollama_host
            )
        except ValueError as e:
            QMessageBox.warning(self, "Bad host", str(e))
            self.ollama_host_edit.setText(c.ollama_host)
            return
        nb = self.embed_backend_combo.currentText()
        no = self.ollama_embed_model_edit.text().strip() or c.ollama_embedding_model
        ns = self.st_embed_model_edit.text().strip() or c.st_embedding_model
        ge = self.gguf_emb_path_edit.text().strip()
        if nb == "gguf":
            if ge:
                ok, err = _validate_gguf_for_ui(ge)
                if not ok:
                    is_ssti = "SSTI" in err or "chat_template" in err
                    if is_ssti and _prompt_trust_for_ssti(self, ge, err):
                        ok, err = _validate_gguf_for_ui(ge)
                        if not ok:
                            QMessageBox.warning(
                                self, "GGUF", f"Embed GGUF still invalid:\n{err}"
                            )
                            return
                    else:
                        if not is_ssti:
                            QMessageBox.warning(
                                self, "GGUF", f"Embed GGUF invalid:\n{err}"
                            )
                        return
            elif c.llm_backend == "gguf" and gp:
                ok, err = _validate_gguf_for_ui(gp)
                if not ok:
                    is_ssti = "SSTI" in err or "chat_template" in err
                    if is_ssti and _prompt_trust_for_ssti(self, gp, err):
                        ok, err = _validate_gguf_for_ui(gp)
                        if not ok:
                            QMessageBox.warning(
                                self,
                                "GGUF",
                                f"Embed will fallback to LLM GGUF which is invalid:\n{err}",
                            )
                            return
                    else:
                        if not is_ssti:
                            QMessageBox.warning(
                                self,
                                "GGUF",
                                f"Embed will fallback to LLM GGUF which is invalid:\n{err}",
                            )
                        return
            else:
                QMessageBox.warning(
                    self,
                    "GGUF",
                    "Embed GGUF not set (will fallback to LLM GGUF if available)",
                )
                # not fatal, allow empty but inform
                pass
        chg = (nb, no, ns, ge) != (
            c.embedding_backend,
            c.ollama_embedding_model,
            c.st_embedding_model,
            c.gguf_embedding_model_path,
        )
        cs = self.chunk_size_spin.value()
        ov = self.chunk_overlap_spin.value()
        if ov >= cs:
            ov = max(0, cs // 5)
            self.chunk_overlap_spin.setValue(ov)
            QMessageBox.information(self, "Fix", f"overlap set {ov}")
        c.embedding_backend = nb
        c.ollama_embedding_model = no
        c.st_embedding_model = ns
        c.gguf_embedding_model_path = ge
        c.auto_detect_context = self.auto_ctx_check.isChecked()
        c.manual_context_window = self.manual_ctx_spin.value()
        c.reserved_output_tokens = self.reserved_output_spin.value()
        c.reserved_system_tokens = self.reserved_system_spin.value()
        c.max_chat_history_turns = self.history_turns_spin.value()
        c.enable_context_compression = self.compression_check.isChecked()
        c.compression_target_ratio = self.compression_ratio_spin.value()
        c.chunk_size = cs
        c.chunk_overlap = ov
        c.top_k = self.top_k_spin.value()
        c.candidate_multiplier = self.candidate_mult_spin.value()
        c.similarity_floor = self.similarity_floor_spin.value()
        c.max_distance = self.max_distance_spin.value()
        c.use_reranker = self.use_reranker_check.isChecked()
        c.rerank_top_n = self.rerank_top_n_spin.value()
        c.max_recent_turns = self.recent_turns_spin.value()
        c.temperature = self.temperature_spin.value()
        c.system_prompt = (
            self.system_prompt_edit.toPlainText().strip() or c.system_prompt
        )
        c.save()
        self._refresh_trust_label()
        msg = "Saved."
        if chg:
            msg += "\nEmbedding changed re-ingest needed."
        if c.llm_backend == "gguf" and not c.gguf_model_path:
            msg += "\nSelect GGUF model path."
        QMessageBox.information(self, "Saved", msg)
        if self.on_saved:
            self.on_saved()
