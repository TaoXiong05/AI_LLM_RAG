"""Resend REST API 的最小封装：列出 / 读取收到的邮件、发送邮件。

只用到 3 个接口，直接用 httpx 调，不引入 resend SDK。
文档：https://resend.com/docs/api-reference/emails/list-received-emails
"""
import httpx

API_BASE = "https://api.resend.com"


class ResendClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            transport=transport,
        )

    def list_received(self, limit: int = 100) -> list[dict]:
        """最近收到的邮件摘要（按时间倒序，最新的在前）。"""
        resp = self._http.get("/emails/receiving", params={"limit": limit})
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_received(self, email_id: str) -> dict:
        """单封收到邮件的完整内容（text / html / headers / attachments 元数据等）。"""
        resp = self._http.get(f"/emails/receiving/{email_id}")
        resp.raise_for_status()
        return resp.json()

    def send(
        self,
        *,
        from_: str,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """发送邮件（纯文本，可附带 HTML 版本），返回 Resend 邮件 id。

        idempotency_key：24 小时内同一个 key 只会真正发送一次，worker 崩溃后重试不会重复发信。
        """
        body: dict = {"from": from_, "to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        if headers:
            body["headers"] = headers
        request_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        resp = self._http.post("/emails", json=body, headers=request_headers)
        resp.raise_for_status()
        return resp.json()["id"]
