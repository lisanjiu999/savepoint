# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：onedir（不是 onefile）。

onefile 每次启动都要解压到临时目录，冷启动慢且更容被安全软件误报。
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(ROOT, "savepoint", "assets", "app.ico")
VERSION_FILE = os.path.join(ROOT, "scripts", "version_info.txt")
APP_NAME = "SavePoint"

# 只保留真正用到的模块，把体积压下来
EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "doctest",
    "lib2to3",
    "test",
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "torch",
    "IPython",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DAnimation",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSpatialAudio",
]

a = Analysis(
    [os.path.join(ROOT, "scripts", "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "savepoint", "assets"), "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 会显著提高杀软误报率
    console=False,
    disable_windowed_traceback=False,
    icon=ICON,
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)