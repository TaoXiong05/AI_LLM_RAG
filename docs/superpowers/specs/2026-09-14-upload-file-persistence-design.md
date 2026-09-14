# 设计：持久化保存用户上传的原始文件

- 日期：2026-09-14
- 状态：已确认设计，等待排期实现（本文档只是设计规格，暂不实现）

## 背景 / 问题

当前上传流程（[app.py:264-278](../../../app.py)）里，用户上传的文件只会被读入内存、解析成文本、切块后存入 pgvector 用于检索问答（[backend/parser.py:94](../../../backend/parser.py)、[backend/db.py:56](../../../backend/db.py)）。**原始文件字节从未落盘**，处理完成后随对象被垃圾回收，彻底丢失。用户希望：

1. 原始文件保持格式不变地保存到服务器；
2. 随时可以下载查阅。

## 现状分析

- 部署方式：自建 Docker Compose，跑在 VPS 上（`deploy/docker-compose.yml`），磁盘是持久的、可靠的（不是 Streamlit Community Cloud 那种临时文件系统）。
- 文档身份体系：系统里没有任何"文档表"，`source`（原始文件名字符串）就是文档的唯一标识，`list_sources()` / `delete_source()` / `clear_knowledge_base()`（`backend/db.py`）全部按 `cmetadata->>'source'` 分组/过滤。
- 无鉴权、无多租户：知识库全局共享，任何访客都能看到全部文档、删除单篇文档（无需密码），只有"清空全部"需要密码。因此"任何人可下载原始文件"和现有威胁模型是一致的，不会引入新的暴露面。
- `deploy/docker-compose.yml` 里 `app` 服务目前没有任何 volume 挂载；只有 `db` 服务的 `pgdata` 卷。
- 项目里没有 ORM/迁移框架，`backend/db.py` 里都是手写 SQL，风格上倾向"能不加表就不加表"。
- `tests/` 目录里已有纯逻辑单元测试（不连真实 Postgres），如 `tests/test_rate_limiter.py`，可以按同样风格给新模块加测试。

## 目标

- 上传成功入库的文件，原始字节原样保存在服务器磁盘上，格式不变。
- 知识库文档列表里可以选中一篇文档并下载其原始文件。
- 删除单篇文档 / 清空知识库时，磁盘上对应的文件同步清理，不产生"数据库已删、文件还在"的不一致。
- 容器重启、镜像更新后文件不丢失。

## 非目标

- 不做多租户/按用户隔离存储（现有系统本来就没有用户概念）。
- 不做重复文件名的去重/合并语义修正——现状本来就是"同名文件的 chunk 会在向量库里累加"，这是既有行为，本次不改动，磁盘存储沿用同样的"同名覆盖"语义。
- 不为「本功能上线前」已经入库的历史文档补救原始文件——原始字节早已丢弃，无法恢复，UI 需要能优雅地识别并提示这类文档。
- 不引入新的数据库表、manifest 文件、NoSQL 存储或新的 Docker 服务/容器。

## 设计

### 存储位置与配置

新增环境变量 `UPLOAD_DIR`（默认 `/data/uploads`），加到 `config.py` 的 `Settings`，与 `collection_name` 等现有配置同一模式：

```python
upload_dir: str
...
upload_dir=os.getenv("UPLOAD_DIR", "/data/uploads"),
```

`deploy/docker-compose.yml` 的 `app` 服务新增具名 volume：

```yaml
app:
  ...
  volumes:
    - uploads:/data/uploads

volumes:
  pgdata:
  uploads:
```

### 文件身份与元信息：不引入额外存储

文件在磁盘上直接以 `source`（原始文件名，经过安全处理）命名，复用系统里已有的"文件名即身份"体系，不新增表/JSON 清单/NoSQL：

| 信息 | 来源 |
|---|---|
| 文件内容 | 磁盘文件本身 |
| 文件大小 | `os.path.getsize()` |
| 文件类型（下载时的 Content-Type） | `mimetypes.guess_type(filename)`，按扩展名推断 |
| 上传时间 | 文件的 mtime（写入时自然产生，无需额外记录） |

这样磁盘文件本身就是唯一的真相来源，不存在"元数据和文件不同步"的风险。

### 新模块 `backend/file_storage.py`

职责单一：只做文件系统层面的读写，不碰数据库、不碰 Streamlit。对外接口：

- `safe_filename(name: str) -> str`：取 `os.path.basename`，拒绝空文件名、`..`、路径分隔符等，防止路径穿越写到 `UPLOAD_DIR` 之外。
- `save_upload(source: str, data: bytes) -> Path`：原子写入——先写到 `UPLOAD_DIR/.<source>.tmp`，写完后 `os.replace()` 原子改名为 `UPLOAD_DIR/<safe_source>`，避免进程崩溃/断电导致文件写到一半损坏。同名文件会被覆盖（与向量库"同名累加"的现状保持一致的身份粒度，见"非目标"）。
- `get_file_path(source: str) -> Path | None`：返回文件是否存在及其路径，找不到时返回 `None`（用于 UI 判断是否展示下载按钮）。
- `delete_file(source: str) -> None`：删除单个文件，不存在时静默忽略。
- `clear_all() -> None`：清空 `UPLOAD_DIR` 下所有文件，对应"清空知识库"操作。

### 数据流

**上传**（改动 [app.py:264-278](../../../app.py) 的处理循环）：

1. 现有逻辑不变：`f.getvalue()` → `parse_file()` → `chunker.chunk_document()` → `db.add_documents(chunks)`。
2. **仅当 `db.add_documents()` 成功执行后**，追加一步：`file_storage.save_upload(f.name, f.getvalue())`。
   - 之所以放在成功入库之后：保证磁盘上出现的文件一定是知识库里真实存在的文档，跳过（不支持类型/解析失败/空文本）的文件不会留下半成品文件。
   - `f.getvalue()` 在 Streamlit 的 `UploadedFile` 上可重复调用（不是一次性流），所以不影响前面 `parse_file(f)` 内部已经读过一次字节。

