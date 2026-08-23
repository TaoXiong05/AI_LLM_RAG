"""轻量测试：验证检索结果的距离阈值过滤逻辑。

项目未引入 pytest，本文件用 assert + 直接运行的方式做冒烟验证。运行：
    python tests/test_retrieval_filter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document

from backend.db import _below_max_distance


def test_filters_out_distant_chunks():
    docs = [
        (Document(page_content="a", metadata={"source": "s"}), 0.15),
        (Document(page_content="b", metadata={"source": "s"}), 0.72),
        (Document(page_content="c", metadata={"source": "s"}), 0.91),
    ]
    kept = _below_max_distance(docs, max_distance=0.8)
    assert [d.page_content for d, _ in kept] == ["a", "b"], kept


def test_threshold_is_exclusive():
    # 距离恰好等于阈值（0.8）的片段应被过滤掉（score < max_distance）
    docs = [(Document(page_content="edge"), 0.8)]
    assert _below_max_distance(docs, max_distance=0.8) == []


def test_keeps_all_when_threshold_unlimited():
    docs = [(Document(page_content="a"), 0.99), (Document(page_content="b"), 1.1)]
    assert len(_below_max_distance(docs, max_distance=2.0)) == 2


def test_empty_input():
    assert _below_max_distance([], 0.8) == []


if __name__ == "__main__":
    test_filters_out_distant_chunks()
    test_threshold_is_exclusive()
    test_keeps_all_when_threshold_unlimited()
    test_empty_input()
    print("OK: retrieval filter tests passed")