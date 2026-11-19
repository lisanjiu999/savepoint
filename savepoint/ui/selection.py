"""选中项的动态彩色描边。

一个全局定时器推进色相，列表用委托在选中项上画彩色圆角框，
卡片类的控件（项目卡片）由主窗口定时刷新边框颜色。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

_phase = 0.0
_timer: QTimer | None = None
_views: list = []


def glow_color(offset: float = 0.0) -> QColor:
    hue = int(((_phase + offset) % 1.0) * 360)
    return QColor.fromHsv(hue, 205, 255)


def ensure_animating(view=None) -> None:
    """注册需要重绘的视图，并按需启动全局动画定时器。"""
    global _timer
    if view is not None and all(view is not item for item in _views):
        _views.append(view)
    if _timer is None:
        _timer = QTimer()
        _timer.setInterval(60)
        _timer.timeout.connect(_tick)
        _timer.start()


def _tick() -> None:
    global _phase
    _phase = (_phase + 0.012) % 1.0
    alive = []
    for view in _views:
        try:
            view.viewport().update()
            alive.append(view)
        except RuntimeError:  # 视图已销毁
            continue
    _views[:] = alive


class GlowDelegate(QStyledItemDelegate):
    """在选中项上叠加一圈流动的彩色边框。"""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: ANN001 - Qt 签名
        super().paint(painter, option, index)
        if not (option.state & QStyle.StateFlag.State_Selected):
            return
        rect = option.rect.adjusted(1, 1, -1, -1)
        pen = QPen(glow_color(), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 6, 6)
        painter.restore()