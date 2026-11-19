"""设置窗口。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import autostart
from .hotkey import parse_hotkey


class SettingsDialog(QDialog):
    changed = Signal()

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.data_dir_edit = QLineEdit(str(config.DATA_DIR))
        self.data_dir_edit.setReadOnly(True)
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.addWidget(self.data_dir_edit, 1)
        browse = QPushButton("更改…")
        browse.clicked.connect(self._pick_dir)
        dir_row.addWidget(browse)
        form.addRow("数据目录", dir_row)
        dir_hint = QLabel("改动后需要重启程序才生效；数据和程序是分开的。")
        dir_hint.setObjectName("Muted")
        form.addRow("", dir_hint)

        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(0, 100)
        self.backup_keep.setValue(config.backup_keep())
        self.backup_keep.setSuffix(" 份")
        form.addRow("备份保留", self.backup_keep)

        self.backup_interval = QSpinBox()
        self.backup_interval.setRange(0, 168)
        self.backup_interval.setValue(config.backup_interval_hours())
        self.backup_interval.setSuffix(" 小时")
        form.addRow("备份间隔", self.backup_interval)

        self.clipboard_seconds = QSpinBox()
        self.clipboard_seconds.setRange(0, 600)
        self.clipboard_seconds.setValue(config.clipboard_clear_seconds())
        self.clipboard_seconds.setSuffix(" 秒")
        self.clipboard_seconds.setSpecialValueText("不自动清空")
        form.addRow("剪贴板清空", self.clipboard_seconds)

        self.hotkey_edit = QLineEdit(config.get_setting("hotkey"))
        self.hotkey_edit.setPlaceholderText("Ctrl+Alt+N")
        form.addRow("全局热键", self.hotkey_edit)

        self.tray_enabled = QCheckBox("在系统托盘显示图标")
        self.tray_enabled.setChecked(config.get_bool("tray_enabled", True))
        form.addRow("", self.tray_enabled)

        self.close_to_tray = QCheckBox("关闭窗口时最小化到托盘，而不是退出")
        self.close_to_tray.setChecked(config.get_bool("close_to_tray", True))
        form.addRow("", self.close_to_tray)

        self.autostart_check = QCheckBox("开机自动启动")
        self.autostart_check.setChecked(autostart.is_enabled())
        form.addRow("", self.autostart_check)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    # ---------------- 交互 ----------------

    def _pick_dir(self) -> None:
        start = self.data_dir_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择数据目录", start)
        if folder:
            self.data_dir_edit.setText(folder.replace("/", "\\"))

    def _save(self) -> None:
        hotkey = self.hotkey_edit.text().strip()
        if hotkey and parse_hotkey(hotkey) is None:
            QMessageBox.warning(
                self, "热键无效", "格式应为 Ctrl+Alt+N 这类组合，键只支持字母、数字、F1-F24。"
            )
            return

        new_dir = self.data_dir_edit.text().strip()
        config.save_settings(
            {
                "data_dir": "" if Path(new_dir) == config.default_data_dir() else new_dir,
                "backup_keep": str(self.backup_keep.value()),
                "backup_interval_hours": str(self.backup_interval.value()),
                "clipboard_clear_seconds": str(self.clipboard_seconds.value()),
                "hotkey": hotkey or "Ctrl+Alt+N",
                "tray_enabled": "1" if self.tray_enabled.isChecked() else "0",
                "close_to_tray": "1" if self.close_to_tray.isChecked() else "0",
            }
        )

        if self.autostart_check.isChecked() != autostart.is_enabled():
            if not autostart.set_enabled(self.autostart_check.isChecked()):
                QMessageBox.warning(self, "开机自启", "写入注册表失败，可能被安全软件拦截。")

        dir_changed = Path(new_dir) != Path(str(config.DATA_DIR))
        self.changed.emit()
        if dir_changed:
            QMessageBox.information(
                self, "数据目录已保存", "重启程序后，新的数据目录才会生效。"
            )
        self.accept()