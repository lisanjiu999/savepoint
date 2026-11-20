"""文档提取与入库的测试。"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import zipfile
from pathlib import Path

DOCX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>第一段：接口设计</w:t></w:r></w:p>
    <w:p><w:r><w:t>第二段：数据库表结构</w:t></w:r></w:p>
  </w:body>
</w:document>
"""

PPTX_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody>
    <a:p><a:r><a:t>幻灯片标题</a:t></a:r></a:p>
  </p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>
"""

XLSX_SHARED = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>姓名</t></si><si><t>张三</t></si>
</sst>
"""

XLSX_SHEET = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c></row>
    <row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>42</v></c></row>
  </sheetData>
</worksheet>
"""


def build_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", DOCX_XML)


def build_pptx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", PPTX_XML)


def build_xlsx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", XLSX_SHARED)
        archive.writestr("xl/worksheets/sheet1.xml", XLSX_SHEET)


def build_pdf(path: Path) -> None:
    """不依赖第三方库，手搓一个最小的单页 PDF。"""
    text = "BT /F1 24 Tf 72 720 Td (Hello SavePoint) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = ["%PDF-1.4"]
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(line) + 1 for line in out))
        out.append(f"{index} 0 obj")
        out.append(body)
        out.append("endobj")
    xref_at = sum(len(line) + 1 for line in out)
    out.append("xref")
    out.append(f"0 {len(objects) + 1}")
    out.append("0000000000 65535 f ")
    for offset in offsets:
        out.append(f"{offset:010d} 00000 n ")
    out.append("trailer")
    out.append(f"<< /Size {len(objects) + 1} /Root 1 0 R >>")
    out.append("startxref")
    out.append(str(xref_at))
    out.append("%%EOF")
    path.write_bytes(("\n".join(out) + "\n").encode("latin-1"))