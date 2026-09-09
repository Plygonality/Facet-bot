import pytest

from facet.config import DEFAULT_SYSTEM_PROMPT, load_config, parse_snowflakes
from facet.limits import RateLimiter, guild_allowed, is_activated, user_allowed


def test_empty_guild_allowlist_refuses_all() -> None:
    allowed: frozenset[int] = frozenset()
    assert guild_allowed(1, allowed) is False
    assert guild_allowed(None, allowed) is False


def test_guild_allowlist_membership() -> None:
    allowed = frozenset({111, 222})
    assert guild_allowed(111, allowed) is True
    assert guild_allowed(333, allowed) is False
    assert guild_allowed(None, allowed) is False


def test_empty_user_allowlist_allows_everyone() -> None:
    allowed: frozenset[int] = frozenset()
    assert user_allowed(1, allowed) is True
    assert user_allowed(99, allowed) is True


def test_user_allowlist_restricts() -> None:
    allowed = frozenset({7})
    assert user_allowed(7, allowed) is True
    assert user_allowed(8, allowed) is False


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_rate_limit_six_per_sixty_seconds() -> None:
    clock = _Clock()
    limiter = RateLimiter(clock=clock)
    user = 42
    for _ in range(6):
        assert limiter.allow(user) is True
    assert limiter.allow(user) is False
    clock.t = 59.9
    assert limiter.allow(user) is False
    clock.t = 60.1
    assert limiter.allow(user) is True


def test_rate_limit_is_per_user() -> None:
    clock = _Clock()
    limiter = RateLimiter(clock=clock)
    for _ in range(6):
        assert limiter.allow(1) is True
    assert limiter.allow(1) is False
    assert limiter.allow(2) is True


def test_other_bots_never_activate() -> None:
    assert (
        is_activated(
            author_is_bot=True,
            bot_mentioned=True,
            reply_to_bot=True,
            in_joined_thread=True,
            thread_auto=True,
        )
        is False
    )


def test_mention_or_reply_activates() -> None:
    base = dict(
        author_is_bot=False,
        bot_mentioned=False,
        reply_to_bot=False,
        in_joined_thread=False,
        thread_auto=False,
    )
    assert is_activated(**base) is False
    assert is_activated(**{**base, "bot_mentioned": True}) is True
    assert is_activated(**{**base, "reply_to_bot": True}) is True


def test_everyone_here_only_does_not_activate() -> None:
    assert (
        is_activated(
            author_is_bot=False,
            bot_mentioned=False,
            reply_to_bot=False,
            in_joined_thread=False,
            thread_auto=False,
        )
        is False
    )


def test_thread_auto_only_if_joined() -> None:
    assert (
        is_activated(
            author_is_bot=False,
            bot_mentioned=False,
            reply_to_bot=False,
            in_joined_thread=True,
            thread_auto=True,
        )
        is True
    )
    assert (
        is_activated(
            author_is_bot=False,
            bot_mentioned=False,
            reply_to_bot=False,
            in_joined_thread=True,
            thread_auto=False,
        )
        is False
    )
    assert (
        is_activated(
            author_is_bot=False,
            bot_mentioned=False,
            reply_to_bot=False,
            in_joined_thread=False,
            thread_auto=True,
        )
        is False
    )


def test_parse_snowflakes() -> None:
    assert parse_snowflakes("", "IDS") == frozenset()
    assert parse_snowflakes(" 1, 2,2 ", "IDS") == frozenset({1, 2})
    with pytest.raises(SystemExit):
        parse_snowflakes("nope", "IDS")


def test_system_prompt_has_no_emdash() -> None:
    assert "\u2014" not in DEFAULT_SYSTEM_PROMPT
    assert "\u2013" not in DEFAULT_SYSTEM_PROMPT


def test_missing_secrets_fail_loud(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "")
    monkeypatch.setenv("DISCORD_TOKEN", "")
    with pytest.raises(SystemExit, match="Missing required env"):
        load_config()


def test_load_config_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
    monkeypatch.setenv("DISCORD_TOKEN", "discord-test-token")
    for name in (
        "GROK_MODEL",
        "FACET_HISTORY",
        "FACET_THREAD_AUTO",
        "FACET_SYSTEM_PROMPT",
        "DISCORD_GUILD_IDS",
        "DISCORD_ALLOW_USER_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    cfg = load_config()
    assert cfg.grok_model == "grok-4.6"
    assert cfg.history_limit == 12
    assert cfg.thread_auto is False
    assert cfg.guild_ids == frozenset()
    assert cfg.allow_user_ids == frozenset()
    assert "Plygon" in cfg.system_prompt
    assert cfg.xai_api_key == "xai-test-key"
