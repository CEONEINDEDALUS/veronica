from __future__ import annotations
from typing import List, Dict
from PyQt6.QtCore import QThread, pyqtSignal

from core.rag_engine import RagEngine


class IngestWorker(QThread):
    progress = pyqtSignal(str, int, int)   # message, current, total
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, engine: RagEngine, file_paths: List[str], kb_name: str):
        super().__init__()
        self.engine = engine
        self.file_paths = file_paths
        self.kb_name = kb_name

    def run(self):
        try:
            result = self.engine.ingest_files(
                self.file_paths, self.kb_name,
                progress_cb=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class ModelListWorker(QThread):
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, engine: RagEngine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            client = self.engine.get_llm_client()
            models = client.list_models()
            self.finished_ok.emit(models)
        except Exception as e:
            self.failed.emit(str(e))


class QueryWorker(QThread):
    meta_ready = pyqtSignal(dict)
    token_received = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, engine: RagEngine, question: str, kb_name: str,
                 chat_history: List[Dict], model: str):
        super().__init__()
        self.engine = engine
        self.question = question
        self.kb_name = kb_name
        self.chat_history = chat_history
        self.model = model
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            for event in self.engine.stream_answer(
                self.question, self.kb_name, self.chat_history, self.model
            ):
                if self._stop:
                    break
                if event["type"] == "meta":
                    self.meta_ready.emit(event)
                elif event["type"] == "token":
                    self.token_received.emit(event["text"])
                elif event["type"] == "error":
                    self.failed.emit(event["text"])
                    return
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))
