"""email_log 表：邮件处理记录，同时承担去重、每日限额计数、重试计数和审计。

时间统一存 epoch 秒（float），SQL 只用 Postgres / SQLite 都支持的语法，方便用内存 SQLite 测试。
状态：pending（处理中 / 待重试）→ replied | silent | failed（终态）。
"""
from sqlalchemy import Engine, text

PENDING = "pending"
REPLIED = "replied"
SILENT = "silent"
FAILED = "failed"

DDL = """
CREATE TABLE IF NOT EXISTS email_log (
    resend_id   TEXT PRIMARY KEY,
    message_id  TEXT,
    sender      TEXT NOT NULL,
    subject     TEXT,
    category    TEXT,
    status      TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_ts  DOUBLE PRECISION NOT NULL,
    updated_ts  DOUBLE PRECISION NOT NULL
)
"""


def ensure_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(DDL))


def get_status(engine: Engine, resend_id: str) -> tuple[str, int] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, retry_count FROM email_log WHERE resend_id = :id"),
            {"id": resend_id},
        ).first()
    return (row.status, row.retry_count) if row else None


def start(
    engine: Engine,
    resend_id: str,
    *,
    message_id: str | None,
    sender: str,
    subject: str | None,
    now: float,
) -> None:
    """登记一封待处理邮件；已登记过（重试时）则保持原记录不变。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO email_log
                    (resend_id, message_id, sender, subject, status, retry_count, created_ts, updated_ts)
                VALUES (:id, :message_id, :sender, :subject, :status, 0, :now, :now)
                ON CONFLICT (resend_id) DO NOTHING
                """
            ),
            {
                "id": resend_id,
                "message_id": message_id,
                "sender": sender,
                "subject": subject,
                "status": PENDING,
                "now": now,
            },
        )


def finish(
    engine: Engine,
    resend_id: str,
    *,
    status: str,
    category: str,
    now: float,
    error: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE email_log
                SET status = :status, category = :category,
                    error = COALESCE(:error, error), updated_ts = :now
                WHERE resend_id = :id
                """
            ),
            {"id": resend_id, "status": status, "category": category, "error": error, "now": now},
        )


def bump_retry(engine: Engine, resend_id: str, *, error: str, now: float) -> int:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE email_log
                SET retry_count = retry_count + 1, error = :error, updated_ts = :now
                WHERE resend_id = :id
                """
            ),
            {"id": resend_id, "error": error, "now": now},
        )
        return conn.execute(
            text("SELECT retry_count FROM email_log WHERE resend_id = :id"), {"id": resend_id}
        ).scalar_one()


def count_replies(
    engine: Engine,
    *,
    since: float,
    sender: str | None = None,
    category: str | None = None,
    exclude_category: str | None = None,
) -> int:
    """统计 since 之后已发出的回复数（status = replied），用于每日限额。"""
    sql = "SELECT COUNT(*) FROM email_log WHERE status = :replied AND created_ts >= :since"
    params: dict = {"replied": REPLIED, "since": since}
    if sender is not None:
        sql += " AND sender = :sender"
        params["sender"] = sender
    if category is not None:
        sql += " AND category = :category"
        params["category"] = category
    if exclude_category is not None:
        sql += " AND (category IS NULL OR category <> :exclude_category)"
        params["exclude_category"] = exclude_category
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def utc_day_start(now: float) -> float:
    """now 所在 UTC 自然日的 0 点（epoch 秒天然按 UTC 对齐）。"""
    return now - (now % 86400)
