from __future__ import annotations
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QProgressBar, QComboBox, QInputDialog,
    QPlainTextEdit, QMessageBox, QHeaderView, QAbstractItemView,
    QSpacerItem, QSizePolicy
)

from core.config import config
from core.rag_engine import RagEngine
from core.document_loader import SUPPORTED_EXTENSIONS
from ui.workers import IngestWorker, KBSummaryWorker


class DocumentsPage(QWidget):
    def __init__(self, engine: RagEngine):
        super().__init__()
        self.engine = engine
        self.pending_files: List[str] = []
        self._build_ui()
        self.refresh_kb_list()
        self.refresh_table()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Documents")
        title.setObjectName("pageTitle")
        exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        subtitle = QLabel(f"Upload as many files as you like. Re-uploading a file replaces its old chunks. Supported: {exts}")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        root.addLayout(header)

        kb_row = QHBoxLayout()
        kb_label = QLabel("Knowledge base")
        kb_label.setObjectName("fieldLabel")
        kb_row.addWidget(kb_label)
        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(180)
        self.kb_combo.currentTextChanged.connect(self.refresh_table)
        kb_row.addWidget(self.kb_combo)

        new_kb_btn = QPushButton("+ New KB")
        new_kb_btn.clicked.connect(self.create_kb)
        kb_row.addWidget(new_kb_btn)

        delete_kb_btn = QPushButton("Delete KB")
        delete_kb_btn.setObjectName("dangerButton")
        delete_kb_btn.clicked.connect(self.delete_kb)
        kb_row.addWidget(delete_kb_btn)

        kb_row.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding))

        add_folder_btn = QPushButton("Add folder...")
        add_folder_btn.clicked.connect(self.add_folder)
        kb_row.addWidget(add_folder_btn)

        add_files_btn = QPushButton("Add files...")
        add_files_btn.setObjectName("primaryButton")
        add_files_btn.clicked.connect(self.add_files)
        kb_row.addWidget(add_files_btn)

        root.addLayout(kb_row)

        table_actions = QHBoxLayout()
        hint = QLabel("Select a row to remove that document from this knowledge base.")
        hint.setObjectName("pageSubtitle")
        table_actions.addWidget(hint)
        table_actions.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding))
        self.remove_doc_btn = QPushButton("Remove selected")
        self.remove_doc_btn.setObjectName("dangerButton")
        self.remove_doc_btn.setEnabled(False)
        self.remove_doc_btn.clicked.connect(self.remove_selected_document)
        table_actions.addWidget(self.remove_doc_btn)
        root.addLayout(table_actions)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Source file", "Chunks stored"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        root.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setObjectName("logView")
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        self.log.setPlaceholderText("Ingestion log will appear here...")
        root.addWidget(self.log)

    # ---------- KB management ----------
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
        self.refresh_table()

    def create_kb(self):
        import re
        name, ok = QInputDialog.getText(self, "New knowledge base", "Name:")
        if not (ok and name.strip()):
            return
        name = name.strip().replace(" ", "_")
        if len(name) < 3 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
            QMessageBox.warning(
                self, "Invalid name",
                "Knowledge base names need at least 3 characters and may only use "
                "letters, digits, dots, dashes and underscores.",
            )
            return
        try:
            self.engine.store.get_collection(name)  # creates it
        except Exception as e:
            QMessageBox.warning(self, "Could not create knowledge base", str(e))
            return
        self.refresh_kb_list()
        self.kb_combo.setCurrentText(name)
        config.active_kb = name
        config.save()

    def delete_kb(self):
        name = self.kb_combo.currentText()
        if not name:
            return
        confirm = QMessageBox.question(
            self, "Delete knowledge base",
            f"Permanently delete '{name}' and all its embedded documents?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.engine.store.delete_knowledge_base(name)
            if config.active_kb == name:
                config.active_kb = "default"
                config.save()
            self.refresh_kb_list()

    def current_kb(self) -> str:
        return self.kb_combo.currentText() or config.active_kb

    # ---------- file selection ----------
    def add_files(self):
        filt = "Documents (*" + " *".join(sorted(SUPPORTED_EXTENSIONS)) + ");;All files (*)"
        files, _ = QFileDialog.getOpenFileNames(self, "Select files to ingest", "", filt)
        if files:
            self._start_ingest(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select a folder to ingest")
        if folder:
            from core.document_loader import iter_supported_files
            files = list(iter_supported_files(folder))
            if not files:
                QMessageBox.information(self, "No supported files",
                                         "No supported document types were found in that folder.")
                return
            self._start_ingest(files)

    def _start_ingest(self, files: List[str]):
        kb = self.current_kb()
        if not kb:
            QMessageBox.warning(self, "No knowledge base", "Create or select a knowledge base first.")
            return
        prev = getattr(self, "worker", None)
        if prev is not None and prev.isRunning():
            QMessageBox.information(self, "Ingestion in progress",
                                     "Please wait for the current ingestion to finish.")
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress.setMaximum(len(files))
        self.log.appendPlainText(f"Starting ingestion of {len(files)} file(s) into '{kb}'...")

        self.worker = IngestWorker(self.engine, files, kb)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_ingest_done)
        self.worker.failed.connect(self._on_ingest_failed)
        self.worker.start()

    def _on_progress(self, message: str, current: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.log.appendPlainText(message)

    def _on_ingest_done(self, result: dict):
        self.log.appendPlainText(
            f"Done: {result['files']} file(s), {result['chunks']} chunk(s) stored."
        )
        for err in result.get("errors", []):
            self.log.appendPlainText(f"  ⚠ {err}")
        self.progress.setVisible(False)
        self.refresh_kb_list()

    def _on_ingest_failed(self, err: str):
        self.log.appendPlainText(f"⚠ Ingestion failed: {err}")
        self.progress.setVisible(False)

    # ---------- document removal ----------
    def _on_table_selection(self):
        has_selection = bool(self.table.selectionModel() and self.table.selectionModel().hasSelection())
        self.remove_doc_btn.setEnabled(has_selection and self.table.rowCount() > 0)

    def remove_selected_document(self):
        row = self.table.currentRow()
        if row < 0:
            return
        source_item = self.table.item(row, 0)
        if not source_item:
            return
        source = source_item.text()
        kb = self.current_kb()
        confirm = QMessageBox.question(
            self, "Remove document",
            f"Remove '{source}' (all its chunks) from knowledge base '{kb}'?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if self.engine.store.remove_document(kb, source):
            self.log.appendPlainText(f"Removed '{source}' from '{kb}'.")
        else:
            QMessageBox.warning(self, "Remove document", f"Could not remove '{source}'.")
        self.refresh_table()

    # ---------- table ----------
    def refresh_table(self):
        kb = self.current_kb()
        self.table.setRowCount(0)
        self.remove_doc_btn.setEnabled(False)
        if not kb:
            return
        self._summary_gen = getattr(self, "_summary_gen", 0) + 1
        gen = self._summary_gen
        prev = getattr(self, "_summary_worker", None)
        if prev is not None and prev.isRunning():
            self._retired_workers = [w for w in getattr(self, "_retired_workers", [])
                                     if w.isRunning()]
            self._retired_workers.append(prev)
        worker = KBSummaryWorker(self.engine, kb)
        self._summary_worker = worker
        worker.summary_ready.connect(
            lambda name, summary, g=gen, wk=worker: self._on_summary_ready(g, name, summary, wk)
        )
        worker.start()

    def _on_summary_ready(self, gen: int, kb: str, summary: dict, worker):
        try:
            if gen != getattr(self, "_summary_gen", 0) or kb != self.current_kb():
                return
            for row, (src, count) in enumerate(sorted(summary.items())):
                self.table.insertRow(row)
                name_item = QTableWidgetItem(src)
                count_item = QTableWidgetItem(str(count))
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, count_item)
        finally:
            if worker is getattr(self, "_summary_worker", None) and worker.isFinished():
                self._summary_worker = None
