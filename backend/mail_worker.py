"""邮件自动回复 worker：轮询 Resend 收件箱，规则 + LLM 分诊，基于知识库逐题作答并自动回信。

运行：python -m backend.mail_worker
设计：docs/superpowers/specs/2026-09-29-email-auto-reply-design.md
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from langchain_core.documents import Document
from sqlalchemy import Engine

from backend import mail_analyzer, mail_log, mail_rules
from backend.mail_analyzer import LLMFn
from backend.mail_templates import (
    AnswerItem,
    compose_answers,
    render_template,
    reply_subject,
    thread_headers,
)

log = logging.getLogger("mail_worker")

TERMINAL = {mail_log.REPLIED, mail_log.SILENT, mail_log.FAILED}


@dataclass
class WorkerConfig:
    mail_from: str
    mail_address: str
    per_sender_daily_limit: int
    daily_global_limit: int
    max_questions: int
    max_body_chars: int
    max_retries: int
    max_age_hours: float


@dataclass
class Deps:
    engine: Engine
    client: object  # ResendClient 或测试替身：list_received / get_received / send
    retrieve: Callable[[str], list[tuple[Document, float]]]
    llm: LLMFn
    config: WorkerConfig
    clock: Callable[[], float] = time.time


def _answer(question: str, lang: str, deps: Deps) -> AnswerItem:
    chunks = deps.retrieve(question)
    if not chunks:
        return AnswerItem(question, None, [])
    result = mail_analyzer.answer_question(question, chunks, lang, deps.llm)
    if not result.answered:
        return AnswerItem(question, None, [])
    sources = [chunks[i - 1][0].metadata.get("source", "") for i in result.cited]
    return AnswerItem(question, result.answer, [s for s in dict.fromkeys(sources) if s])


def decide(email: dict, deps: Deps, now: float) -> tuple[str, str | None]:
    """决定如何回复一封邮件：返回 (category, 回复正文)，正文为 None 表示静默。

    LLM 调用失败会直接抛异常，由 handle_email 负责重试。
    """
    cfg = deps.config
    if not mail_rules.is_addressed_to(email, cfg.mail_address):
        return "ignored_recipient", None
    if mail_rules.is_auto_generated(email, cfg.mail_address):
        return "auto_generated", None
    if mail_rules.is_spoofed(email):
        return "spoofed", None

    day = mail_log.utc_day_start(now)
    if mail_log.count_replies(deps.engine, since=day) >= cfg.daily_global_limit:
        return "global_limit", None

    subject = email.get("subject") or ""
    body = mail_rules.extract_body(email)
    lang = mail_rules.detect_lang(f"{subject}\n{body}")

    sender = mail_rules.sender_address(email)
    used = mail_log.count_replies(
        deps.engine, since=day, sender=sender, exclude_category="sender_limit_notice"
    )
    if used >= cfg.per_sender_daily_limit:
        if mail_log.count_replies(deps.engine, since=day, sender=sender, category="sender_limit_notice"):
            return "sender_limit_silent", None
        return "sender_limit_notice", render_template("sender_limit", lang, n=cfg.per_sender_daily_limit)

    attached = mail_rules.has_attachments(email)
    problem = mail_rules.precheck(body, attached, cfg.max_body_chars)
    if problem:
        return problem, render_template(problem, lang, n=cfg.max_body_chars)

    analysis = mail_analyzer.analyze_email(subject, body, lang, deps.llm)
    lang = analysis.language
    if analysis.category in ("spam", "abuse", "other"):
        return analysis.category, None
    if analysis.category == "injection":
        return "injection", render_template("injection", lang)

    questions = analysis.questions[: cfg.max_questions]
    items = [_answer(q, lang, deps) for q in questions]
    if all(item.answer is None for item in items):
        return "not_found", render_template("all_not_found", lang)
    truncated = cfg.max_questions if len(analysis.questions) > cfg.max_questions else None
    return "answered", compose_answers(items, lang, truncated, attached)


def _send(email: dict, reply: str, deps: Deps, idempotency_key: str) -> None:
    deps.client.send(
        from_=deps.config.mail_from,
        to=mail_rules.sender_address(email),
        subject=reply_subject(email.get("subject")),
        text=reply,
        headers=thread_headers(email),
        idempotency_key=idempotency_key,
    )


def _give_up(email: dict, deps: Deps, now: float) -> None:
    """重试次数用尽：给正常来信的人回一封"系统繁忙"；若连发信都失败，只记日志。"""
    resend_id = email["id"]
    cfg = deps.config
    try:
        if (
            not mail_rules.is_addressed_to(email, cfg.mail_address)
            or mail_rules.is_auto_generated(email, cfg.mail_address)
            or mail_rules.is_spoofed(email)
        ):
            mail_log.finish(deps.engine, resend_id, status=mail_log.FAILED, category="gave_up", now=now)
            return
        lang = mail_rules.detect_lang(f"{email.get('subject') or ''}\n{mail_rules.extract_body(email)}")
    except Exception as exc:  # noqa: BLE001 - 邮件本身无法解析：直接置为终态，避免每次轮询都重试
        log.exception("邮件 %s 收尾前的解析失败", resend_id)
        mail_log.finish(
            deps.engine, resend_id, status=mail_log.FAILED, category="give_up_error",
            now=now, error=repr(exc)[:1000],
        )
        return
    try:
        _send(email, render_template("busy", lang), deps, idempotency_key=f"busy-{resend_id}")
    except Exception as exc:  # noqa: BLE001 - 发信通道本身故障，只能记录
        log.exception("邮件 %s 的繁忙提示发送失败", resend_id)
        mail_log.finish(
            deps.engine, resend_id, status=mail_log.FAILED, category="busy_send_failed",
            now=now, error=repr(exc)[:1000],
        )
        return
    mail_log.finish(deps.engine, resend_id, status=mail_log.REPLIED, category="busy", now=now)


def _too_old(summary: dict, now: float, max_age_hours: float) -> bool:
    raw = summary.get("created_at")
    if not raw:
        return False
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return now - created > max_age_hours * 3600


def handle_email(summary: dict, deps: Deps) -> None:
    now = deps.clock()
    resend_id = summary["id"]
    state = mail_log.get_status(deps.engine, resend_id)
    if state and state[0] in TERMINAL:
        return
    # 首次启动时 Resend 里可能有历史邮件，只处理最近 max_age_hours 内到达的
    if state is None and _too_old(summary, now, deps.config.max_age_hours):
        return

    try:
        email = deps.client.get_received(resend_id)
    except Exception as exc:  # noqa: BLE001 - 读取详情失败：没有正文和发件人，无法回信
        if state is None:
            # 尚未落日志：后续轮询会重试，由 max_age_hours 兜底
            log.warning("读取邮件 %s 详情失败：%r", resend_id, exc)
            return
        retries = mail_log.bump_retry(deps.engine, resend_id, error=repr(exc)[:1000], now=now)
        log.warning("读取邮件 %s 详情失败（第 %d 次）：%r", resend_id, retries, exc)
        if retries >= deps.config.max_retries:
            mail_log.finish(
                deps.engine, resend_id, status=mail_log.FAILED, category="fetch_failed",
                now=now, error=repr(exc)[:1000],
            )
        return
    mail_log.start(
        deps.engine, resend_id,
        message_id=email.get("message_id"),
        sender=mail_rules.sender_address(email),
        subject=email.get("subject"),
        now=now,
    )
    if state and state[0] == mail_log.PENDING and state[1] >= deps.config.max_retries:
        # 重试次数已用尽（例如上次收尾写日志失败）：不再重跑 decide，直接收尾
        _give_up(email, deps, now)
        return
    try:
        category, reply = decide(email, deps, now)
        if reply is not None:
            _send(email, reply, deps, idempotency_key=f"reply-{resend_id}")
    except Exception as exc:  # noqa: BLE001 - LLM / Resend 临时故障，下次轮询重试
        retries = mail_log.bump_retry(deps.engine, resend_id, error=repr(exc)[:1000], now=now)
        log.warning("处理邮件 %s 失败（第 %d 次）：%r", resend_id, retries, exc)
        if retries >= deps.config.max_retries:
            _give_up(email, deps, now)
        return

    status = mail_log.REPLIED if reply is not None else mail_log.SILENT
    mail_log.finish(deps.engine, resend_id, status=status, category=category, now=now)
    log.info("邮件 %s：%s / %s", resend_id, status, category)


def poll_once(deps: Deps) -> None:
    summaries = deps.client.list_received()
    # 接口按时间倒序返回，反转后先处理先到的邮件，保证每日额度按到达顺序消耗
    for summary in reversed(summaries):
        try:
            handle_email(summary, deps)
        except Exception:  # noqa: BLE001 - 单封邮件出错（如读取详情失败）不影响其他邮件
            log.exception("处理邮件 %s 出错，下次轮询重试", summary.get("id"))


def build_deps() -> Deps:
    from langchain_openai import ChatOpenAI

    from backend import db
    from backend.resend_client import ResendClient
    from config import settings

    chat = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
        timeout=60,
        max_retries=2,
    )

    def llm(messages: list[dict]) -> str:
        return str(chat.invoke(messages).content)

    return Deps(
        engine=db.get_engine(),
        client=ResendClient(settings.resend_api_key),
        retrieve=db.similarity_search,
        llm=llm,
        config=WorkerConfig(
            mail_from=settings.mail_from,
            mail_address=settings.mail_address,
            per_sender_daily_limit=settings.mail_per_sender_daily_limit,
            daily_global_limit=settings.mail_daily_global_limit,
            max_questions=settings.mail_max_questions,
            max_body_chars=settings.mail_max_body_chars,
            max_retries=settings.mail_max_retries,
            max_age_hours=settings.mail_max_age_hours,
        ),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from backend import db
    from config import settings

    if not settings.resend_api_key:
        # 空转而不是退出：restart: unless-stopped 下退出会导致容器反复重启刷日志
        log.error("RESEND_API_KEY 未配置，邮件自动回复未启用")
        while True:
            time.sleep(3600)

    deps = build_deps()
    db.ensure_pgvector_extension()
    mail_log.ensure_table(deps.engine)
    log.info("邮件 worker 已启动：%s，每 %.0f 秒轮询一次", settings.mail_address, settings.mail_poll_seconds)
    while True:
        try:
            poll_once(deps)
        except Exception:  # noqa: BLE001 - 列表接口失败等，等下一轮
            log.exception("轮询失败")
        time.sleep(settings.mail_poll_seconds)


if __name__ == "__main__":
    main()
