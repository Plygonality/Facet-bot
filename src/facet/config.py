"""Load and validate process config from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "grok-4.6"
DEFAULT_HISTORY = 12
XAI_BASE_URL = "https://api.x.ai/v1"
GROK_TIMEOUT_S = 120.0
RATE_MAX_CALLS = 6
RATE_WINDOW_S = 60.0
DISCORD_CONTENT_LIMIT = 2000
MAX_VISION_IMAGES = 8
MAX_VISION_BYTES = 20 * 1024 * 1024

DEFAULT_SYSTEM_PROMPT = """You are Facet, a Grok instance in Discord, built by Plygon.
Direct. Specific. No filler, no motivational closers, no moralizing.
Match the user's language (Dutch or English).
No em-dashes. Use commas, colons, periods, parentheses.
Do not claim to be official xAI.
Do not execute shell, browse the host, or invent tool results. Text and vision only in v1.
If asked for methods of crime, weapons, or self-harm, refuse and stop."""


@dataclass
class Config:
    xai_api_key: str = field(repr=False)
    discord_token: str = field(repr=False)
    grok_model: str
    history_limit: int
    thread_auto: bool
    system_prompt: str
    guild_ids: frozenset[int]
    allow_user_ids: frozenset[int]
    data_dir: Path


def load_config() -> Config:
    load_dotenv()

    missing: list[str] = []
    api_key = _required("XAI_API_KEY", missing)
    token = _required("DISCORD_TOKEN", missing)
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Missing required env: {names}")

    model = os.getenv("GROK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    history = _positive_int("FACET_HISTORY", os.getenv("FACET_HISTORY", str(DEFAULT_HISTORY)))
    thread_auto = _bool_env("FACET_THREAD_AUTO", os.getenv("FACET_THREAD_AUTO", "0"))
    prompt = _system_prompt(os.getenv("FACET_SYSTEM_PROMPT", "").strip())
    guild_ids = parse_snowflakes(os.getenv("DISCORD_GUILD_IDS", ""), "DISCORD_GUILD_IDS")
    allow_user_ids = parse_snowflakes(
        os.getenv("DISCORD_ALLOW_USER_IDS", ""), "DISCORD_ALLOW_USER_IDS"
    )

    return Config(
        xai_api_key=api_key,
        discord_token=token,
        grok_model=model,
        history_limit=history,
        thread_auto=thread_auto,
        system_prompt=prompt,
        guild_ids=guild_ids,
        allow_user_ids=allow_user_ids,
        data_dir=Path("data"),
    )


def parse_snowflakes(raw: str, name: str) -> frozenset[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            raise SystemExit(f"{name} contains a non-integer id: {part!r}") from None
        if value < 0:
            raise SystemExit(f"{name} contains a negative id: {part!r}")
        ids.append(value)
    return frozenset(ids)


def _required(name: str, missing: list[str]) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        missing.append(name)
    return value


def _positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise SystemExit(f"{name} must be >= 1, got {value}")
    return value


def _bool_env(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise SystemExit(f"{name} must be 0 or 1, got {raw!r}")


def _system_prompt(path_value: str) -> str:
    if not path_value:
        return DEFAULT_SYSTEM_PROMPT
    path = Path(path_value)
    if not path.is_file():
        raise SystemExit(f"FACET_SYSTEM_PROMPT is not a file: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"FACET_SYSTEM_PROMPT is empty: {path}")
    return text
