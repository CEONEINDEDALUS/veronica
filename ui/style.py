"""
Veronica's premium dark theme. 'Veronica' is also the name of the speedwell
flower - small violet-blue blooms - hence the accent palette.

build_stylesheet() covers every widget used in the app (including spin boxes,
menus, message boxes, tables, combo popups) so nothing falls back to a light
native style. build_palette() mirrors the same colors into QPalette so native
rendering bits (combo arrows, checkbox ticks, placeholder text, disabled
states) stay consistent with the stylesheet.
"""
from __future__ import annotations

BG_0 = "#121017"       # window background
BG_1 = "#1A1721"       # panels / sidebar
BG_2 = "#221E2C"       # cards / inputs
BG_3 = "#2B2636"       # hover
BORDER = "#38324A"
BORDER_SOFT = "#2E2940"
TEXT = "#F0EDF8"
TEXT_DIM = "#9A93AC"
ACCENT_DEFAULT = "#8B5CF6"
DANGER = "#F87171"
SUCCESS = "#4ADE80"


def _rgb(hexc: str):
    h = hexc.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


import re as _re

_HEX_COLOR = _re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def sanitize_accent(color: str) -> str:
    """Only well-formed hex colors survive into stylesheets/palettes."""
    c = (color or "").strip()
    if _re.fullmatch(r"[0-9a-fA-F]{6}", c):
        c = "#" + c
    if _HEX_COLOR.match(c):
        if len(c) == 4:
            c = "#" + "".join(ch * 2 for ch in c[1:])
        return c.lower()
    return ACCENT_DEFAULT


def _rgba(hexc: str, alpha: float) -> str:
    r, g, b = _rgb(hexc)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _mix(hexc: str, other: str, factor: float) -> str:
    r1, g1, b1 = _rgb(hexc)
    r2, g2, b2 = _rgb(other)
    r = round(r1 + (r2 - r1) * factor)
    g = round(g1 + (g2 - g1) * factor)
    b = round(b1 + (b2 - b1) * factor)
    return f"#{r:02X}{g:02X}{b:02X}"


def build_palette(accent: str = ACCENT_DEFAULT):
    from PyQt6.QtGui import QPalette, QColor

    accent_hover = _mix(accent, "#FFFFFF", 0.22)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG_0))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_1))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DIM))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_2))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Link, QColor(accent_hover))
    pal.setColor(QPalette.ColorRole.Light, QColor(BG_3))
    pal.setColor(QPalette.ColorRole.Midlight, QColor(BG_3))
    pal.setColor(QPalette.ColorRole.Mid, QColor(BORDER))
    pal.setColor(QPalette.ColorRole.Dark, QColor("#0C0A10"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_DIM))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_DIM))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(TEXT_DIM))
    return pal


