# RAG Demo — Streamlit + PostgreSQL (pgvector) + LangChain

[中文](#中文) | [English](#english)

---

## 中文

一个基于 **Streamlit + PostgreSQL(pgvector)+ LangChain** 搭建的文档问答 RAG(检索增强生成)Demo。上传 PDF / DOCX / TXT / 图片文件,即可基于文档内容提问,回答会标注引用来源。同一个知识库还驱动一个**全自动邮件客服**:把问题发到 `support@taoxiong.site`,几分钟内就会收到基于知识库的回信。

> ⚠️ 这是一个演示项目,请勿上传涉及隐私、机密或敏感信息的文档。

### 功能特性

**网页问答**

- 支持 PDF / DOCX / TXT / 图片(png/jpg/webp/bmp)多文件上传,自动解析、切片并向量化入库
- 扫描版 PDF 页面、DOCX 内嵌图片和纯图片通过视觉大模型 OCR 提取文字(独立的 `OCR_MODEL`)
- 基于 PostgreSQL 的 `pgvector` 扩展做相似度检索,通过 LangChain 的 `PGVector` 接入;低于相关度阈值(`RETRIEVAL_MAX_DISTANCE`)的片段不作为引用展示
- 对话流式输出(打字机效果),回答下方展示命中的参考片段及相似度得分
- 知识库管理:查看已入库文档列表、删除单个文档、清空整个知识库(需输入密码 `CLEAR_KB_PASSWORD`)
- 按 IP 限流,防止公开站点被刷(`RATE_LIMIT_*`)
- 页面顶部用两张卡片分别介绍「在本页面提问」和「AI 邮件客服」两种使用方式,窄屏下自动堆叠
- 界面默认英文,侧边栏一键切换中文
- LLM / Embedding 服务商可配置,任何 OpenAI 兼容接口均可(本地默认阿里云百炼,线上部署使用 Google Gemini)

**邮件自动回复**

- 后台 worker(`python -m backend.mail_worker`)轮询 Resend 收到的邮件,只处理发给 `support@taoxiong.site` 的来信
- 规则预检:过滤自动回复/群发邮件、伪造发件人、仅含附件的邮件,并识别中英文
- LLM 分拣来信(问题 / 垃圾广告 / 辱骂 / 提示词注入 / 其他),把邮件拆成最多 `MAIL_MAX_QUESTIONS` 个独立问题;只写了关键词或主题(如 “GIT INFOS”)也会被当作信息请求
- 每个问题单独检索知识库并作答,回答完整、分段,正文带 `[1]` 式引用编号,末尾列出来源文件(如 `[1][3] faq.pdf, [2] guide.docx`);知识库查不到的问题会如实说明,不会用通用知识编造
- 回信同时包含 HTML 和纯文本两个版本
- 感谢、问候等没有识别出问题的来信,会收到一封说明「如何提问」的提示邮件;垃圾广告和辱骂保持静默
- 额度保护:每个发件人每日上限(`MAIL_PER_SENDER_DAILY_LIMIT`)、全系统每日上限(`MAIL_DAILY_GLOBAL_LIMIT`),超出时每人当天只收到一次提示;另有硬上限 `MAIL_DAILY_HARD_CAP`,达到后连提示也不再发,保证不超出 Resend 每日配额
- `email_log` 表负责去重、计数和失败重试(`MAIL_MAX_RETRIES`);首次启动只处理最近 `MAIL_MAX_AGE_HOURS` 小时内的邮件
- 设计文档:[`docs/superpowers/specs/2026-09-29-email-auto-reply-design.md`](docs/superpowers/specs/2026-09-29-email-auto-reply-design.md)

### 技术栈

| 模块 | 组件 |
| --- | --- |
| 前端界面 | Streamlit |
| 向量数据库 | PostgreSQL + pgvector(本地用 Docker `pgvector/pgvector:pg16`,也可用 [Neon](https://neon.tech) 等托管实例) |
| RAG 编排 | LangChain(`langchain-core` / `langchain-text-splitters` / `langchain-openai` / `langchain-postgres`) |
| 对话 / Embedding / OCR 模型 | 任意 OpenAI 兼容接口:本地默认阿里云百炼(`qwen3.8-max` + `text-embedding-v3`),线上使用 Google Gemini |
| 文档解析 | `pypdf`、`PyMuPDF`(PDF)、`python-docx`(DOCX) |
| 邮件收发 | [Resend](https://resend.com)(REST API) |
| 部署 | Docker Compose + Caddy,GitHub Actions 自动部署到 ARM64 VM |

### 项目结构

```
AI_LLM_RAG/
├── app.py                    # Streamlit 界面入口
├── config.py                 # 配置：读取 .env / Streamlit Secrets
├── i18n.py                   # 中英文界面文案
├── requirements.txt
├── .env.example              # 环境变量模板
├── Dockerfile
├── docker-compose.local.yml  # 本地开发数据库（Postgres + pgvector）
├── DEPLOYMENT.md             # VM 部署说明
├── backend/
│   ├── parser.py             # PDF/DOCX/TXT/图片 文本解析
│   ├── ocr.py                # 视觉大模型 OCR
│   ├── chunker.py            # 文本切片（RecursiveCharacterTextSplitter，chunk_size=500, overlap=50）
│   ├── db.py                 # Postgres/pgvector 读写、知识库管理
│   ├── rag_chain.py          # 检索 + 拼 Prompt + 流式生成回答
│   ├── rate_limiter.py       # 按 IP 的滑动窗口限流
│   ├── resend_client.py      # Resend 收发信 API
│   ├── mail_rules.py         # 邮件规则：正文提取、自动邮件/伪造识别、预检
│   ├── mail_templates.py     # 回复模板（中/英）与 HTML/纯文本正文拼装
│   ├── mail_log.py           # email_log 表：去重、每日限额、重试
│   ├── mail_analyzer.py      # LLM 分拣拆题、逐题基于知识库作答
│   └── mail_worker.py        # 邮件 worker 入口：python -m backend.mail_worker
├── deploy/                   # 线上 docker-compose.yml 与 Caddy 站点配置
├── .github/workflows/        # deploy.yml（自动部署）、diagnose-mail.yml（邮件 worker 诊断）
├── docs/superpowers/         # 设计文档与实施计划
└── tests/                    # 轻量测试脚本
```

### 本地运行

**环境要求**：Python 3.11+、一个已启用 `pgvector` 扩展的 PostgreSQL 实例。

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量

   ```bash
   cp .env.example .env
   ```

   编辑 `.env`，填入 Postgres 连接信息（`PG_HOST` / `PG_PORT` / `PG_DATABASE` / `PG_USER` / `PG_PASSWORD`）和 LLM/Embedding 的 API Key（`OPENAI_API_KEY`）。其余字段有默认值，可以不改。

   > `PG_HOST` 请用 `127.0.0.1` 而不是 `localhost`：Windows 上 `localhost` 会先尝试 IPv6（`::1`），连接 WSL/Docker 里的 Postgres 时要等两三分钟超时才回退。

3. 启动本地数据库（如已有 Postgres 可跳过）

   ```bash
   docker compose -f docker-compose.local.yml up -d
   ```

4. 启动应用

   ```bash
   python -m streamlit run app.py
   ```

   浏览器打开 `http://localhost:8501`，在侧边栏上传文档、点击「处理并构建向量库」，然后就可以在下方提问。

5. （可选）启动邮件 worker：在 `.env` 中填入 Full access 的 `RESEND_API_KEY`，然后运行

   ```bash
   python -m backend.mail_worker
   ```

   `RESEND_API_KEY` 留空时 worker 空转，不处理邮件。

### 运行测试

测试是不依赖 pytest 的独立脚本（邮件相关测试使用 SQLite 内存库和假的 Resend/LLM），逐个运行即可，例如：

```bash
python tests/test_mail_worker.py
```

### 部署

- **VM（线上环境）**：Docker Compose 运行 app、mail worker 和 Postgres，Caddy 作为唯一公网入口，推送到 `master` 后由 GitHub Actions 自动构建 ARM64 镜像并部署。所需的 GitHub 环境变量、DNS 配置和排障方法见 [DEPLOYMENT.md](DEPLOYMENT.md)。没有 SSH 权限时，可手动运行 **Diagnose mail worker** workflow 查看 worker 状态。
- **Streamlit Community Cloud**（仅网页问答，不含邮件 worker）：在 [share.streamlit.io](https://share.streamlit.io) 新建应用，入口文件填 `app.py`，在 Secrets 里按 `.env.example` 的字段以 TOML 格式（`KEY = "value"`）填写配置即可；`config.py` 会自动把 Secrets 合并进环境变量。仓库里的 `.python-version` 固定使用 Python 3.12。

### 已知限制

- 文件上传控件（拖拽区域、"Browse files" 等文案）是 Streamlit 内置组件自带的英文文案，应用层无法翻译。
- 知识库为单一全局集合（`COLLECTION_NAME`），不区分用户/会话；如需多租户需要自行扩展。更换 Embedding 模型时需要使用新的 `COLLECTION_NAME` 并重新入库。
- 邮件客服暂不处理附件，问题需写在邮件正文中。
- 演示项目未做用户鉴权，请勿在公网部署中存放真实隐私数据。

---

## English

A document Q&A **RAG (Retrieval-Augmented Generation)** demo built with **Streamlit + PostgreSQL (pgvector) + LangChain**. Upload PDF / DOCX / TXT / image files, then ask questions grounded in their content — answers come with cited sources. The same knowledge base also powers a **fully automated email support desk**: send a question to `support@taoxiong.site` and get a knowledge-base-grounded reply within minutes.

> ⚠️ This is a demo project. Please do not upload documents containing private, confidential, or otherwise sensitive information.

### Features

**Web Q&A**

- Multi-file upload for PDF / DOCX / TXT / images (png/jpg/webp/bmp), with automatic parsing, chunking, and vectorization
- Scanned PDF pages, images embedded in DOCX files, and plain images are OCR'd by a vision model (separate `OCR_MODEL`)
- Similarity search backed by PostgreSQL's `pgvector` extension, via LangChain's `PGVector`; chunks below the relevance threshold (`RETRIEVAL_MAX_DISTANCE`) are not shown as citations
- Streaming chat responses, with retrieved source chunks and similarity scores shown below each answer
- Knowledge base management: list ingested documents, delete a single document, or clear the whole knowledge base (password-protected via `CLEAR_KB_PASSWORD`)
- Per-IP rate limiting to protect the public site (`RATE_LIMIT_*`)
- The page header presents the two ways to use the app — "Ask your documents" and "AI support desk" — as side-by-side cards that stack on narrow screens
- English UI by default, with a one-click toggle to Chinese in the sidebar
- Configurable LLM / embedding provider — any OpenAI-compatible API works (local default: Alibaba Cloud Bailian; production: Google Gemini)

**Email auto-reply**

- A background worker (`python -m backend.mail_worker`) polls mail received by Resend and only handles mail addressed to `support@taoxiong.site`
- Rule-based pre-checks: filters auto-replies/bulk mail, spoofed senders, and attachment-only emails, and detects Chinese vs English
- LLM triage (question / spam / abuse / prompt injection / other) splits each email into up to `MAIL_MAX_QUESTIONS` standalone questions; a bare keyword or topic (e.g. "GIT INFOS") counts as an information request
- Each question is answered separately from the knowledge base in a complete, multi-paragraph reply with `[1]`-style citations and a sources line mapping numbers to files (e.g. `[1][3] faq.pdf, [2] guide.docx`); questions the knowledge base can't answer are stated honestly, never filled in with general knowledge
- Replies are sent as both HTML and plain text
- Emails with no recognizable question (thanks, greetings) get a friendly "how to ask" hint; spam and abuse stay silent
- Quota protection: a per-sender daily limit (`MAIL_PER_SENDER_DAILY_LIMIT`) and a global daily limit (`MAIL_DAILY_GLOBAL_LIMIT`), each sender gets one notice per day when a limit is hit; a hard cap (`MAIL_DAILY_HARD_CAP`) stops even the notices, keeping total sends under Resend's daily quota
- The `email_log` table handles deduplication, counting, and retries (`MAIL_MAX_RETRIES`); on first start only mail from the last `MAIL_MAX_AGE_HOURS` hours is processed
- Design doc: [`docs/superpowers/specs/2026-09-29-email-auto-reply-design.md`](docs/superpowers/specs/2026-09-29-email-auto-reply-design.md)

### Tech Stack

| Layer | Component |
| --- | --- |
| Frontend | Streamlit |
| Vector store | PostgreSQL + pgvector (Docker `pgvector/pgvector:pg16` locally, or a hosted instance such as [Neon](https://neon.tech)) |
| RAG orchestration | LangChain (`langchain-core` / `langchain-text-splitters` / `langchain-openai` / `langchain-postgres`) |
| Chat / embedding / OCR models | Any OpenAI-compatible API: Alibaba Cloud Bailian locally by default (`qwen3.8-max` + `text-embedding-v3`), Google Gemini in production |
| Document parsing | `pypdf`, `PyMuPDF` (PDF), `python-docx` (DOCX) |
| Email | [Resend](https://resend.com) (REST API) |
| Deployment | Docker Compose + Caddy, auto-deployed to an ARM64 VM by GitHub Actions |

### Project Structure

```
AI_LLM_RAG/
├── app.py                    # Streamlit UI entry point
├── config.py                 # Config: reads .env / Streamlit Secrets
├── i18n.py                   # EN/ZH UI strings
├── requirements.txt
├── .env.example              # Environment variable template
├── Dockerfile
├── docker-compose.local.yml  # Local dev database (Postgres + pgvector)
├── DEPLOYMENT.md             # VM deployment guide
├── backend/
│   ├── parser.py             # PDF/DOCX/TXT/image text extraction
│   ├── ocr.py                # Vision-model OCR
│   ├── chunker.py            # Text chunking (RecursiveCharacterTextSplitter, chunk_size=500, overlap=50)
│   ├── db.py                 # Postgres/pgvector I/O, knowledge base management
│   ├── rag_chain.py          # Retrieval + prompt assembly + streaming generation
│   ├── rate_limiter.py       # Per-IP sliding-window rate limiter
│   ├── resend_client.py      # Resend email send/receive API
│   ├── mail_rules.py         # Email rules: body extraction, auto-mail/spoof detection, pre-checks
│   ├── mail_templates.py     # Reply templates (ZH/EN), HTML and plain-text body assembly
│   ├── mail_log.py           # email_log table: deduplication, daily quotas, retries
│   ├── mail_analyzer.py      # LLM triage and question splitting, per-question KB answering
│   └── mail_worker.py        # Email worker entry point: python -m backend.mail_worker
├── deploy/                   # Production docker-compose.yml and Caddy site config
├── .github/workflows/        # deploy.yml (auto-deploy), diagnose-mail.yml (mail worker diagnostics)
├── docs/superpowers/         # Design docs and implementation plans
└── tests/                    # Lightweight test scripts
```

### Run Locally

**Requirements**: Python 3.11+ and a PostgreSQL instance with the `pgvector` extension enabled.

1. Install dependencies

   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your Postgres connection details (`PG_HOST` / `PG_PORT` / `PG_DATABASE` / `PG_USER` / `PG_PASSWORD`) and your LLM/embedding API key (`OPENAI_API_KEY`). Everything else has a working default.

   > Use `127.0.0.1` for `PG_HOST`, not `localhost`: on Windows, `localhost` tries IPv6 (`::1`) first and can take two to three minutes to fall back when connecting to Postgres in WSL/Docker.

3. Start the local database (skip if you already have Postgres)

   ```bash
   docker compose -f docker-compose.local.yml up -d
   ```

4. Start the app

   ```bash
   python -m streamlit run app.py
   ```

   Open `http://localhost:8501`, upload documents in the sidebar, click "Process & Build Vector Store", then ask questions below.

5. (Optional) Start the mail worker: set a Full access `RESEND_API_KEY` in `.env`, then run

   ```bash
   python -m backend.mail_worker
   ```

   With `RESEND_API_KEY` empty the worker stays idle and processes no mail.

### Run Tests

Tests are standalone scripts with no pytest dependency (the mail tests use an in-memory SQLite database and fake Resend/LLM clients). Run them one at a time, for example:

```bash
python tests/test_mail_worker.py
```

### Deployment

- **VM (production)**: Docker Compose runs the app, the mail worker, and Postgres, with Caddy as the only public entry point. Pushing to `master` triggers GitHub Actions to build an ARM64 image and deploy it. See [DEPLOYMENT.md](DEPLOYMENT.md) for the required GitHub environment values, DNS setup, and troubleshooting. Without SSH access, run the **Diagnose mail worker** workflow manually to check the worker's status.
- **Streamlit Community Cloud** (web Q&A only, no mail worker): create a new app at [share.streamlit.io](https://share.streamlit.io) with `app.py` as the entry point, and paste the values from `.env.example` into Secrets in TOML format (`KEY = "value"`); `config.py` merges Secrets into environment variables automatically. `.python-version` pins the deployment to Python 3.12.

### Known Limitations

- The file uploader widget's built-in text (drag-and-drop area, "Browse files", etc.) is Streamlit's own English UI chrome and cannot be translated at the app level.
- The knowledge base is a single global collection (`COLLECTION_NAME`) — no per-user/session isolation; extend it yourself if you need multi-tenancy. When changing the embedding model, use a new `COLLECTION_NAME` and re-ingest your documents.
- The email support desk doesn't process attachments; questions must be written in the email body.
- This demo has no user authentication — do not store real private data in a publicly deployed instance.
