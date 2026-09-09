# Facet

Grok-powered Discord bot by Plygon (Plygonality). Mention it, reply to it, or talk in a thread it already joined. It calls the xAI Grok API and answers as plain Discord messages.

There is no official xAI Discord bot. Facet is a private client you run yourself.

Suggested Discord application description:

> Grok-backed Discord agent. Mention or reply to talk. Thread-scoped memory, image read, hard rate limits. Built for Plygon servers.

## Setup

### 1. Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Open the Bot tab, create a bot, and copy the bot token. That is `DISCORD_TOKEN`.
3. Enable the **Message Content Intent**. This is a privileged gateway intent. Without it the bot cannot read message text and cannot see mentions, replies, or thread chatter.
4. Invite the bot with scopes `bot` and `applications.commands`. Grant at least: View Channels, Send Messages, Send Messages in Threads, Read Message History.

Example invite URL (replace `CLIENT_ID`):

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=274877975552&scope=bot%20applications.commands
```

`274877975552` is View Channels + Send Messages + Read Message History + Send Messages in Threads.

### 2. xAI API key

Create `XAI_API_KEY` at [console.x.ai](https://console.x.ai). Facet talks to `https://api.x.ai/v1` with the OpenAI-compatible Chat Completions API.

### 3. Environment file

```
cp .env.example .env
```

Fill in `XAI_API_KEY`, `DISCORD_TOKEN`, and `DISCORD_GUILD_IDS`.

### 4. Run

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

```
uv sync
uv run facet
```

Facet is a Discord gateway client. It does not bind a TCP port and it does not serve HTTP.

## Environment variables

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `XAI_API_KEY` | yes | none | xAI API key. Startup fails if missing. Never logged. |
| `DISCORD_TOKEN` | yes | none | Discord bot token. Startup fails if missing. Never logged. |
| `GROK_MODEL` | no | `grok-4.6` | Chat Completions model id. `/model` changes this for the running process. |
| `DISCORD_GUILD_IDS` | no | empty | Comma-separated guild snowflakes. Empty refuses every guild. |
| `DISCORD_ALLOW_USER_IDS` | no | empty | Optional user allowlist. Empty allows every user in an allowed guild. |
| `FACET_HISTORY` | no | `12` | Last N stored messages per channel or thread (user and assistant each count as one turn). |
| `FACET_THREAD_AUTO` | no | `0` | `1` replies in threads the bot has already joined, without a mention. |
| `FACET_SYSTEM_PROMPT` | no | built-in | Path to a UTF-8 file that replaces the shipped system prompt. |

Missing `XAI_API_KEY` or `DISCORD_TOKEN` is a hard startup error. Secrets stay in `.env`, which is gitignored.

## Behavior

Facet replies only when:

1. the bot is mentioned, or
2. the message is a reply to the bot, or
3. the message is in a thread the bot already joined and `FACET_THREAD_AUTO=1`.

It ignores other messages, other bots, and `@everyone` / `@here` pings that do not mention the bot. Direct messages are ignored.

Memory is scoped per guild channel. Messages in a thread use the thread id, not the parent channel. History is JSON under `./data/` (gitignored). `/reset` clears that scope.

Grok sees the system prompt, the last N turns, and the current user message. Each turn is labeled with Discord display name and user id. The bot mention is stripped before the request. PNG, JPEG, and WebP attachments on the triggering message, or on the replied-to message, are sent as vision parts. Videos are skipped.

Replies are plain text, split near 2000 characters on paragraph boundaries. A typing indicator runs while Grok works. On API failure the channel gets one short error. The exception is logged locally, never dumped in Discord.

Rate limit: 6 Grok calls per user per 60 seconds. Over that, Facet replies `rate limited` and stops.

Slash commands:

- `/reset` clears history for the current channel or thread.
- `/status` shows model, history length, and allowlist state.
- `/model [name]` is owner-only and sets `GROK_MODEL` for the process.

Owner means the Discord application owner (or team owners), via `Bot.is_owner`.

## Tests

```
uv sync
uv run pytest
```

Tests cover split, allowlists, rate limits, and JSON memory. They do not connect to Discord.

## License

MIT. Copyright 2026 Plygon.
