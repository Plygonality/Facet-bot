"""Split model output to Discord's per-message character limit."""

from __future__ import annotations

from facet.config import DISCORD_CONTENT_LIMIT


def split_message(text: str, limit: int = DISCORD_CONTENT_LIMIT) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return ["(empty response)"]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit]
        cut = _best_cut(window, limit)
        piece = remaining[:cut].strip()
        if not piece:
            piece = remaining[:limit]
            cut = limit
        chunks.append(piece)
        remaining = remaining[cut:].lstrip()
    return chunks


def _best_cut(window: str, limit: int) -> int:
    floor = max(1, limit // 2)
    for needle, extra in (("\n\n", 0), ("\n", 0), (". ", 1), ("? ", 1), ("! ", 1), (" ", 0)):
        idx = window.rfind(needle)
        if idx >= floor:
            return idx + extra
    return limit
