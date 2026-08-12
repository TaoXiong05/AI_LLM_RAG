# RAG Demo — Streamlit + PostgreSQL (pgvector) + LangChain

[中文](#中文) | [English](#english)

---

## 中文

一个基于 **Streamlit + PostgreSQL(pgvector)+ LangChain** 搭建的文档问答 RAG(检索增强生成)Demo。上传 PDF / DOCX / TXT 文档,即可基于文档内容提问,回答会标注引用来源。

> ⚠️ 这是一个演示项目,请勿上传涉及隐私、机密或敏感信息的文档。

### 功能特性

- 支持 PDF / DOCX / TXT 多文件上传,自动解析、切片并向量化入库
- 基于 PostgreSQL 的 `pgvector` 扩展做相似度检索,通过 LangChain 的 `PGVector` 接入
- 对话流式输出(打字机效果),回答下方展示命中的参考片段及相似度得分
- 知识库管理:查看已入库文档列表、删除单个文档、清空整个知识库(均有二次确认)
- 界面默认英文,侧边栏一键切换中文
- LLM / Embedding 服务商可配置,默认接入阿里云百炼(OpenAI 兼容接口)

### 技术栈

| 模块 | 组件 |
| --- | --- |
| 前端界面 | Streamlit |
| 向量数据库 | PostgreSQL + pgvector（示例使用 [Neon](https://neon.tech) 托管实例） |
| RAG 编排 | LangChain（`langchain-core` / `langchain-text-splitters` / `langchain-openai` / `langchain-postgres`） |
| 对话 / Embedding 模型 | 阿里云百炼（OpenAI 兼容接口，`qwen3.8-max` + `text-embedding-v3`，可替换为任意 OpenAI 兼容服务） |
| 文档解析 | `pypdf`（PDF）、`python-docx`（DOCX） |

### 项目结构

```
AI_LLM_RAG/
├── app.py                  # Streamlit 界面入口
├── config.py                # 配置：读取 .env / Streamlit Secrets
├── i18n.py                  # 中英文界面文案
├── requirements.txt
├── .env.example              # 环境变量模板
├── .python-version           # 部署到 Streamlit Cloud 用的 Python 版本
└── backend/
    ├── parser.py             # PDF/DOCX/TXT 文本解析
    ├── chunker.py             # 文本切片（RecursiveCharacterTextSplitter，chunk_size=500, overlap=50）
    ├── db.py                  # Postgres/pgvector 读写、知识库管理
    └── rag_chain.py           # 检索 + 拼 Prompt + 流式生成回答
```

### 本地运行

**环境要求**：Python 3.11+、一个已启用 `pgvector` 扩展的 PostgreSQL 实例（本地或云托管均可，如 [Neon](https://neon.tech)）。

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量

   ```bash
   cp .env.example .env
   ```

   编辑 `.env`，填入你的 Postgres 连接信息（`PG_HOST` / `PG_PORT` / `PG_DATABASE` / `PG_USER` / `PG_PASSWORD`）和 LLM/Embedding 的 API Key（`OPENAI_API_KEY`）。其余字段有默认值，可以不改。

3. 启动应用

   ```bash
   streamlit run app.py
   ```

   浏览器打开 `http://localhost:8501`，在侧边栏上传文档、点击「处理并构建向量库」，然后就可以在下方提问。

### 部署到 Streamlit Community Cloud

1. 把代码推到 GitHub 仓库。
2. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录，New app，选择仓库 / 分支，入口文件填 `app.py`。
3. 在 Advanced settings 的 Secrets 里，按 `.env.example` 的字段，以 TOML 格式（`KEY = "value"`）填入所有配置项。
4. 点击 Deploy。`config.py` 会自动把 Secrets 合并进环境变量，无需改代码。

> Streamlit Community Cloud 目前对 Python 3.14 支持还不完善，仓库里的 `.python-version` 固定使用 3.12。

### 已知限制

- 文件上传控件（拖拽区域、"Browse files" 等文案）是 Streamlit 内置组件自带的英文文案，应用层无法翻译。
- 知识库为单一全局集合（`COLLECTION_NAME`），不区分用户/会话；如需多租户需要自行扩展。
- 演示项目未做鉴权，请勿在公网部署中存放真实隐私数据。

---

## English

A document Q&A **RAG (Retrieval-Augmented Generation)** demo built with **Streamlit + PostgreSQL (pgvector) + LangChain**. Upload PDF / DOCX / TXT files, then ask questions grounded in their content — answers come with cited sources.

> ⚠️ This is a demo project. Please do not upload documents containing private, confidential, or otherwise sensitive information.

### Features

- Multi-file upload for PDF / DOCX / TXT, with automatic parsing, chunking, and vectorization
- Similarity search backed by PostgreSQL's `pgvector` extension, via LangChain's `PGVector`
- Streaming chat responses, with retrieved source chunks and similarity scores shown below each answer
- Knowledge base management: list ingested documents, delete a single document, or clear the whole knowledge base (each with a confirmation step)
- English UI by default, with a one-click toggle to Chinese in the sidebar
- Configurable LLM / embedding provider — defaults to Alibaba Cloud Bailian (OpenAI-compatible API)

### Tech Stack

| Layer | Component |
| --- | --- |
| Frontend | Streamlit |
| Vector store | PostgreSQL + pgvector (demo uses a [Neon](https://neon.tech)-hosted instance) |
| RAG orchestration | LangChain (`langchain-core` / `langchain-text-splitters` / `langchain-openai` / `langchain-postgres`) |
| Chat / embedding model | Alibaba Cloud Bailian (OpenAI-compatible API, `qwen3.8-max` + `text-embedding-v3`; swappable for any OpenAI-compatible service) |
| Document parsing | `pypdf` (PDF), `python-docx` (DOCX) |

### Project Structure

```
AI_LLM_RAG/
├── app.py                  # Streamlit UI entry point
├── config.py                # Config: reads .env / Streamlit Secrets
├── i18n.py                  # EN/ZH UI strings
├── requirements.txt
├── .env.example              # Environment variable template
├── .python-version           # Python version pin for Streamlit Cloud
└── backend/
    ├── parser.py             # PDF/DOCX/TXT text extraction
    ├── chunker.py             # Text chunking (RecursiveCharacterTextSplitter, chunk_size=500, overlap=50)
    ├── db.py                  # Postgres/pgvector I/O, knowledge base management
    └── rag_chain.py           # Retrieval + prompt assembly + streaming generation
```

### Run Locally

**Requirements**: Python 3.11+, a PostgreSQL instance with the `pgvector` extension enabled (local or hosted, e.g. [Neon](https://neon.tech)).

1. Install dependencies

   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your Postgres connection details (`PG_HOST` / `PG_PORT` / `PG_DATABASE` / `PG_USER` / `PG_PASSWORD`) and your LLM/embedding API key (`OPENAI_API_KEY`). Everything else has a working default.

3. Start the app

   ```bash
   streamlit run app.py
   ```

   Open `http://localhost:8501`, upload documents in the sidebar, click "Process & Build Vector Store", then ask questions below.

### Deploy to Streamlit Community Cloud

1. Push the code to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, click New app, and pick the repo/branch with `app.py` as the entry point.
3. Under Advanced settings → Secrets, paste all the values from `.env.example` in TOML format (`KEY = "value"`).
4. Click Deploy. `config.py` automatically merges Secrets into environment variables — no code changes needed.

> Streamlit Community Cloud doesn't fully support Python 3.14 yet, so `.python-version` pins the deployment to 3.12.

### Known Limitations

- The file uploader widget's built-in text (drag-and-drop area, "Browse files", etc.) is Streamlit's own English UI chrome and cannot be translated at the app level.
- The knowledge base is a single global collection (`COLLECTION_NAME`) — no per-user/session isolation; extend it yourself if you need multi-tenancy.
- This demo has no authentication layer — do not store real private data in a publicly deployed instance.
