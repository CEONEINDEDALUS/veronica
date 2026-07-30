from __future__ import annotations
from typing import List
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QProgressBar, QComboBox, QInputDialog,
    QPlainTextEdit, QMessageBox, QHeaderView, QSpacerItem, QSizePolicy, QFrame
)

from core.config import config
from core.rag_engine import RagEngine
from core.document_loader import SUPPORTED_EXTENSIONS
from ui.workers import IngestWorker


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
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Documents")
        title.setObjectName("pageTitle")
        exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        subtitle = QLabel(f"Upload as many files as you like. Supported: {exts}")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        root.addLayout(header)

        kb_row = QHBoxLayout()
        kb_row.addWidget(QLabel("Knowledge base:"))
        self.kb_combo = QComboBox()
        self.kb_combo.setMinimumWidth(180)
        self.kb_combo.currentTextChanged.connect(self.refresh_table)
        kb_row.addWidget(self.kb_combo)

        new_kb_btn = QPushButton("+ New")
        new_kb_btn.clicked.connect(self.create_kb)
        kb_row.addWidget(new_kb_btn)

        delete_kb_btn = QPushButton("Delete KB")
        delete_kb_btn.setObjectName("dangerButton")
        delete_kb_btn.clicked.connect(self.delete_kb)
        kb_row.addWidget(delete_kb_btn)

        kb_row.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding))

        add_files_btn = QPushButton("Add files...")
        add_files_btn.setObjectName("primaryButton")
        add_files_btn.clicked.connect(self.add_files)
        kb_row.addWidget(add_files_btn)

        add_folder_btn = QPushButton("Add folder...")
        add_folder_btn.clicked.connect(self.add_folder)
        kb_row.addWidget(add_folder_btn)

        root.addLayout(kb_row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Source file", "Chunks stored"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
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
        self.kb_combo.blockSignals(False)

    def create_kb(self):
        name, ok = QInputDialog.getText(self, "New knowledge base", "Name:")
        if ok and name.strip():
            name = name.strip().replace(" ", "_")
            self.engine.store.get_collection(name)  # creates it
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
            self.refresh_kb_list()
            self.refresh_table()

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
        self.refresh_table()

    def _on_ingest_failed(self, err: str):
        self.log.appendPlainText(f"⚠ Ingestion failed: {err}")
        self.progress.setVisible(False)

    def refresh_table(self):
        kb = self.current_kb()
        self.table.setRowCount(0)
        if not kb:
            return
        summary = self.engine.store.document_summary(kb)
        for row, (src, count) in enumerate(sorted(summary.items())):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(src))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))
