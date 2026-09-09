import json
from pathlib import Path

from facet.grok import image_media_type, is_retriable_status, pack_messages
from facet.memory import Memory, scope_key


def test_scope_key_is_guild_and_channel() -> None:
    assert scope_key(1, 2) == "1-2"
    assert scope_key(10, 99) != scope_key(10, 100)


def test_append_persists_json(tmp_path: Path) -> None:
    mem = Memory(tmp_path, history_limit=12)
    mem.append("1-2", {"role": "user", "content": "hi", "name": "Emil", "user_id": "9"})
    mem.append("1-2", {"role": "assistant", "content": "hello"})
    path = tmp_path / "1-2.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["turns"]) == 2
    assert data["turns"][0]["name"] == "Emil"


def test_separate_scopes(tmp_path: Path) -> None:
    mem = Memory(tmp_path, history_limit=12)
    mem.append("1-10", {"role": "user", "content": "channel"})
    mem.append("1-11", {"role": "user", "content": "thread"})
    assert mem.load("1-10")[0]["content"] == "channel"
    assert mem.load("1-11")[0]["content"] == "thread"


def test_trims_to_history_limit(tmp_path: Path) -> None:
    mem = Memory(tmp_path, history_limit=4)
    for i in range(6):
        mem.append("g-c", {"role": "user", "content": str(i)})
    turns = mem.load("g-c")
    assert [t["content"] for t in turns] == ["2", "3", "4", "5"]
    reloaded = Memory(tmp_path, history_limit=4)
    assert [t["content"] for t in reloaded.load("g-c")] == ["2", "3", "4", "5"]


def test_reset_clears_file_and_cache(tmp_path: Path) -> None:
    mem = Memory(tmp_path, history_limit=12)
    mem.append("9-9", {"role": "user", "content": "keep me"})
    mem.reset("9-9")
    assert mem.load("9-9") == []
    assert not (tmp_path / "9-9.json").exists()


def test_pack_messages_labels_turns() -> None:
    history = [{"role": "user", "content": "hi", "name": "Emil", "user_id": "9"}]
    packed = pack_messages(
        "sys",
        history,
        user_name="Emil",
        user_id="9",
        user_text="@bot later",
        images=[],
    )
    assert packed[0] == {"role": "system", "content": "sys"}
    assert packed[1] == {"role": "user", "content": "Emil (9): hi"}
    assert packed[2] == {"role": "user", "content": "Emil (9): @bot later"}


def test_pack_messages_includes_vision_parts() -> None:
    packed = pack_messages(
        "sys",
        [],
        user_name="Emil",
        user_id="9",
        user_text="",
        images=[(b"\x89PNG", "image/png")],
    )
    content = packed[1]["content"]
    assert content[0] == {"type": "text", "text": "Emil (9): (no text)"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_image_types_skip_video() -> None:
    assert image_media_type("x.png", "image/png") == "image/png"
    assert image_media_type("x.jpg", "image/jpg") == "image/jpeg"
    assert image_media_type("x.webp", None) == "image/webp"
    assert image_media_type("clip.mp4", "video/mp4") is None
    assert image_media_type("clip.mp4", None) is None


def test_retriable_http_statuses() -> None:
    assert is_retriable_status(429) is True
    assert is_retriable_status(500) is True
    assert is_retriable_status(503) is True
    assert is_retriable_status(400) is False
    assert is_retriable_status(401) is False
