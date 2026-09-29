"""邮件回复的预设模板与正文拼装（纯文本，中 / 英两种语言）。"""
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
        "signature": "—\n本邮件由 AI 根据知识库内容自动生成，仅供参考。",
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
        "signature": "—\nThis email was generated automatically by AI from the knowledge base and is for reference only.",
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
