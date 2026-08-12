"""
RAG (检索增强生成) 最小可跑通 demo

流程：
1. 准备一份示例知识库文本，按段落切分成若干 chunk
2. 用百炼 embedding 模型把每个 chunk 转成向量，缓存在内存里
3. 用户提问时，把问题也转成向量，和所有 chunk 向量算余弦相似度
4. 取相似度最高的几个 chunk 拼进 prompt，作为上下文交给对话模型回答

不依赖 faiss / numpy / langchain，纯 Python 实现，方便先看懂原理。
"""
import math

from openai import OpenAI

client = OpenAI(
    base_url="https://ws-wibk6xl3op0zm1sx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)

CHAT_MODEL = "qwen3.8-max"
EMBED_MODEL = "text-embedding-v3"

# 1. 示例知识库：按段落手动切成 chunk
RAW_TEXT = """
RAG（Retrieval-Augmented Generation，检索增强生成）是一种让大语言模型结合外部知识库回答问题的技术。
它的核心思路是：在模型生成回答之前，先从知识库中检索出与问题最相关的内容，再把这些内容作为上下文一起交给模型，从而让回答更准确、更贴合私有数据，并减少模型“胡编乱造”（幻觉）的情况。

RAG 系统通常包含三个步骤：索引（Indexing）、检索（Retrieval）和生成（Generation）。
索引阶段会把文档切分成小块（chunk），并用 embedding 模型把每个 chunk 转换成向量，存入向量数据库。
检索阶段会把用户的问题也转换成向量，通过计算相似度（如余弦相似度）找出最相关的若干个 chunk。
生成阶段则把检索到的 chunk 拼接成上下文，连同用户问题一起交给大语言模型，由模型生成最终答案。

常见的向量数据库有 FAISS、Chroma、Milvus、Pinecone 等，它们负责高效地存储向量并支持快速的相似度检索。
在小规模数据或demo场景下，也可以不使用专门的向量数据库，而是直接用内存中的列表保存向量，用简单的余弦相似度计算完成检索。
"""

def split_into_chunks(text: str) -> list[str]:
    return [p.strip() for p in text.strip().split("\n\n") if p.strip()]


def get_embedding(text: str) -> list[float]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)  # type: ignore
    return resp.data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def build_knowledge_base(text: str) -> list[dict]:
    chunks = split_into_chunks(text)
    return [{"text": chunk, "embedding": get_embedding(chunk)} for chunk in chunks]


def retrieve(question: str, knowledge_base: list[dict], top_k: int = 2) -> list[str]:
    query_embedding = get_embedding(question)
    scored = [
        (cosine_similarity(query_embedding, item["embedding"]), item["text"])
        for item in knowledge_base
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]


def ask(question: str, knowledge_base: list[dict]) -> str:
    context_chunks = retrieve(question, knowledge_base)
    context = "\n\n".join(context_chunks)

    prompt = f"""请只根据下面提供的参考资料回答问题，如果参考资料中没有相关信息，请直接说不知道。

【参考资料】
{context}

【问题】
{question}"""

    print("\n" + "=" * 20 + "检索到的上下文" + "=" * 20)
    for i, chunk in enumerate(context_chunks, 1):
        print(f"[{i}] {chunk}\n")

    response = client.chat.completions.create(  # type: ignore
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": "你是一个严谨的问答助手，只依据用户提供的参考资料回答问题。"},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print("正在构建知识库（embedding 中）...")
    kb = build_knowledge_base(RAW_TEXT)
    print(f"知识库构建完成，共 {len(kb)} 个 chunk。\n")

    question = "RAG 有哪几个步骤？"
    print("问题:", question)

    answer = ask(question, kb)
    print("\n" + "=" * 20 + "回答" + "=" * 20)
    print(answer)
