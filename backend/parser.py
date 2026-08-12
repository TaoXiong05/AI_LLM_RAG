"""把上传的 PDF / Docx / Txt 文件解析成纯文本。"""
import io
from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class UnsupportedFileTypeError(ValueError):
    pass


@dataclass
class ParsedDocument:
    source: str
    text: str


def parse_pdf(file_bytes: bytes, filename: str) -> ParsedDocument:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return ParsedDocument(source=filename, text=text)


def parse_docx(file_bytes: bytes, filename: str) -> ParsedDocument:
    doc = DocxDocument(io.BytesIO(file_bytes))
    text = "\n".join(p.text for p in doc.paragraphs)
    return ParsedDocument(source=filename, text=text)


def parse_txt(file_bytes: bytes, filename: str) -> ParsedDocument:
    text = file_bytes.decode("utf-8", errors="replace")
    return ParsedDocument(source=filename, text=text)


def parse_file(uploaded_file) -> ParsedDocument:
    """uploaded_file 只需鸭子类型满足 .name / .getvalue()（Streamlit UploadedFile 即可）。"""
    filename = uploaded_file.name
    suffix = Path(filename).suffix.lower()
    file_bytes = uploaded_file.getvalue()

    if suffix == ".pdf":
        return parse_pdf(file_bytes, filename)
    if suffix == ".docx":
        return parse_docx(file_bytes, filename)
    if suffix == ".txt":
        return parse_txt(file_bytes, filename)

    raise UnsupportedFileTypeError(f"不支持的文件类型：{suffix}")
