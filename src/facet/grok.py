"""xAI Grok client. Chat Completions now, Responses later, same Discord call site."""

from __future__ import annotations

import asyncio
import base64
import logging
import random
from typing import Any

from openai import APIStatusError, AsyncOpenAI

from facet.config import GROK_TIMEOUT_S, XAI_BASE_URL

log = logging.getLogger(__name__)

VISION_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_EXT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def is_retriable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def image_media_type(filename: str, content_type: str | None) -> str | None:
    if content_type:
        media = content_type.split(";", 1)[0].strip().lower()
        if media.startswith("video/"):
            return None
        if media == "image/jpg":
            media = "image/jpeg"
        if media in VISION_TYPES:
            return media
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    return _EXT_TYPES.get(ext)


def pack_messages(
    system_prompt: str,
    history: list[dict[str, Any]],
    *,
    user_name: str,
    user_id: str,
    user_text: str,
    images: list[tuple[bytes, str]],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for turn in history:
        role = turn.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = str(turn.get("content") or "")
        if role == "user":
            name = str(turn.get("name") or "user")
            uid = str(turn.get("user_id") or "0")
            content = f"{name} ({uid}): {content}"
        messages.append({"role": role, "content": content})
    body = user_text if user_text else "(no text)"
    labeled = f"{user_name} ({user_id}): {body}"
    if not images:
        messages.append({"role": "user", "content": labeled})
        return messages
    parts: list[dict[str, Any]] = [{"type": "text", "text": labeled}]
    for data, media in images:
        b64 = base64.standard_b64encode(data).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{b64}", "detail": "high"},
            }
        )
    messages.append({"role": "user", "content": parts})
    return messages


class GrokClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=XAI_BASE_URL,
            timeout=GROK_TIMEOUT_S,
            max_retries=0,
        )

    async def complete(self, messages: list[dict[str, Any]], model: str) -> str:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await self._chat(messages, model)
            except APIStatusError as exc:
                last_error = exc
                if attempt == 0 and is_retriable_status(exc.status_code):
                    delay = random.uniform(0.4, 1.6)
                    log.warning(
                        "Grok HTTP %s, retrying once in %.2fs",
                        exc.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
        assert last_error is not None
        raise last_error

    async def _chat(self, messages: list[dict[str, Any]], model: str) -> str:
        # Chat Completions is the v1 transport. Swap this method for Responses later.
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
        )
        if not response.choices:
            raise RuntimeError("Grok returned no choices")
        text = response.choices[0].message.content
        return text or ""

    async def aclose(self) -> None:
        await self._client.close()
