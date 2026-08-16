"""基于视觉大模型的 OCR：把图片（扫描页、文档内图片、纯图片）转成文字。

复用当前 .env 里的 OpenAI 兼容端点（Google Gemini），使用独立的 OCR_MODEL，
避免挤占对话模型的额度，也便于单独调参 / 换更擅长视觉的模型。
"""
import base64
import io
from functools import lru_cache

from openai import OpenAI

from config import settings

OCR_PROMPT = (
    "你是一个高精度 OCR 引擎。请把图片中的全部文字原样提取出来，"
    "保留原有的段落与换行；如果图片里没有文字，只回复“（无文字）”。"
    "只输出识别到的文字本身，不要添加任何解释或客套话。"
)

# MIME 嗅探兜底
_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "TIFF": "image/tiff",
}


@lru_cache(maxsize=1)
def get_ocr_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=180.0,
    )


def _sniff_mime(image_bytes: bytes) -> str:
    """尽量从图片字节推断 MIME，失败时默认 PNG。"""
    try:  # noqa: BLE001 - 嗅探失败就回退默认
        from PIL import Image

        fmt = Image.open(io.BytesIO(image_bytes)).format or ""
        return _MIME_BY_FORMAT.get(fmt.upper(), "image/png")
    except Exception:
        return "image/png"


def ocr_image(image_bytes: bytes, mime: str | None = None) -> str:
    """把单张图片交给视觉模型识别文字，返回识别出的文本。"""
    if not image_bytes:
        return ""
    mime = mime or _sniff_mime(image_bytes)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    resp = get_ocr_client().chat.completions.create(
        model=settings.ocr_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )
    return (resp.choices[0].message.content or "").strip()