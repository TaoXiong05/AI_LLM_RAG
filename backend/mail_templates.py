"""邮件回复的预设模板与正文拼装（中 / 英两种语言）。

每封回信同时生成纯文本和 HTML 两个版本：邮件客户端优先显示 HTML，
不支持 HTML 的客户端回退到纯文本。HTML 只用内联样式，保证 Gmail / Outlook 等客户端显示一致。
"""
import html
import re
from dataclasses import dataclass

from backend.mail_rules import lower_headers

TEMPLATES = {
    "zh": {
        "greeting": "您好，\n\n感谢您的来信，以下是针对您问题的回复：",
        "question": "问题 {n}：{q}",
        "answer": "回答：{a}",
        "sources": "参考来源：{s}",
        "sep": "、",
        "not_found": "回答：知识库中没有检索到相关内容。",
        "truncated": "（每封邮件最多处理 {n} 个问题，其余问题未作答，如需咨询请另行来信。）",
        "attachment_note": "（暂不支持处理邮件附件，本回复仅基于邮件正文。）",
        "empty": "您好，\n\n未能从您的邮件中识别出问题，请直接用文字描述您的问题后重新发送。",
        "too_long": "您好，\n\n您的邮件内容过长（超过 {n} 字），请精简后重新发送。",
        "attachment_only": "您好，\n\n暂不支持处理邮件附件，请把您的问题直接写在邮件正文中重新发送。",
        "injection": "您好，\n\n抱歉，您的请求无法处理。本邮箱仅回答与知识库内容相关的问题。",
        "sender_limit": "您好，\n\n您今天的自动回复次数已达上限（{n} 封），请明天再来信。",
        "all_not_found": "您好，\n\n很抱歉，知识库中没有检索到与您的问题相关的内容。",
        "busy": "您好，\n\n系统暂时繁忙，未能处理您的邮件，请稍后重新发送。",
        "no_question": "您好，\n\n感谢来信！本邮箱由 AI 客服自动处理，只回答与知识库内容相关的问题，"
        "这次没有在您的邮件中识别到具体问题。\n\n如果您有想了解的内容，直接回复本邮件，把问题完整写出来即可，"
        "例如：“什么是 MCP 服务器？”",
        "signature": "—\n本邮件由 AI 根据知识库内容自动生成，仅供参考。",
        "brand": "RAG 智能客服",
        "question_label": "问题 {n}",
        "sources_label": "参考来源",
        "not_found_short": "知识库中没有检索到相关内容。",
        "reply_hint": "如有新的问题，直接回复本邮件即可，请把问题完整写出来。",
    },
    "en": {
        "greeting": "Hello,\n\nThank you for your email. Here are the answers to your questions:",
        "question": "Question {n}: {q}",
        "answer": "Answer: {a}",
        "sources": "Sources: {s}",
        "sep": ", ",
        "not_found": "Answer: No relevant information was found in the knowledge base.",
        "truncated": "(At most {n} questions are answered per email; please send the rest in a new email.)",
        "attachment_note": "(Attachments are not supported; this reply is based on the email body only.)",
        "empty": "Hello,\n\nWe could not find a question in your email. Please describe your question in the email body and send it again.",
        "too_long": "Hello,\n\nYour email is too long (over {n} characters). Please shorten it and send it again.",
        "attachment_only": "Hello,\n\nAttachments are not supported. Please write your question in the email body and send it again.",
        "injection": "Hello,\n\nSorry, your request cannot be processed. This mailbox only answers questions about the knowledge base.",
        "sender_limit": "Hello,\n\nYou have reached today's limit of {n} automatic replies. Please write again tomorrow.",
        "all_not_found": "Hello,\n\nSorry, no information related to your question was found in the knowledge base.",
        "busy": "Hello,\n\nThe system is temporarily busy and could not process your email. Please try again later.",
        "no_question": "Hello,\n\nThanks for your email! This mailbox is handled automatically by an AI assistant "
        "that answers questions about the knowledge base, and we couldn't find a specific question in your message."
        "\n\nIf there's something you'd like to know, just reply to this email and write out the full question, "
        "for example: \"What is an MCP server?\"",
        "signature": "—\nThis email was generated automatically by AI from the knowledge base and is for reference only.",
        "brand": "RAG Support",
        "question_label": "Question {n}",
        "sources_label": "Sources",
        "not_found_short": "No relevant information was found in the knowledge base.",
        "reply_hint": "Have another question? Just reply to this email and write the full question.",
    },
}


