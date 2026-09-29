# 设计：邮件自动回复（Resend 收发信 + 知识库 RAG 回复）

- 日期：2026-09-29
- 状态：已确认设计（grilling 会话达成共识），实现计划见 `docs/superpowers/plans/2026-09-29-email-auto-reply.md`

## 背景

给项目配置一个对外邮箱 `support@taoxiong.site`：任何人来信提问，系统自动分析邮件里的问题，基于现有知识库（与网页端共用的 pgvector collection）生成回复并自动发出。定位是 **Demo 功能**，但必须有完整的错误处理，能应对无效邮件和攻击性邮件。

## 基础设施（已完成）

- DNS 由 Namecheap 托管。`taoxiong.site` 的 Mail Settings 已切为 Custom MX，根域 MX → `inbound-smtp.ap-northeast-1.amazonaws.com`（Resend Receiving），原 Namecheap 邮件转发已停用（确认无其他地址在用）。
- 发信：Resend 已添加域名，DKIM（`resend._domainkey` TXT）与 SPF（`send`、`rsend` 两条 CNAME）已生效。
- Resend API key 已创建。
- 后果：发往任何 `@taoxiong.site` 地址的邮件都会进入 Resend；worker 只处理收件人是 `support@taoxiong.site` 的邮件。

## 决策汇总

| # | 决策 |
|---|---|
| 收信方式 | 轮询 Resend `GET /emails/receiving`（默认每 60 秒），不做 webhook、不新增 HTTP 服务 |
| 发信方式 | Resend `POST /emails`，发件人 `support@taoxiong.site` |
| 发送模式 | 全自动，无草稿 / 人工审核 |
| 运行位置 | docker-compose 新增 `mail-worker` 服务，同一镜像，命令 `python -m backend.mail_worker` |
| 知识库 | 与网页端共用 `COLLECTION_NAME` |
| 发件人范围 | 任何人；每个发件人每天（UTC 自然日）最多 5 封回复，错误模板也计入；超额后回一次"今日额度已用完"，之后静默 |
| 全局上限 | 每天全系统最多 50 封；达到后当天静默，只记日志 |
| 问题分析 | 一次 LLM 调用：分类（question / spam / abuse / injection / other）+ 拆分为独立问题 |
| 问题上限 | 每封最多处理 5 个问题，超出的在回复末尾说明 |
| 逐题作答 | 每题单独检索；距离阈值过滤后无片段 → 未检索到；有片段 → LLM 结构化输出 `{answered, answer}`，`answered=false` 或回答里没有有效引用编号 → 未检索到 |
| 未检索到 | 代码填固定句"知识库中没有检索到相关内容"，**绝不**用网络 / 通用知识作答；所有问题都未检索到 → 整封使用预设模板 |
| 回复语言 | 跟随来信（zh / en；其他语言按 en 模板） |
| 回复格式 | 纯文本；逐条"问题 / 回答 / 参考来源（文件名）"；末尾 AI 声明 |
| 线程 | 只看最新一封（剥离引用历史）；回信 `Re:` 主题 + `In-Reply-To` / `References` 头 |
| 附件 | 不处理、不入库；只有附件 → 预设模板；附件 + 正文 → 正常回答并注明附件未处理 |
| 状态存储 | Postgres 新表 `email_log`：去重、每日计数、重试次数、审计 |
| 故障 | LLM / API 临时故障下次轮询重试，最多 3 次；之后发"系统繁忙"模板；若发信本身失败则只记日志 |

## 错误与攻击处理表

| 类别 | 检测 | 处理 |
|---|---|---|
| 收件人不是 support@ | 规则（to / cc / received_for） | 静默 |
| 自动回复 / 退信 / 邮件列表 / noreply / 自己发给自己 | 规则（邮件头、发件人本地部分） | 静默 |
| DMARC 校验失败（伪造发件人） | Resend `authentication.dmarc == "fail"` | 静默（避免给被冒充者发 backscatter） |
| 全局日上限已到 | `email_log` 计数 | 每个发件人当天提示一次，之后静默；总发信量达到硬上限 `MAIL_DAILY_HARD_CAP`（默认 90）后连提示也不发（2026-09-29 修订：原为静默） |
| 发件人日上限已到 | `email_log` 计数 | 首次回额度提示模板，之后静默 |
| 正文为空 | 规则 | 模板"未能识别您的问题" |
| 只有附件 | 规则（非 inline 附件） | 模板"暂不支持附件" |
| 正文超长（> 5000 字符） | 规则 | 模板"内容过长" |
| 垃圾广告 / 辱骂 | LLM 分类 | 静默 |
| 非提问（感谢、问候、没识别出问题） | LLM 分类 | 模板"如何提问"提示（2026-09-29 修订：原为静默；只写关键词/主题的来信按提问处理） |
| Prompt injection | LLM 分类 + 提示词隔离（邮件内容放在 `<email>` 标签中，明确声明是数据不是指令） | 模板"请求无法处理" |
| LLM / Resend 临时故障 | 异常 | 重试 ≤ 3 次，之后"系统繁忙"模板；发信失败则标记 failed |

另外：只处理创建时间在 24 小时内的邮件，避免 worker 首次启动时把 Resend 里的历史邮件全部回一遍。

## 组件

```
backend/
├── resend_client.py   # Resend REST 最小封装（httpx）：list_received / get_received / send
├── mail_rules.py      # 纯规则：正文提取、引用剥离、自动邮件识别、伪造识别、语言检测、预检
├── mail_templates.py  # 预设模板（zh/en）、回复正文拼装、Re: 主题、线程头
├── mail_log.py        # email_log 表：建表、去重、状态流转、每日计数
├── mail_analyzer.py   # LLM：分类 + 拆题；逐题基于片段作答（JSON 输出）
└── mail_worker.py     # 编排：poll_once / handle_email / decide；main() 轮询循环
```

`email_log` 状态：`pending`（处理中 / 待重试）→ `replied` | `silent` | `failed`（终态）。`category` 记录具体原因（answered、not_found、spam、sender_limit_notice、busy 等）。每日计数只统计 `status = 'replied'`；发件人额度不含 `sender_limit_notice` 本身。

## 配置（新增环境变量）

| 变量 | 默认值 |
|---|---|
| `RESEND_API_KEY` | 空（未配置时 worker 空转并报错日志） |
| `MAIL_FROM` | `RAG Support <support@taoxiong.site>` |
| `MAIL_POLL_SECONDS` | 60 |
| `MAIL_PER_SENDER_DAILY_LIMIT` | 5 |
| `MAIL_DAILY_GLOBAL_LIMIT` | 50 |
| `MAIL_MAX_QUESTIONS` | 5 |
| `MAIL_MAX_BODY_CHARS` | 5000 |
| `MAIL_MAX_RETRIES` | 3 |
| `MAIL_MAX_AGE_HOURS` | 24 |

## 非目标

草稿 / 人工审核、webhook / 新 HTTP 服务、HTML 邮件、线程历史作为上下文、附件内容处理或入库、独立邮件知识库、Streamlit 管理页面。
