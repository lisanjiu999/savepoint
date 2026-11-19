"""单实例互斥 + 唤起已有窗口。

之前用 QSharedMemory 只做了"发现已有实例就弹提示"，第二个实例启动后
自己退出，第一个实例如果被最小化到托盘，用户就再也找不到窗口了。

现在改成 QLocalServer：第二个实例连上第一个，发一条 show 指令，
第一个实例收到后把窗口显示出来并置前，然后第二个实例安静退出。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SHOW_MESSAGE = b"show"
CONNECT_TIMEOUT_MS = 500


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        self._name = f"savepoint-{digest}"
        self._server: QLocalServer | None = None
        self._log = logging.getLogger("savepoint.single")

    @property
    def server_name(self) -> str:
        return self._name

    # ---------------- 第二个实例 ----------------

    def notify_existing(self) -> bool:
        """唤起已在运行的实例。成功返回 True。"""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            return False
        socket.write(SHOW_MESSAGE)
        socket.flush()
        socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        socket.disconnectFromServer()
        socket.waitForDisconnected(CONNECT_TIMEOUT_MS)
        return True

    # ---------------- 第一个实例 ----------------

    def listen(self) -> bool:
        # 上次异常退出可能留下同名服务，先清掉
        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._name):
            self._log.warning("单实例监听失败：%s", server.errorString())
            return False
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.readyRead.connect(lambda conn=connection: self._on_ready(conn))
            connection.disconnected.connect(connection.deleteLater)
            # 数据可能在连上 readyRead 之前就到了
            if connection.bytesAvailable():
                self._on_ready(connection)

    def _on_ready(self, connection) -> None:  # noqa: ANN001 - Qt 回调
        payload = bytes(connection.readAll()).strip()
        if payload == SHOW_MESSAGE:
            self.activated.emit()
        connection.disconnectFromServer()