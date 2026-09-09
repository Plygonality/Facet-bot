"""JSON conversation history, one file per Discord channel or thread."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def scope_key(guild_id: int, channel_id: int) -> str:
    return f"{guild_id}-{channel_id}"


class Memory:
    def __init__(self, data_dir: Path, history_limit: int) -> None:
        self.data_dir = data_dir
        self.history_limit = history_limit
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def load(self, scope: str) -> list[dict[str, Any]]:
        if scope in self._cache:
            return self._cache[scope]
        path = self._path(scope)
        if not path.is_file():
            self._cache[scope] = []
            return self._cache[scope]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Failed to read history %s", path)
            self._cache[scope] = []
            return self._cache[scope]
        turns = raw.get("turns", [])
        if not isinstance(turns, list):
            turns = []
        self._cache[scope] = [t for t in turns if isinstance(t, dict)]
        return self._cache[scope]

    def append(self, scope: str, turn: dict[str, Any]) -> None:
        turns = self.load(scope)
        turns.append(turn)
        overflow = len(turns) - self.history_limit
        if overflow > 0:
            del turns[:overflow]
        self._write(scope, turns)

    def reset(self, scope: str) -> None:
        self._cache[scope] = []
        path = self._path(scope)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.exception("Failed to delete history %s", path)

    def _path(self, scope: str) -> Path:
        return self.data_dir / f"{scope}.json"

    def _write(self, scope: str, turns: list[dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(scope)
        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps({"turns": turns}, ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