**下载**（改动 [app.py:302-306](../../../app.py) 附近的文档列表区域）：

- 选中某篇文档后，调用 `file_storage.get_file_path(selected_source)`：
  - 存在：用 `st.download_button` 展示，文件名用 `selected_source`，`mime` 用 `mimetypes.guess_type` 推断。
  - 不存在（本功能上线前的历史文档）：展示提示文案，说明这是历史文档、原始文件未保存，无法下载。

**删除同步**（改动 [app.py:317-321](../../../app.py) 单文档删除 / [app.py:350-359](../../../app.py) 清空知识库）：

- 单文档删除：`db.delete_source(pending)` 之后紧接着调用 `file_storage.delete_file(pending)`。
- 清空知识库：`db.clear_knowledge_base()` 之后紧接着调用 `file_storage.clear_all()`。

### 文案（i18n）

在 `i18n.py` 里按现有 `en`/`zh` 两份字典的格式各加一组 key（示例，具体文案实现时可微调）：

- `download_doc_button`："Download Original File" / "下载原始文件"
- `download_not_available`："Original file not available for documents ingested before this feature." / "这是本功能上线前的历史文档，原始文件未保存，无法下载。"

## 错误处理

- **路径穿越**：`safe_filename()` 在写入前拒绝非法文件名，防止恶意 `f.name`（理论上浏览器不会发送这种文件名，但作为服务端防御措施）。
- **写入中断**：原子写入（temp file + `os.replace`）保证不会出现"写到一半"的半成品文件。
- **磁盘写入失败**（如磁盘满）：`save_upload` 抛出的异常应该被现有的 per-file `try/except`（[app.py:264-277](../../../app.py)）捕获，落到 `warnings` 里提示用户该文件处理失败，不影响其它文件继续处理。需要注意：此时该文档的 chunk 已经写入了 pgvector，但原始文件保存失败——这种"部分成功"的情况在提示文案里应明确说明（比如"已建立索引，但原始文件保存失败"），避免用户以为完全失败。
- **删除时文件已不存在**：`delete_file()`/`clear_all()` 对"文件不存在"的情况静默处理，不抛异常（可能是历史文档，也可能重复点击删除）。

## 涉及文件清单

| 文件 | 改动 |
|---|---|
| `config.py` | 新增 `upload_dir` 配置项 |
| `backend/file_storage.py`（新增） | 文件系统读写模块：`safe_filename` / `save_upload` / `get_file_path` / `delete_file` / `clear_all` |
| `app.py` | 上传循环里追加保存调用；文档列表区域加下载按钮；单文档删除/清空知识库处追加文件清理调用 |
| `i18n.py` | 新增下载按钮、历史文档提示的中英文案 |
| `deploy/docker-compose.yml` | `app` 服务新增 `uploads` 具名 volume |
| `tests/test_file_storage.py`（新增） | 覆盖 `safe_filename` 路径穿越防护、原子写入、get/delete/clear_all，使用 `tmp_path`，不依赖真实 Postgres |

## 测试计划

**自动化**（`tests/test_file_storage.py`，风格参考现有 `tests/test_rate_limiter.py`）：
- `safe_filename` 对 `../../etc/passwd`、空字符串、纯路径分隔符等输入的防护。
- `save_upload` 写入后文件内容与原始字节完全一致（byte-for-byte）；重复保存同名文件会覆盖旧内容。
- `get_file_path` 对存在/不存在的文件分别返回正确路径 / `None`。
- `delete_file` 删除后 `get_file_path` 返回 `None`；对不存在的文件调用不报错。
- `clear_all` 清空目录后所有文件都不可获取。

**手动验证**（在实际实现阶段，接入 Docker Compose 环境后执行）：
1. 上传 pdf/docx/txt/图片各一个，确认处理成功后 `UPLOAD_DIR`（容器内 `/data/uploads`，对应宿主机 volume）出现对应文件。
2. 在文档列表选中一篇，点击下载，确认下载下来的文件与原始上传文件字节一致、能正常用对应软件打开。
3. 删除单篇文档，确认磁盘上的文件同步消失，其余文档不受影响。
4. 清空知识库（输入密码），确认 `UPLOAD_DIR` 下所有文件都被清空。
5. 重启 `app` 容器（`docker compose restart app`），确认之前保存的文件仍然存在（验证 volume 生效）。
6. 对一篇本功能上线前就已存在于知识库的历史文档（如果测试环境有的话），确认列表里能正确显示"原始文件不可下载"提示，而不是报错。

## 已确认的设计决策（供实现时参考，避免重新讨论）

- 部署环境是自建 Docker Compose + VPS，本地磁盘持久可靠 → 选择本地磁盘 + Docker 具名卷，而非对象存储（S3/MinIO）。
- 不引入新的数据库表 / manifest.json / NoSQL（如 TinyDB）—— 文件大小、类型、上传时间都能从磁盘文件本身推导，额外存储只会增加"数据源不同步"的风险，不增加实际价值。
- 原始文件的保存与"文本切块 + 向量化"是两条独立的数据流，都源自同一份上传字节，互不依赖——**不存在"用 chunks 重组文件"的环节**，因此也不存在因切块方式导致文件损坏的风险。
- 磁盘写入采用"先写临时文件、再原子性 rename"，防止进程崩溃/断电导致文件损坏。
- 下载入口：知识库文档列表页面内嵌下载按钮（而非需要 SSH 到服务器手动取文件）。
