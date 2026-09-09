from facet.split import split_message


def test_empty_becomes_placeholder() -> None:
    assert split_message("") == ["(empty response)"]
    assert split_message("   \n") == ["(empty response)"]


def test_short_message_unchanged() -> None:
    assert split_message("hello") == ["hello"]


def test_prefers_paragraph_boundary() -> None:
    first = "a" * 100 + "\n\n" + "b" * 50
    second = "c" * 80
    text = first + "\n\n" + second
    chunks = split_message(text, limit=180)
    assert len(chunks) == 2
    assert chunks[0] == first
    assert chunks[1] == second


def test_falls_back_to_newline_then_space() -> None:
    text = ("word " * 30).strip()
    chunks = split_message(text, limit=40)
    assert all(len(c) <= 40 for c in chunks)
    assert "".join(c.replace(" ", "") for c in chunks) == text.replace(" ", "")


def test_hard_cuts_long_token() -> None:
    text = "x" * 50
    chunks = split_message(text, limit=20)
    assert chunks == ["x" * 20, "x" * 20, "x" * 10]


def test_discord_limit_exactly_2000() -> None:
    text = "y" * 2000
    assert split_message(text) == [text]


def test_over_discord_limit_splits() -> None:
    text = "z" * 2001
    chunks = split_message(text)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == text


def test_strips_crlf() -> None:
    first = "a" * 8
    second = "b" * 8
    assert split_message(first + "\r\n\r\n" + second, limit=12) == [first, second]
