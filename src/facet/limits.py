"""Guild and user allowlists plus per-user Grok rate limits."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

from facet.config import RATE_MAX_CALLS, RATE_WINDOW_S


def guild_allowed(guild_id: int | None, allowed: frozenset[int]) -> bool:
    if guild_id is None:
        return False
    return guild_id in allowed


def user_allowed(user_id: int, allowed: frozenset[int]) -> bool:
    if not allowed:
        return True
    return user_id in allowed


def is_activated(
    *,
    author_is_bot: bool,
    bot_mentioned: bool,
    reply_to_bot: bool,
    in_joined_thread: bool,
    thread_auto: bool,
) -> bool:
    if author_is_bot:
        return False
    if bot_mentioned or reply_to_bot:
        return True
    return thread_auto and in_joined_thread


class RateLimiter:
    def __init__(
        self,
        max_calls: int = RATE_MAX_CALLS,
        window_s: float = RATE_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_calls = max_calls
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[int, list[float]] = defaultdict(list)

    def allow(self, user_id: int) -> bool:
        now = self._clock()
        cutoff = now - self.window_s
        hits = [t for t in self._hits[user_id] if t > cutoff]
        if len(hits) >= self.max_calls:
            self._hits[user_id] = hits
            return False
        hits.append(now)
        self._hits[user_id] = hits
        return True
