"""邮件的纯规则处理：正文提取、引用剥离、自动邮件 / 伪造识别、语言检测、规则预检。

不调用 LLM、不访问网络，输入是 Resend「Retrieve Received Email」接口返回的 dict。
"""
import base64
import re
from email.utils import parseaddr
from html.parser import HTMLParser
from urllib.parse import unquote

# 这些发件人本地部分代表系统自动邮件，回复它们只会制造回环或退信
AUTO_LOCALPART = re.compile(
    r"^(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounces?)([+.\-_].*)?$", re.I
)
AUTO_PRECEDENCE = {"bulk", "junk", "list", "auto_reply"}
AUTO_HEADERS = ("list-id", "list-unsubscribe", "x-autoreply", "x-autorespond")

# 回复历史的起始行：Gmail/Outlook/QQ 等客户端的常见写法，遇到后其后内容全部丢弃
QUOTE_HEADER = re.compile(
    r"^\s*(on\s.+wrote:|在.+写道[:：]|-{2,}\s*original message\s*-{2,}|-{2,}\s*原始邮件\s*-{2,}"
    r"|from:\s.+|发件人[:：].+)\s*$",
    re.I,
)


def sender_address(email: dict) -> str:
    return parseaddr(email.get("from") or "")[1].lower()


def lower_headers(email: dict) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (email.get("headers") or {}).items()}


def is_addressed_to(email: dict, address: str) -> bool:
    """收件人（to / cc / received_for）里是否包含 address。根域 MX 指向 Resend，其他地址的邮件要忽略。"""
    fields = (email.get("to") or []) + (email.get("cc") or []) + (email.get("received_for") or [])
    return any(parseaddr(f)[1].lower() == address for f in fields)


def is_auto_generated(email: dict, own_address: str) -> bool:
    """自动回复、退信、邮件列表、noreply、自己发给自己：一律不回复。"""
    sender = sender_address(email)
    if not sender or sender == own_address:
        return True
    if AUTO_LOCALPART.match(sender.split("@")[0]):
        return True
    headers = lower_headers(email)
    if headers.get("auto-submitted", "no").strip().lower() != "no":
        return True
    if headers.get("precedence", "").strip().lower() in AUTO_PRECEDENCE:
        return True
    return any(key in headers for key in AUTO_HEADERS)


def is_spoofed(email: dict) -> bool:
    """DMARC 校验失败说明发件人很可能是伪造的，回信会打到被冒充的人（backscatter）。"""
    return str((email.get("authentication") or {}).get("dmarc") or "").lower() == "fail"


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    # blockquote 里是引用的历史邮件，和 script/style 一样整体跳过
    _SKIP = {"script", "style", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """HTML 转纯文本。Resend 可能以 data URI 形式返回 html（html_format = data_uri），先解码。"""
    if markup.startswith("data:"):
        header, _, payload = markup.partition(",")
        try:
            if ";base64" in header:
                markup = base64.b64decode(payload).decode("utf-8", "replace")
            else:
                markup = unquote(payload)
        except ValueError:  # binascii.Error 是 ValueError 子类：base64 损坏的正文按空处理
            markup = ""
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_quoted(text: str) -> str:
    """去掉引用的历史内容：以 > 开头的行，以及回复头（On ... wrote: 等）之后的全部内容。"""
    kept: list[str] = []
    for line in text.splitlines():
        if QUOTE_HEADER.match(line):
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def extract_body(email: dict) -> str:
    """最新一封邮件的正文（纯文本、已剥离引用历史）。"""
    # 纯空白的 text 部分视为没有，回退到 html
    text = (email.get("text") or "").strip() or html_to_text(email.get("html") or "")
    return strip_quoted(text)


def detect_lang(text: str) -> str:
    """粗略判断来信语言：中文字符信息量大，按 1 个汉字 ≈ 3 个字母计权。"""
    cjk = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk and cjk * 3 >= latin else "en"


def has_attachments(email: dict) -> bool:
    """是否带真正的附件（inline 的签名图片等不算）。"""
    return any(
        (att.get("content_disposition") or "").lower() != "inline"
        for att in email.get("attachments") or []
    )


def precheck(body: str, has_attachments: bool, max_chars: int) -> str | None:
    """不需要 LLM 就能判定的无效邮件，返回对应模板类别；正常邮件返回 None。"""
    if not body.strip():
        return "attachment_only" if has_attachments else "empty"
    if len(body) > max_chars:
        return "too_long"
    return None
