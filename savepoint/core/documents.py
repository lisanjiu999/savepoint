"""文档入库：把本地文件存进项目，并尽力提取纯文本。

设计取舍：
* PDF 用 pypdf（纯 Python，体积小）。
* docx / pptx / xlsx 本身就是 zip + XML，这里用标准库 zipfile + ElementTree 解析，
  避免为此把 lxml 打进安装包。解析失败不影响文件本身被保存。
* 老式二进制格式（.doc / .xls / .ppt）无法在不引入重型依赖的前提下解析，
  只保存文件，并明确告诉用户「存好了，但没提取文本」。
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from .. import config

# 允许拖进来的文档类型
DOC_SUFFIXES = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".doc": "Word",
    ".pptx": "PPT",
    ".ppt": "PPT",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".txt": "文本",
    ".md": "Markdown",
    ".csv": "CSV",
    ".json": "JSON",
    ".log": "日志",
    ".xml": "XML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".ini": "配置",
    ".py": "代码",
    ".js": "代码",
    ".ts": "代码",
    ".html": "网页",
    ".htm": "网页",
    ".sql": "SQL",
}

# 这些老格式只能保存，不能提取文本
LEGACY_BINARY = {".doc", ".xls", ".ppt"}

MAX_TEXT_CHARS = 200_000
MAX_PDF_PAGES = 300
MAX_STORE_BYTES = 200 * 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class DocumentError(Exception):
    """文档无法读取或保存。"""


def is_document(path: Path) -> bool:
    return path.suffix.lower() in DOC_SUFFIXES


# 按后缀自动归类：用户不用手动整理，拖进来就归位
TYPE_GROUPS: list[tuple[str, set[str]]] = [
    ("Word", {".docx", ".doc"}),
    ("PDF", {".pdf"}),
    ("Excel", {".xlsx", ".xls"}),
    ("PPT", {".pptx", ".ppt"}),
    ("Markdown", {".md"}),
    ("文本", {".txt", ".csv", ".json", ".log", ".xml", ".yml", ".yaml", ".ini"}),
    ("代码", {".py", ".js", ".ts", ".html", ".htm", ".sql"}),
]
OTHER_GROUP = "其他"

# 分组顺序固定，界面上不会跳来跳去
TYPE_ORDER = [name for name, _suffixes in TYPE_GROUPS] + [OTHER_GROUP]


def type_group_of(suffix: str) -> str:
    """把一个后缀映射到类型分组。"""
    lowered = (suffix or "").lower()
    for name, suffixes in TYPE_GROUPS:
        if lowered in suffixes:
            return name
    return OTHER_GROUP


def suffixes_of_group(group: str) -> list[str]:
    for name, suffixes in TYPE_GROUPS:
        if name == group:
            return sorted(suffixes)
    return []


def kind_of(suffix: str) -> str:
    return DOC_SUFFIXES.get(suffix.lower(), "文件")


# ---------------- 文本提取 ----------------


def _limit(text: str) -> str:
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS] + "\n…（内容过长，已截断）"
    return text


def _extract_pdf(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "缺少 pypdf，无法提取 PDF 文本（文件仍会保存）"
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - 损坏或加密的 PDF
        return "", f"PDF 打不开：{exc}"
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            return "", "PDF 有密码保护，未提取文本（文件仍会保存）"

    chunks: list[str] = []
    pages = len(reader.pages)
    for index, page in enumerate(reader.pages):
        if index >= MAX_PDF_PAGES:
            chunks.append(f"\n…（共 {pages} 页，只提取了前 {MAX_PDF_PAGES} 页）")
            break
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - 个别页面损坏
            continue
    text = _limit("\n".join(chunks))
    if not text:
        return "", "这个 PDF 可能是扫描件，没有可提取的文字"
    return text, ""


def _extract_docx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        return "", f"docx 解析失败：{exc}"
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return "", f"docx 内容损坏：{exc}"

    lines: list[str] = []
    for paragraph in root.iter(f"{_W}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{_W}t")]
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return _limit("\n".join(lines)), ""


def _extract_pptx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ]
            names.sort(key=lambda item: int(re.findall(r"\d+", item)[0]))
            chunks: list[str] = []
            for index, name in enumerate(names, start=1):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError:
                    continue
                texts = [
                    node.text.strip()
                    for node in root.iter(f"{_A}t")
                    if (node.text or "").strip()
                ]
                if texts:
                    chunks.append(f"【第 {index} 页】\n" + "\n".join(texts))
    except (zipfile.BadZipFile, OSError) as exc:
        return "", f"pptx 解析失败：{exc}"
    text = _limit("\n\n".join(chunks))
    if not text:
        return "", "这份 PPT 里没有可提取的文字"
    return text, ""


def _extract_xlsx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.iter(f"{_S}si"):
                    shared.append(
                        "".join(node.text or "" for node in item.iter(f"{_S}t"))
                    )

            sheets = [
                name
                for name in archive.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            ]
            sheets.sort(key=lambda item: int(re.findall(r"\d+", item)[0]))
            chunks: list[str] = []
            for index, name in enumerate(sheets, start=1):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError:
                    continue
                rows: list[str] = []
                for row in root.iter(f"{_S}row"):
                    cells: list[str] = []
                    for cell in row.iter(f"{_S}c"):
                        kind = cell.get("t")
                        value_node = cell.find(f"{_S}v")
                        value = value_node.text if value_node is not None else ""
                        if kind == "s" and value and value.isdigit():
                            position = int(value)
                            value = shared[position] if position < len(shared) else ""
                        elif kind == "inlineStr":
                            value = "".join(
                                node.text or "" for node in cell.iter(f"{_S}t")
                            )
                        cells.append((value or "").strip())
                    if any(cells):
                        rows.append("\t".join(cells))
                if rows:
                    chunks.append(f"【工作表 {index}】\n" + "\n".join(rows))
    except (zipfile.BadZipFile, OSError) as exc:
        return "", f"xlsx 解析失败：{exc}"
    text = _limit("\n\n".join(chunks))
    if not text:
        return "", "这份表格里没有可提取的文字"
    return text, ""


def _extract_plain(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return _limit(data.decode(encoding)), ""
        except UnicodeDecodeError:
            continue
    return _limit(data.decode("utf-8", errors="replace")), "文件不是 UTF-8，部分字符可能显示为乱码"


def extract_text(path: Path) -> tuple[str, str]:
    """提取纯文本，返回 (文本, 提示)。提取失败不算错误，文件照样能存。"""
    suffix = path.suffix.lower()
    if suffix in LEGACY_BINARY:
        return "", f"{suffix} 是旧版 Office 格式，只保存文件，不提取文本"
    try:
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return _extract_docx(path)
        if suffix == ".pptx":
            return _extract_pptx(path)
        if suffix == ".xlsx":
            return _extract_xlsx(path)
        return _extract_plain(path)
    except Exception as exc:  # noqa: BLE001 - 任何解析异常都不该挡住保存
        return "", f"提取文本时出错：{exc}"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "file"
    return cleaned[:80]


# ---------------- 存储 ----------------


class DocStore:
    def __init__(self, doc_dir: Path | None = None) -> None:
        self.doc_dir = Path(doc_dir or config.DOC_DIR)
        self.doc_dir.mkdir(parents=True, exist_ok=True)

    def abs_path(self, rel: str) -> Path:
        return self.doc_dir / rel

    def save(self, source: Path) -> tuple[str, int, str]:
        """复制文件进文档库，返回 (相对路径, 字节数, sha256)。

        文件平铺存放，分区只是数据库里的一个字段，这样重命名分区不需要移动文件。
        """
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise DocumentError(f"读取失败：{exc}") from exc
        if not data:
            raise DocumentError("文件是空的")
        if len(data) > MAX_STORE_BYTES:
            raise DocumentError(
                f"文件超过 {MAX_STORE_BYTES // 1024 // 1024} MB，没有保存"
            )

        digest = sha256_of(data)
        stamp = datetime.now()
        name = f"{stamp:%Y%m%d-%H%M%S}_{digest[:8]}_{_safe_name(source.name)}"
        rel = name
        target = self.doc_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                target.write_bytes(data)
            except OSError as exc:
                raise DocumentError(f"写入失败：{exc}") from exc
        return rel, len(data), digest

    def remove(self, rel_paths: list[str]) -> None:
        for rel in rel_paths:
            if not rel:
                continue
            path = self.doc_dir / rel
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass