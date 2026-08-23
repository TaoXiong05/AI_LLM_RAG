"""轻量测试：验证从模型回答解析引用编号并选出被引用片段。

项目未引入 pytest，用 assert + 直接运行的方式做冒烟验证。运行：
    python tests/test_citation_selection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document

from backend.rag_chain import parse_cited_indices, select_cited_chunks


def make_chunks(n: int) -> list[tuple[Document, float]]:
    return [
        (Document(page_content=f"chunk-{i}", metadata={"source": "s"}), 0.3)
        for i in range(1, n + 1)
    ]


def test_parse_keeps_order_and_deduplicates():
    answer = "先见[2]，再见[1]，最后又见[2]。"
    assert parse_cited_indices(answer) == [2, 1]


def test_parse_ignores_zero_index():
    assert parse_cited_indices("编号[0]无效") == []


def test_parse_empty_when_no_citations():
    answer = "知识库内部找不到相关资料，以下回答为网络搜索答案。"
    assert parse_cited_indices(answer) == []


def test_select_filters_to_cited_chunks():
    chunks = make_chunks(3)
    selected = select_cited_chunks("根据[2]所述...以及[1]补充。", chunks)
    assert [d.page_content for d, _ in selected] == ["chunk-2", "chunk-1"]


def test_select_ignores_out_of_range_and_confabulated_indices():
    chunks = make_chunks(2)
    # [9] 超出了 2 个片段的编号范围，应被忽略
    selected = select_cited_chunks("引用[9]和[1]。", chunks)
    assert [d.page_content for d, _ in selected] == ["chunk-1"]


def test_select_empty_when_no_reference():
    chunks = make_chunks(3)
    answer = "No relevant information was found in the knowledge base. …"
    assert select_cited_chunks(answer, chunks) == []


if __name__ == "__main__":
    test_parse_keeps_order_and_deduplicates()
    test_parse_ignores_zero_index()
    test_parse_empty_when_no_citations()
    test_select_filters_to_cited_chunks()
    test_select_ignores_out_of_range_and_confabulated_indices()
    test_select_empty_when_no_reference()
    print("OK: citation selection tests passed")