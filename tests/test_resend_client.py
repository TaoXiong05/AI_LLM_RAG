"""轻量测试：Resend REST 客户端（用 httpx.MockTransport，不发真实请求）。

运行：
    python tests/test_resend_client.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from backend.resend_client import ResendClient


def _client(handler) -> ResendClient:
    return ResendClient("re_test", transport=httpx.MockTransport(handler))


def test_list_received_returns_data_and_sends_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"object": "list", "has_more": False, "data": [{"id": "e1"}]})

    assert _client(handler).list_received(limit=50) == [{"id": "e1"}]
    assert seen["auth"] == "Bearer re_test"
    assert seen["url"] == "https://api.resend.com/emails/receiving?limit=50"


def test_get_received():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/emails/receiving/e1"
        return httpx.Response(200, json={"id": "e1", "text": "hi"})

    assert _client(handler).get_received("e1")["text"] == "hi"


def test_send_posts_body_and_idempotency_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("Idempotency-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "sent1"})

    sent_id = _client(handler).send(
        from_="S <s@x.com>",
        to="a@y.com",
        subject="Re: q",
        text="body",
        headers={"In-Reply-To": "<m>"},
        idempotency_key="reply-e1",
    )
    assert sent_id == "sent1"
    assert seen["path"] == "/emails"
    assert seen["key"] == "reply-e1"
    assert seen["body"] == {
        "from": "S <s@x.com>",
        "to": ["a@y.com"],
        "subject": "Re: q",
        "text": "body",
        "headers": {"In-Reply-To": "<m>"},
    }


def test_send_includes_html_when_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "sent2"})

    _client(handler).send(from_="S <s@x.com>", to="a@y.com", subject="s", text="t", html="<p>t</p>")
    assert seen["body"]["html"] == "<p>t</p>" and seen["body"]["text"] == "t"


def test_http_errors_raise():
    client = _client(lambda request: httpx.Response(500, json={"message": "boom"}))
    try:
        client.list_received()
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: resend client tests passed")
