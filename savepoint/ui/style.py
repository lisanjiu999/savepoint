"""统一配色与样式表。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

ACCENT = "#2f6feb"
ACCENT_SOFT = "#eaf1ff"
TEXT = "#1f2328"
MUTED = "#6b7280"
LINE = "#e5e7eb"
BG = "#f5f6f8"

STATUS_COLORS = {
    "active": "#2f6feb",
    "paused": "#d97706",
    "done": "#16a34a",
    "archived": "#9ca3af",
}


def light_palette() -> QPalette:
    """强制浅色调色板。

    Windows 深色模式下 Qt 会拿到深色底，而样式表把文字写死成深色，
    结果就是深底黑字看不清。这里显式指定亮色，保证对比度。
    """
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    palette = QPalette()
    palette.setColor(role.Window, QColor(BG))
    palette.setColor(role.WindowText, QColor(TEXT))
    palette.setColor(role.Base, QColor("#ffffff"))
    palette.setColor(role.AlternateBase, QColor("#f2f4f8"))
    palette.setColor(role.Text, QColor(TEXT))
    palette.setColor(role.Button, QColor("#ffffff"))
    palette.setColor(role.ButtonText, QColor(TEXT))
    palette.setColor(role.BrightText, QColor("#ffffff"))
    palette.setColor(role.ToolTipBase, QColor(TEXT))
    palette.setColor(role.ToolTipText, QColor("#ffffff"))
    palette.setColor(role.Highlight, QColor(ACCENT))
    palette.setColor(role.HighlightedText, QColor("#ffffff"))
    palette.setColor(role.PlaceholderText, QColor("#9ca3af"))
    palette.setColor(role.Link, QColor(ACCENT))
    palette.setColor(role.Light, QColor("#ffffff"))
    palette.setColor(role.Midlight, QColor("#f0f1f4"))
    palette.setColor(role.Mid, QColor("#d9dde4"))
    palette.setColor(role.Dark, QColor("#b6bcc6"))
    palette.setColor(role.Shadow, QColor("#e5e7eb"))

    palette.setColor(group.Disabled, role.Text, QColor("#9ca3af"))
    palette.setColor(group.Disabled, role.WindowText, QColor("#9ca3af"))
    palette.setColor(group.Disabled, role.ButtonText, QColor("#9ca3af"))
    return palette

QSS = """
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10.5pt;
    color: #1f2328;
}
#Root { background: #f5f6f8; }
#Sidebar { background: #ffffff; border-right: 1px solid #e5e7eb; }
#TopBar { background: #ffffff; border-bottom: 1px solid #e5e7eb; }
#AppTitle { font-size: 13pt; font-weight: 600; }
#Muted { color: #6b7280; font-size: 9pt; }
#SectionTitle { font-size: 10pt; font-weight: 600; color: #374151; }
#CardTitle { font-size: 12.5pt; font-weight: 600; }
#Card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; }
#ShotCard {
    background: #ffffff;
    border: 1px solid #e8eaee;
    border-radius: 9px;
}
#ShotCard:hover { border-color: #c9d3e3; background: #fcfdff; }
#EntryCard {
    background: #ffffff;
    border: 1px solid #edeff3;
    border-radius: 8px;
}
#EntryCard:hover { border-color: #d7dfec; background: #fcfdff; }
#TagChip {
    color: #4b5563;
    background: #f2f4f8;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 1px 9px;
    font-size: 8.5pt;
}
#Divider { background: #eef0f3; max-height: 1px; border: none; }
#DropZone {
    border: 1px dashed #c7ccd4;
    border-radius: 8px;
    background: #fbfcfe;
    color: #6b7280;
}
#DropZoneActive {
    border: 1px dashed #2f6feb;
    border-radius: 8px;
    background: #eef4ff;
}

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border-radius: 6px; margin: 2px 6px; color: #1f2328; }
QListWidget::item:selected { background: #eaf1ff; color: #1f2328; }
QListWidget::item:hover { background: #f2f4f8; color: #1f2328; }

QTreeWidget { outline: none; }
QTreeWidget::item { color: #1f2328; }
QTreeWidget::item:selected { background: #eaf1ff; color: #1f2328; }
QTreeWidget::item:hover { background: #f2f4f8; color: #1f2328; }
QTreeView::branch { background: transparent; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #d9dde4;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #bcd3ff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #2f6feb;
}
QLineEdit#SearchBox { padding: 6px 10px; background: #f2f4f8; border: 1px solid #e5e7eb; }

QPushButton {
    background: #ffffff;
    border: 1px solid #d9dde4;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background: #f2f4f8; }
QPushButton:pressed { background: #e8ebf0; }
QPushButton#Primary {
    background: #2f6feb; border: 1px solid #2f6feb; color: #ffffff; font-weight: 600;
}
QPushButton#Primary:hover { background: #2a63d4; }
QPushButton#Danger { color: #c0392b; }
QPushButton#Danger:hover { background: #fdecea; border-color: #f5b7b1; }
QPushButton#Link {
    border: none; background: transparent; color: #2f6feb; padding: 2px 4px;
}
QPushButton#Link:hover { text-decoration: underline; }
QPushButton#Chip {
    border: 1px solid #e5e7eb; background: #ffffff; border-radius: 11px;
    padding: 2px 10px; color: #4b5563; font-size: 9pt;
}
QPushButton#Chip:checked { background: #eaf1ff; border-color: #bcd3ff; color: #2f6feb; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #d3d7de; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #bcc2cc; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: #d3d7de; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QMenu { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background: #eaf1ff; }

QToolTip {
    background: #1f2328; color: #ffffff; border: none; padding: 4px 8px; border-radius: 4px;
}
#StatusPill {
    border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600;
}

QDialog, QMessageBox {
    background: #ffffff;
}
QMessageBox QLabel {
    color: #1f2328;
    background: transparent;
}
QDialog QLabel {
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
"""