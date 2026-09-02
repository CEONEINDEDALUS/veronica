from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QButtonGroup, QSpacerItem, QSizePolicy
)

from core.config import config
from core.rag_engine import RagEngine
from ui.chat_widget import ChatPage
from ui.documents_widget import DocumentsPage
from ui.settings_widget import SettingsPage
from ui.style import build_stylesheet, sanitize_accent


class NavButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Veronica — Private RAG Assistant")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        self.engine = RagEngine(config)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        brand = QLabel("🔮 Veronica")
        brand.setObjectName("brandTitle")
        subtitle = QLabel("Private RAG · runs fully local")
        subtitle.setObjectName("brandSubtitle")
        side_layout.addWidget(brand)
        side_layout.addWidget(subtitle)

        self.btn_chat = NavButton("💬  Chat")
        self.btn_docs = NavButton("📁  Documents")
        self.btn_settings = NavButton("⚙️  Settings")

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, b in enumerate([self.btn_chat, self.btn_docs, self.btn_settings]):
            self.nav_group.addButton(b, i)
            side_layout.addWidget(b)

        side_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        footer = QLabel("v1.0 · 100% local, private")
        footer.setObjectName("brandSubtitle")
        footer.setContentsMargins(16, 8, 16, 16)
        side_layout.addWidget(footer)

        root.addWidget(sidebar)

        # --- Content area ---
        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.chat_page = ChatPage(self.engine)
        self.documents_page = DocumentsPage(self.engine)
        self.settings_page = SettingsPage(on_saved=self._on_settings_saved)

        self.stack.addWidget(self.chat_page)
        self.stack.addWidget(self.documents_page)
        self.stack.addWidget(self.settings_page)
        content_layout.addWidget(self.stack)

        root.addWidget(content, 1)

        self.btn_chat.clicked.connect(lambda: self._go(0))
        self.btn_docs.clicked.connect(lambda: self._go(1))
        self.btn_settings.clicked.connect(lambda: self._go(2))
        self.btn_chat.setChecked(True)

        config.accent_color = sanitize_accent(config.accent_color)
        self.setStyleSheet(build_stylesheet(config.accent_color))

    def _go(self, index: int):
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.documents_page.refresh_kb_list()
            self.documents_page.refresh_table()
        if index == 0:
            self.chat_page.refresh_kb_list()

    def _on_settings_saved(self):
        config.accent_color = sanitize_accent(config.accent_color)
        self.setStyleSheet(build_stylesheet(config.accent_color))
        self.chat_page.refresh_models()
        self.chat_page.refresh_kb_list()
