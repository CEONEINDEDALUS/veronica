"""
A modern, dark, violet-accented theme. 'Veronica' is also the name of the
speedwell flower - small violet-blue blooms - hence the accent palette.
"""

BG_0 = "#121017"       # window background
BG_1 = "#1A1720"       # panels
BG_2 = "#221E2C"       # cards / inputs
BG_3 = "#2B2636"       # hover
BORDER = "#3A3446"
TEXT = "#EDEAF5"
TEXT_DIM = "#9A93AC"
ACCENT = "#8B5CF6"
ACCENT_HOVER = "#A480FA"
ACCENT_DIM = "#5B3FA0"
DANGER = "#F87171"
SUCCESS = "#4ADE80"


def build_stylesheet(accent: str = ACCENT) -> str:
    accent_hover = ACCENT_HOVER
    return f"""
    * {{
        font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
        color: {TEXT};
        outline: none;
    }}

    QMainWindow, QWidget#centralWidget {{
        background-color: {BG_0};
    }}

    QWidget#sidebar {{
        background-color: {BG_1};
        border-right: 1px solid {BORDER};
    }}

    QLabel#brandTitle {{
        color: {TEXT};
        font-size: 20px;
        font-weight: 700;
        padding: 18px 16px 2px 16px;
    }}

    QLabel#brandSubtitle {{
        color: {TEXT_DIM};
        font-size: 11px;
        padding: 0px 16px 18px 16px;
    }}

    QPushButton#navButton {{
        background-color: transparent;
        color: {TEXT_DIM};
        border: none;
        text-align: left;
        padding: 12px 18px;
        font-size: 13px;
        font-weight: 600;
        border-left: 3px solid transparent;
    }}
    QPushButton#navButton:hover {{
        background-color: {BG_2};
        color: {TEXT};
    }}
    QPushButton#navButton:checked {{
        background-color: {BG_2};
        color: {TEXT};
        border-left: 3px solid {accent};
    }}

    QWidget#contentArea {{
        background-color: {BG_0};
    }}

    QLabel#pageTitle {{
        font-size: 18px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#pageSubtitle {{
        font-size: 12px;
        color: {TEXT_DIM};
    }}

    QFrame#card {{
        background-color: {BG_1};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}

    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}

    QFrame#userBubble {{
        background-color: {accent};
        border-radius: 14px;
    }}
    QFrame#assistantBubble {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}
    QLabel#bubbleText {{
        font-size: 13px;
        background: transparent;
    }}
    QLabel#bubbleMeta {{
        font-size: 10px;
        color: {TEXT_DIM};
        background: transparent;
    }}

    QTextEdit, QLineEdit, QPlainTextEdit {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 10px;
        font-size: 13px;
        selection-background-color: {accent};
    }}
    QTextEdit:focus, QLineEdit:focus {{
        border: 1px solid {accent};
    }}

    QPushButton {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {BG_3};
        border: 1px solid {accent};
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        background-color: {BG_1};
    }}

    QPushButton#primaryButton {{
        background-color: {accent};
        border: none;
        color: white;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {accent_hover};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: {ACCENT_DIM};
        color: #cfc3ef;
    }}

    QPushButton#dangerButton {{
        background-color: transparent;
        border: 1px solid {DANGER};
        color: {DANGER};
    }}
    QPushButton#dangerButton:hover {{
        background-color: {DANGER};
        color: white;
    }}

    QComboBox {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        selection-background-color: {accent};
        outline: none;
    }}

    QTableWidget {{
        background-color: {BG_1};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER};
    }}
    QHeaderView::section {{
        background-color: {BG_2};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px;
        font-weight: 600;
        font-size: 11px;
        color: {TEXT_DIM};
    }}

    QProgressBar {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 6px;
        text-align: center;
        font-size: 10px;
        height: 16px;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 6px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {BG_3};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QSlider::groove:horizontal {{
        background: {BG_2};
        height: 5px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {accent};
        width: 15px;
        height: 15px;
        margin: -5px 0;
        border-radius: 7px;
    }}

    QCheckBox {{
        font-size: 12px;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER};
        background-color: {BG_2};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
    }}

    QSplitter::handle {{
        background-color: {BORDER};
    }}

    QToolTip {{
        background-color: {BG_2};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px;
    }}

    QLabel#statusPill {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 10px;
        color: {TEXT_DIM};
    }}
    """
