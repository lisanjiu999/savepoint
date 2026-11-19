"""树形导航用的图标：折叠箭头 + 分区色块 + 文档色条。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

FOLDER_COLORS = [
    "#c084fc", "#f472b6", "#60a5fa", "#34d399",
    "#fbbf24", "#fb7185", "#22d3ee", "#a78bfa",
]

# 文档条用的颜色，和分区色分开一点，避免看着像同一类
NOTE_COLORS = [
    "#60a5fa", "#f0b27a", "#a3e635", "#f472b6",
    "#22d3ee", "#c084fc", "#facc15", "#fb7185",
]


def _index(name: str, palette: list[str]) -> int:
    return sum(ord(ch) for ch in name) % len(palette)


def color_for(name: str) -> QColor:
    return QColor(FOLDER_COLORS[_index(name, FOLDER_COLORS)])


def _paint_chevron(painter: QPainter, expanded: bool, color: QColor) -> None:
    pen = QPen(color, 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if expanded:
        points = [QPointF(3, 6), QPointF(8, 11.5), QPointF(13, 6)]
    else:
        points = [QPointF(5.5, 3.5), QPointF(11, 9), QPointF(5.5, 14.5)]
    painter.drawPolyline(points)


def folder_icon(name: str, expanded: bool, dark: bool = True) -> QIcon:
    """左边折叠箭头，右边彩色方块，放在一个图标里。"""
    pixmap = QPixmap(36, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    chevron = QColor("#e9edf2") if dark else QColor("#6b7280")
    _paint_chevron(painter, expanded, chevron)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color_for(name))
    painter.drawRoundedRect(QRectF(19, 4, 12, 10), 3, 3)
    painter.end()
    return QIcon(pixmap)


def note_icon(title: str) -> QIcon:
    """文档用一根小色条，区分于分区的方块。"""
    pixmap = QPixmap(36, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(NOTE_COLORS[_index(title or "x", NOTE_COLORS)]))
    painter.drawRoundedRect(QRectF(23, 4, 4, 10), 2, 2)
    painter.end()
    return QIcon(pixmap)