@dataclass
class AnswerItem:
    question: str
    answer: str | None  # None 表示知识库中未检索到
    sources: list[str]


def _t(lang: str, key: str) -> str:
    return TEMPLATES.get(lang, TEMPLATES["en"])[key]


def render_template(key: str, lang: str, **kwargs) -> str:
    """整封使用预设模板的邮件正文（含 AI 声明签名）。多余的 kwargs 会被忽略。"""
    return _t(lang, key).format(**kwargs) + "\n\n" + _t(lang, "signature")


def compose_answers(
    items: list[AnswerItem], lang: str, truncated_limit: int | None, attachment_note: bool
) -> str:
    """逐题拼装回复：问题 / 回答（或未检索到）/ 参考来源，末尾附说明与签名。"""
    parts = [_t(lang, "greeting")]
    for n, item in enumerate(items, 1):
        block = [_t(lang, "question").format(n=n, q=item.question)]
        if item.answer is None:
            block.append(_t(lang, "not_found"))
        else:
            block.append(_t(lang, "answer").format(a=item.answer))
            if item.sources:
                block.append(_t(lang, "sources").format(s=_t(lang, "sep").join(item.sources)))
        parts.append("\n".join(block))
    if truncated_limit:
        parts.append(_t(lang, "truncated").format(n=truncated_limit))
    if attachment_note:
        parts.append(_t(lang, "attachment_note"))
    parts.append(_t(lang, "signature"))
    return "\n\n".join(parts)


# ---------------- HTML 版本 ----------------

_ACCENT = "#2563eb"
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',Arial,sans-serif"
_P = "margin:0 0 12px;font-size:15px;line-height:1.65;color:#1f2937;"
_MUTED = "margin:0 0 12px;font-size:13px;line-height:1.6;color:#6b7280;"
_CITE = re.compile(r"\[(\d+)\]")


def _paragraphs(text: str, style: str = _P) -> str:
    """纯文本 → HTML 段落：空行分段、单个换行转 <br>，引用编号 [n] 以蓝色上标显示。"""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    out = []
    for block in blocks:
        escaped = html.escape(block).replace("\n", "<br>")
        escaped = _CITE.sub(
            rf'<sup style="color:{_ACCENT};font-size:11px;font-weight:600;">[\1]</sup>', escaped
        )
        out.append(f'<p style="{style}">{escaped}</p>')
    return "".join(out)


def _page(lang: str, body: str) -> str:
    """邮件外框：品牌抬头 + 正文卡片 + 页脚（AI 声明与回复提示）。"""
    signature = _t(lang, "signature").lstrip("—").strip()
    return (
        f'<!doctype html><html lang="{"zh" if lang == "zh" else "en"}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:#f3f4f6;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">'
        f'<tr><td align="center" style="padding:24px 12px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:620px;background:#ffffff;border-radius:12px;border:1px solid #e5e7eb;font-family:{_FONT};">'
        f'<tr><td style="padding:20px 28px;border-bottom:1px solid #e5e7eb;">'
        f'<span style="font-size:13px;font-weight:700;letter-spacing:.04em;color:{_ACCENT};">'
        f'{html.escape(_t(lang, "brand"))}</span></td></tr>'
        f'<tr><td style="padding:24px 28px 8px;">{body}</td></tr>'
        f'<tr><td style="padding:16px 28px 22px;border-top:1px solid #e5e7eb;">'
        f'<p style="{_MUTED}margin-bottom:4px;">{html.escape(_t(lang, "reply_hint"))}</p>'
        f'<p style="{_MUTED}margin-bottom:0;font-size:12px;">{html.escape(signature)}</p>'
        f"</td></tr></table></td></tr></table></body></html>"
    )


