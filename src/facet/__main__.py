"""Process entry: load env, then run the Discord gateway client."""

from __future__ import annotations

import logging
import sys

from facet.bot import run
from facet.config import load_config


class _RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[redacted]")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    config = load_config()
    redact = _RedactFilter([config.xai_api_key, config.discord_token])
    logging.getLogger().addFilter(redact)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redact)
    run(config)


if __name__ == "__main__":
    main()
