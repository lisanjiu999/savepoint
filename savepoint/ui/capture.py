"""屏幕区域截图。

覆盖整个虚拟桌面，拖拽选区域，松手回调；Esc 或右键取消。
截图前会把主窗口藏起来，避免把自己拍进去。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

DIM = QColor(0, 0, 0, 110)
ACCENT = QColor(47, 111, 235)


def _virtual_geometry() -> QRect:
    geometry = QRect()
    for screen in QGuiApplication.screens():
        geometry = geometry.united(screen.geometry())
    return geometry


def grab_virtual_desktop() -> QPixmap:
    """把整个虚拟桌面拼成一张图。"""
    geometry = _virtual_geometry()
    screens = QGuiApplication.screens()
    ratio = max((screen.devicePixelRatio() for screen in screens), default=1.0)

    canvas = QPixmap(int(geometry.width() * ratio), int(geometry.height() * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.black)

    painter = QPainter(canvas)
    try:
        for screen in screens:
            shot = screen.grabWindow(0)
            if shot.isNull():
                continue
            area = screen.geometry()
            painter.drawPixmap(
                QRect(
                    area.x() - geometry.x(),
                    area.y() - geometry.y(),
                    area.width(),
                    area.height(),
                ),
                shot,
            )
    finally:
        painter.end()
    return canvas


class ScreenCaptureOverlay(QWidget):
    captured = Signal(QPixmap)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._geometry = _virtual_geometry()
        self.setGeometry(self._geometry)
        self._background = grab_virtual_desktop()

        self._origin = None
        self._current = None
        self._closed = False

    # ---------------- 绘制 ----------------

    def _selection(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._background)
        painter.fillRect(self.rect(), DIM)

        selection = self._selection()
        if not selection.isEmpty():
            # 选中的区域恢复原始亮度
            painter.setClipRect(selection)
            painter.drawPixmap(self.rect(), self._background)
            painter.setClipping(False)

            painter.setPen(QPen(ACCENT, 2))
            painter.drawRect(selection.adjusted(0, 0, -1, -1))

            label = f"{selection.width()} × {selection.height()}"
            metrics = painter.fontMetrics()
            box = metrics.boundingRect(label).adjusted(-8, -4, 8, 4)
            box.moveTopLeft(selection.topLeft() + QPoint(0, -box.height() - 6))
            if box.top() < 0:
                box.moveTopLeft(selection.bottomLeft() + QPoint(0, 6))
            painter.fillRect(box, QColor(31, 35, 40, 220))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(box, Qt.AlignCenter, label)
        else:
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                self.rect(),
                Qt.AlignHCenter | Qt.AlignTop,
                "\n拖动鼠标选择区域　·　Esc 或右键取消",
            )

    # ---------------- 交互 ----------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.RightButton:
            self._cancel()
            return
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        self._current = event.position().toPoint()
        selection = self._selection()
        self._origin = None
        self._current = None
        if selection.width() < 8 or selection.height() < 8:
            self.update()
            return
        self._finish(selection)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() == Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _finish(self, selection: QRect) -> None:
        ratio = self._background.devicePixelRatio()
        device_rect = QRect(
            int(selection.x() * ratio),
            int(selection.y() * ratio),
            int(selection.width() * ratio),
            int(selection.height() * ratio),
        )
        cropped = self._background.copy(device_rect)
        self._closed = True
        self.close()
        self.captured.emit(cropped)

    def _cancel(self) -> None:
        self._closed = True
        self.close()
        self.cancelled.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        # 用 Alt+F4 之类关掉时也要通知调用方恢复窗口
        if not self._closed:
            self._closed = True
            self.cancelled.emit()
        super().closeEvent(event)