def render_template_html(key: str, lang: str, **kwargs) -> str:
    """预设模板邮件的 HTML 版本。"""
    return _page(lang, _paragraphs(_t(lang, key).format(**kwargs)))


def compose_answers_html(
    items: list[AnswerItem], lang: str, truncated_limit: int | None, attachment_note: bool
) -> str:
    """逐题回复的 HTML 版本：每个问题一张卡片（标题 / 回答段落 / 参考来源）。"""
    parts = [_paragraphs(_t(lang, "greeting"))]
    for n, item in enumerate(items, 1):
        card = [
            f'<div style="margin:20px 0 0;padding:18px 20px;border:1px solid #e5e7eb;'
            f'border-left:4px solid {_ACCENT};border-radius:8px;background:#fafafa;">',
            f'<div style="font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;'
            f'color:{_ACCENT};margin-bottom:6px;">{html.escape(_t(lang, "question_label").format(n=n))}</div>',
            f'<div style="font-size:16px;font-weight:600;line-height:1.5;color:#111827;margin-bottom:12px;">'
            f"{html.escape(item.question)}</div>",
        ]
        if item.answer is None:
            card.append(
                f'<p style="{_P}color:#6b7280;font-style:italic;">'
                f'{html.escape(_t(lang, "not_found_short"))}</p>'
            )
        else:
            card.append(_paragraphs(item.answer))
            if item.sources:
                bold_cites = (_CITE.sub(r"<b>[\1]</b>", html.escape(s)) for s in item.sources)
                rows = "".join(f'<li style="margin:2px 0;">{s}</li>' for s in bold_cites)
                card.append(
                    f'<div style="margin-top:4px;padding:10px 14px;background:#ffffff;border:1px solid #e5e7eb;'
                    f'border-radius:6px;font-size:13px;color:#4b5563;">'
                    f'<div style="font-weight:600;margin-bottom:4px;">{html.escape(_t(lang, "sources_label"))}</div>'
                    f'<ul style="margin:0;padding-left:18px;">{rows}</ul></div>'
                )
        card.append("</div>")
        parts.append("".join(card))
    notes = []
    if truncated_limit:
        notes.append(_t(lang, "truncated").format(n=truncated_limit))
    if attachment_note:
        notes.append(_t(lang, "attachment_note"))
    if notes:
        parts.append('<div style="margin-top:18px;">' + "".join(_paragraphs(x, _MUTED) for x in notes) + "</div>")
    return _page(lang, "".join(parts))


@dataclass
class Reply:
    """一封回信的两个版本。"""

    text: str
    html: str


def template_reply(key: str, lang: str, **kwargs) -> Reply:
    return Reply(render_template(key, lang, **kwargs), render_template_html(key, lang, **kwargs))


def answers_reply(
    items: list[AnswerItem], lang: str, truncated_limit: int | None, attachment_note: bool
) -> Reply:
    return Reply(
        compose_answers(items, lang, truncated_limit, attachment_note),
        compose_answers_html(items, lang, truncated_limit, attachment_note),
    )


def reply_subject(subject: str | None) -> str:
    subject = (subject or "").strip()
    if re.match(r"^re\s*[:：]", subject, re.I):
        return subject
    return f"Re: {subject}".strip()


def thread_headers(email: dict) -> dict[str, str]:
    """让回信在对方邮件客户端里归入同一会话。"""
    message_id = email.get("message_id")
    if not message_id:
        return {}
    references = lower_headers(email).get("references", "").strip()
    return {"In-Reply-To": message_id, "References": f"{references} {message_id}".strip()}