def build_stylesheet(accent: str = ACCENT_DEFAULT) -> str:
    accent_hover = _mix(accent, "#FFFFFF", 0.22)
    accent_pressed = _mix(accent, "#000000", 0.30)
    danger_hover = _mix(DANGER, "#000000", 0.25)

    return f"""
    * {{
        font-family: 'Segoe UI', 'Inter', 'Ubuntu', 'Noto Sans', sans-serif;
        color: {TEXT};
        outline: none;
        selection-background-color: {accent};
        selection-color: #FFFFFF;
    }}
    *:disabled {{
        color: {_mix(TEXT_DIM, BG_0, 0.35)};
    }}

    QMainWindow, QWidget#centralWidget {{
        background-color: {BG_0};
    }}

    /* ---------- Sidebar ---------- */
    QWidget#sidebar {{
        background-color: {BG_1};
        border-right: 1px solid {BORDER_SOFT};
    }}

    QLabel#brandTitle {{
        color: {TEXT};
        font-size: 21px;
        font-weight: 800;
        letter-spacing: 0.4px;
        padding: 22px 18px 2px 18px;
    }}
    QLabel#brandSubtitle {{
        color: {TEXT_DIM};
        font-size: 11px;
        padding: 0px 18px 20px 18px;
    }}

    QPushButton#navButton {{
        background-color: transparent;
        color: {TEXT_DIM};
        border: none;
        border-radius: 9px;
        text-align: left;
        padding: 11px 16px;
        margin: 2px 12px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton#navButton:hover {{
        background-color: {_rgba(accent, 0.08)};
        color: {TEXT};
    }}
    QPushButton#navButton:checked {{
        background-color: {_rgba(accent, 0.16)};
        color: {TEXT};
        font-weight: 700;
    }}

    QWidget#contentArea {{
        background-color: {BG_0};
    }}

    /* ---------- Page headers & cards ---------- */
    QLabel#pageTitle {{
        font-size: 20px;
        font-weight: 800;
        letter-spacing: 0.2px;
        color: {TEXT};
    }}
    QLabel#pageSubtitle {{
        font-size: 12px;
        color: {TEXT_DIM};
    }}
    QLabel#fieldLabel {{
        font-size: 12px;
        font-weight: 600;
        color: {TEXT_DIM};
    }}
    QLabel#cardTitle {{
        font-size: 14px;
        font-weight: 700;
        color: {TEXT};
    }}

    QFrame#card {{
        background-color: {BG_1};
        border: 1px solid {BORDER_SOFT};
        border-radius: 14px;
    }}

    /* ---------- Chat ---------- */
    QWidget#messagesContainer {{
        background-color: transparent;
    }}

    QFrame#userBubble {{
        background-color: {accent};
        border-radius: 16px;
        border-bottom-right-radius: 5px;
    }}
    QFrame#assistantBubble {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 16px;
        border-bottom-left-radius: 5px;
    }}
    QFrame#userBubble QLabel#bubbleRole {{
        color: {_rgba("#FFFFFF", 0.72)};
    }}
    QFrame#assistantBubble QLabel#bubbleRole {{
        color: {accent_hover};
    }}
    QLabel#bubbleRole {{
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.8px;
        background: transparent;
    }}
    QLabel#bubbleText {{
        font-size: 13px;
        background: transparent;
    }}
    QFrame#userBubble QLabel#bubbleText,
    QFrame#userBubble QLabel#bubbleMeta {{
        color: #FFFFFF;
    }}
    QLabel#bubbleMeta {{
        font-size: 10px;
        color: {TEXT_DIM};
        background: transparent;
    }}

    QLabel#emptyState {{
        font-size: 14px;
        color: {TEXT_DIM};
        padding: 90px 40px 0px 40px;
        background: transparent;
    }}

    QLabel#statusPill {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 11px;
        padding: 4px 12px;
        font-size: 10px;
        font-weight: 600;
        color: {TEXT_DIM};
    }}
    QLabel#statusPill[error="true"] {{
        background-color: {_rgba(DANGER, 0.12)};
        border: 1px solid {_rgba(DANGER, 0.55)};
        color: {DANGER};
    }}

    QPushButton#iconButton {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 8px;
        padding: 7px 0px;
        font-size: 13px;
    }}

    /* ---------- Inputs ---------- */
    QTextEdit, QLineEdit, QPlainTextEdit {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 10px;
        padding: 9px 12px;
        font-size: 13px;
        selection-background-color: {accent};
    }}
    QTextEdit:focus, QLineEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {accent};
        background-color: {_mix(BG_2, BG_3, 0.45)};
    }}

    QSpinBox, QDoubleSpinBox {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
        min-width: 110px;
    }}
    QSpinBox:hover, QDoubleSpinBox:hover {{
        border: 1px solid {BORDER};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {accent};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: transparent;
        border: none;
        width: 18px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {BG_3};
        border-radius: 4px;
    }}

    QCheckBox {{
        font-size: 12px;
        spacing: 9px;
        padding: 2px 0px;
    }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 5px;
        border: 1px solid {BORDER};
        background-color: {BG_2};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {accent};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
    }}
    QCheckBox::indicator:checked:hover {{
        background-color: {accent_hover};
    }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 9px;
        padding: 9px 18px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {BG_3};
        border: 1px solid {accent};
    }}
    QPushButton:pressed {{
        background-color: {BG_2};
    }}
    QPushButton:disabled {{
        color: {_mix(TEXT_DIM, BG_0, 0.35)};
        background-color: {BG_1};
        border: 1px solid {BORDER_SOFT};
    }}

    QPushButton#primaryButton {{
        background-color: {accent};
        border: none;
        color: #FFFFFF;
        padding: 10px 20px;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {accent_hover};
    }}
    QPushButton#primaryButton:pressed {{
        background-color: {accent_pressed};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: {_mix(accent, BG_1, 0.55)};
        color: {_rgba("#FFFFFF", 0.65)};
    }}

    QPushButton#dangerButton {{
        background-color: transparent;
        border: 1px solid {_rgba(DANGER, 0.6)};
        color: {DANGER};
    }}
    QPushButton#dangerButton:hover {{
        background-color: {DANGER};
        border: 1px solid {DANGER};
        color: #FFFFFF;
    }}
    QPushButton#dangerButton:pressed {{
        background-color: {danger_hover};
        color: #FFFFFF;
    }}
    QPushButton#dangerButton:disabled {{
        border: 1px solid {BORDER_SOFT};
        color: {_mix(TEXT_DIM, BG_0, 0.35)};
        background-color: transparent;
    }}

    /* ---------- Combo boxes ---------- */
    QComboBox {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 9px;
        padding: 7px 12px;
        font-size: 12px;
        min-height: 18px;
    }}
    QComboBox:hover {{
        border: 1px solid {BORDER};
    }}
    QComboBox:focus {{
        border: 1px solid {accent};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 9px;
        padding: 4px;
        selection-background-color: {_rgba(accent, 0.28)};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 30px;
        border-radius: 6px;
        padding: 4px 8px;
        margin: 1px 2px;
    }}

    /* ---------- Table ---------- */
    QTableWidget {{
        background-color: {BG_1};
        alternate-background-color: {_mix(BG_1, BG_2, 0.5)};
        border: 1px solid {BORDER_SOFT};
        border-radius: 10px;
        gridline-color: transparent;
        selection-background-color: {_rgba(accent, 0.24)};
        selection-color: {TEXT};
    }}
    QTableWidget::item {{
        padding: 6px 10px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {_rgba(accent, 0.24)};
        border-left: 2px solid {accent};
    }}
    QHeaderView::section {{
        background-color: {BG_2};
        border: none;
        border-bottom: 1px solid {BORDER_SOFT};
        padding: 9px 10px;
        font-weight: 700;
        font-size: 11px;
        color: {TEXT_DIM};
    }}
    QTableCornerButton::section {{
        background-color: {BG_2};
        border: none;
    }}

    /* ---------- Progress ---------- */
    QProgressBar {{
        background-color: {BG_2};
        border: 1px solid {BORDER_SOFT};
        border-radius: 7px;
        text-align: center;
        font-size: 10px;
        font-weight: 600;
        min-height: 16px;
        max-height: 16px;
        color: {TEXT_DIM};
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 6px;
    }}

    /* ---------- Scrollbars ---------- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BG_3};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BG_3};
        border-radius: 4px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {accent};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}

    /* ---------- Menus & dialogs ---------- */
    QMenu {{
        background-color: {BG_2};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 24px 7px 14px;
        border-radius: 6px;
        font-size: 12px;
    }}
    QMenu::item:selected {{
        background-color: {_rgba(accent, 0.28)};
    }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER_SOFT};
        margin: 5px 8px;
    }}

    QMessageBox, QDialog {{
        background-color: {BG_1};
    }}
    QMessageBox QLabel {{
        color: {TEXT};
        font-size: 13px;
        background: transparent;
    }}
    QMessageBox QPushButton {{
        min-width: 84px;
        padding: 8px 16px;
    }}

    QToolTip {{
        background-color: {BG_2};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 8px;
        font-size: 11px;
    }}

    QSplitter::handle {{
        background-color: {BORDER_SOFT};
    }}
    """
