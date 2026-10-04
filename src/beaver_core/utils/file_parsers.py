"""Text extraction for the document formats users can upload.

Deliberately lightweight: each format is handled by a small pure-Python library
rather than the heavyweight MinerU/Docling pipeline in ``beaver_core.models.parser``
(which is optional and not wired in). A missing optional dependency surfaces as
a readable ``ValidationError`` naming the package to install.

Every parser returns a list of pages so the caller can keep ``page_idx``
meaningful in the vector store: real pages for PDF/PPTX, one page for a
document that has no pagination, one page per sheet for spreadsheets.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Callable, Dict, List

from .exceptions import ValidationError

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".log"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
LEGACY_DOC_SUFFIXES = {".doc"}
XLSX_SUFFIXES = {".xlsx", ".xlsm"}
XLS_SUFFIXES = {".xls"}
CSV_SUFFIXES = {".csv", ".tsv"}
PPTX_SUFFIXES = {".pptx"}

SUPPORTED_SUFFIXES = (
    TEXT_SUFFIXES | PDF_SUFFIXES | DOCX_SUFFIXES | LEGACY_DOC_SUFFIXES
    | XLSX_SUFFIXES | XLS_SUFFIXES | CSV_SUFFIXES | PPTX_SUFFIXES
)

# Shown to the user when they upload a format we cannot read.
SUPPORTED_HINT = (
    "支持 .md / .txt / .pdf / .docx / .xlsx / .xls / .csv / .pptx；"
    "旧版 .doc 请先另存为 .docx"
)

_MAX_CELL_CHARS = 2000


def _require(module_name: str, package: str):
    try:
        return __import__(module_name)
    except ImportError:
        raise ValidationError(
            f"读取该格式需要安装 {package}：pip install {package}", field="path"
        )


def _read_text(path: Path) -> str:
    """Read a text file, tolerating the encodings Windows tools produce."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _rows_to_text(rows: List[List[str]], header: str | None = None) -> str:
    lines = []
    if header:
        lines.append(f"## {header}")
    for row in rows:
        cells = [
            str(cell).replace("\n", " ").strip()[:_MAX_CELL_CHARS]
            for cell in row
        ]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


# --- individual formats -----------------------------------------------------

def _parse_text(path: Path) -> List[str]:
    return [_read_text(path)]


def _parse_pdf(path: Path) -> List[str]:
    pypdf = _require("pypdf", "pypdf")
    reader = pypdf.PdfReader(str(path))
    pages: List[str] = []
    for index, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001 - one bad page must not kill the doc
            logger.warning("failed to extract page %d of %s: %s", index, path.name, e)
            text = ""
        pages.append(text.strip())
    if not any(pages):
        raise ValidationError(
            "未能从 PDF 中提取到文本，可能是扫描件（图片型 PDF）。请先做 OCR 或改用可复制文本的版本。",
            field="path",
        )
    return pages


def _parse_docx(path: Path) -> List[str]:
    docx = _require("docx", "python-docx")
    document = docx.Document(str(path))
    parts: List[str] = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    for table in document.tables:
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        rendered = _rows_to_text(rows)
        if rendered:
            parts.append(rendered)
    return ["\n".join(parts)]


def _parse_legacy_doc(path: Path) -> List[str]:
    # The old binary .doc container is not readable by python-docx; a pure-Python
    # reader does not exist. Tell the user exactly what to do instead of failing
    # with an obscure parse error.
    raise ValidationError(
        "不支持旧版 .doc 格式，请在 Word 中「另存为」.docx 后重新上传", field="path"
    )


def _parse_xlsx(path: Path) -> List[str]:
    openpyxl = _require("openpyxl", "openpyxl")
    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    pages: List[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if cell is None else str(cell) for cell in row])
            rendered = _rows_to_text(rows, header=f"Sheet: {sheet.title}")
            pages.append(rendered)
    finally:
        workbook.close()
    return pages


def _parse_xls(path: Path) -> List[str]:
    xlrd = _require("xlrd", "xlrd")
    workbook = xlrd.open_workbook(str(path))
    pages: List[str] = []
    for sheet in workbook.sheets():
        rows = [
            [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
        pages.append(_rows_to_text(rows, header=f"Sheet: {sheet.name}"))
    return pages


def _parse_csv(path: Path) -> List[str]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = _read_text(path)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return [_rows_to_text(rows)]


def _parse_pptx(path: Path) -> List[str]:
    pptx = _require("pptx", "python-pptx")
    presentation = pptx.Presentation(str(path))
    pages: List[str] = []
    for index, slide in enumerate(presentation.slides, 1):
        parts: List[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
        pages.append(f"## Slide {index}\n" + "\n".join(parts) if parts else "")
    return pages


_PARSERS: Dict[str, Callable[[Path], List[str]]] = {}
for suffix in TEXT_SUFFIXES:
    _PARSERS[suffix] = _parse_text
for suffix in PDF_SUFFIXES:
    _PARSERS[suffix] = _parse_pdf
for suffix in DOCX_SUFFIXES:
    _PARSERS[suffix] = _parse_docx
for suffix in LEGACY_DOC_SUFFIXES:
    _PARSERS[suffix] = _parse_legacy_doc
for suffix in XLSX_SUFFIXES:
    _PARSERS[suffix] = _parse_xlsx
for suffix in XLS_SUFFIXES:
    _PARSERS[suffix] = _parse_xls
for suffix in CSV_SUFFIXES:
    _PARSERS[suffix] = _parse_csv
for suffix in PPTX_SUFFIXES:
    _PARSERS[suffix] = _parse_pptx


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _PARSERS


def extract_pages(path: str | Path) -> List[str]:
    """Extract text page by page. Empty pages are dropped."""
    file_path = Path(path)
    parser = _PARSERS.get(file_path.suffix.lower())
    if parser is None:
        raise ValidationError(
            f"不支持的文件类型：{file_path.suffix or '(无扩展名)'}。{SUPPORTED_HINT}",
            field="path",
        )
    pages = [page for page in parser(file_path) if page and page.strip()]
    if not pages:
        raise ValidationError(f"未能从 {file_path.name} 中提取到文本内容", field="path")
    return pages
