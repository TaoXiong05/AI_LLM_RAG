"""把解析出的文本切片成带 metadata 的 LangChain Document。"""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.parser import ParsedDocument

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


def get_splitter(
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def chunk_document(
    parsed: ParsedDocument,
    splitter: RecursiveCharacterTextSplitter | None = None,
) -> list[Document]:
    splitter = splitter or get_splitter()
    pieces = splitter.split_text(parsed.text)
    return [
        Document(
            page_content=piece,
            metadata={"source": parsed.source, "chunk_index": i},
        )
        for i, piece in enumerate(pieces)
    ]
