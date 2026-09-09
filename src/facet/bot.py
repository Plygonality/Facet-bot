"""Discord gateway client and slash commands."""

from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from facet.config import MAX_VISION_BYTES, MAX_VISION_IMAGES, Config
from facet.grok import GrokClient, image_media_type, pack_messages
from facet.limits import RateLimiter, guild_allowed, is_activated, user_allowed
from facet.memory import Memory, scope_key
from facet.split import split_message

log = logging.getLogger(__name__)


def strip_bot_mention(text: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{bot_id}>\s*", "", text).strip()


class FacetBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.config = config
        self.memory = Memory(config.data_dir, config.history_limit)
        self.grok = GrokClient(config.xai_api_key)
        self.limiter = RateLimiter()
        self._locks: dict[str, asyncio.Lock] = {}
        self._register_commands()

    def _register_commands(self) -> None:
        @self.tree.command(name="reset", description="Clear Facet history for this channel or thread")
        async def reset(interaction: discord.Interaction) -> None:
            if await self._reject_command(interaction):
                return
            scope = self._scope(interaction)
            async with self._lock(scope):
                self.memory.reset(scope)
            where = "thread" if isinstance(interaction.channel, discord.Thread) else "channel"
            await interaction.response.send_message(
                f"History cleared for this {where}.",
                ephemeral=True,
            )

        @self.tree.command(name="status", description="Show Facet model, history, and allowlist state")
        async def status(interaction: discord.Interaction) -> None:
            if await self._reject_command(interaction):
                return
            scope = self._scope(interaction)
            n = len(self.memory.load(scope))
            guild_state = (
                f"{len(self.config.guild_ids)} guild(s)"
                if self.config.guild_ids
                else "empty (all guilds refused)"
            )
            user_state = (
                f"{len(self.config.allow_user_ids)} user(s)"
                if self.config.allow_user_ids
                else "off (all users in allowed guilds)"
            )
            lines = [
                f"model: {self.config.grok_model}",
                f"history: {n}/{self.config.history_limit} turns",
                f"guild allowlist: {guild_state}",
                f"user allowlist: {user_state}",
                f"thread auto: {'on' if self.config.thread_auto else 'off'}",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        @self.tree.command(name="model", description="Set GROK_MODEL for this process (owner only)")
        @app_commands.describe(name="xAI model id, for example grok-4.6")
        async def model_cmd(interaction: discord.Interaction, name: str) -> None:
            if await self._reject_command(interaction):
                return
            if not await self.is_owner(interaction.user):
                await interaction.response.send_message("Owner only.", ephemeral=True)
                return
            model = name.strip()
            if not model:
                await interaction.response.send_message("Model name is empty.", ephemeral=True)
                return
            self.config.grok_model = model
            await interaction.response.send_message(f"Model set to {model}.", ephemeral=True)

    async def setup_hook(self) -> None:
        if self.config.guild_ids:
            for guild_id in self.config.guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self) -> None:
        await self.grok.aclose()
        await super().close()

    async def on_ready(self) -> None:
        user = self.user
        log.info("Logged in as %s (%s)", user, user.id if user else "?")
        if not self.config.guild_ids:
            log.warning("DISCORD_GUILD_IDS is empty; refusing all guilds")

    async def on_message(self, message: discord.Message) -> None:
        if self.user is None:
            return
        if message.type not in {
            discord.MessageType.default,
            discord.MessageType.reply,
            discord.MessageType.thread_starter_message,
        }:
            return
        if message.guild is None:
            return
        if not guild_allowed(message.guild.id, self.config.guild_ids):
            return
        if not user_allowed(message.author.id, self.config.allow_user_ids):
            return

        replied = await self._resolved_reference(message)
        reply_to_bot = replied is not None and replied.author.id == self.user.id
        in_joined_thread = isinstance(message.channel, discord.Thread) and message.channel.me is not None
        if not is_activated(
            author_is_bot=message.author.bot,
            bot_mentioned=self.user in message.mentions,
            reply_to_bot=reply_to_bot,
            in_joined_thread=in_joined_thread,
            thread_auto=self.config.thread_auto,
        ):
            return

        if isinstance(message.channel, discord.Thread):
            try:
                await message.channel.join()
            except discord.HTTPException:
                log.warning("Could not join thread %s", message.channel.id)

        if not self.limiter.allow(message.author.id):
            await self._send_plain(message, "rate limited")
            return

        user_text = strip_bot_mention(message.content or "", self.user.id)
        images = await self._collect_images(message, replied)
        scope = scope_key(message.guild.id, message.channel.id)
        display = message.author.display_name
        uid = str(message.author.id)

        async with self._lock(scope):
            history = list(self.memory.load(scope))
            packed = pack_messages(
                self.config.system_prompt,
                history,
                user_name=display,
                user_id=uid,
                user_text=user_text,
                images=images,
            )
            try:
                async with message.channel.typing():
                    reply = await self.grok.complete(packed, self.config.grok_model)
            except Exception:
                log.exception("Grok request failed")
                await self._send_plain(message, "Grok request failed. Try again.")
                return
            self.memory.append(
                scope,
                {"role": "user", "content": user_text, "name": display, "user_id": uid},
            )
            self.memory.append(scope, {"role": "assistant", "content": reply})

        await self._send_plain(message, reply)

    async def _reject_command(self, interaction: discord.Interaction) -> bool:
        guild_id = interaction.guild_id
        if not guild_allowed(guild_id, self.config.guild_ids):
            await interaction.response.send_message("This guild is not allowed.", ephemeral=True)
            return True
        if not user_allowed(interaction.user.id, self.config.allow_user_ids):
            await interaction.response.send_message("You are not allowed to use Facet.", ephemeral=True)
            return True
        if interaction.channel is None:
            await interaction.response.send_message("No channel on this interaction.", ephemeral=True)
            return True
        return False

    def _scope(self, interaction: discord.Interaction) -> str:
        assert interaction.guild_id is not None
        assert interaction.channel_id is not None
        return scope_key(interaction.guild_id, interaction.channel_id)

    def _lock(self, scope: str) -> asyncio.Lock:
        lock = self._locks.get(scope)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[scope] = lock
        return lock

    async def _resolved_reference(self, message: discord.Message) -> discord.Message | None:
        ref = message.reference
        if ref is None:
            return None
        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            return resolved
        if ref.message_id is None:
            return None
        try:
            return await message.channel.fetch_message(ref.message_id)
        except (discord.HTTPException, AttributeError):
            return None

    async def _collect_images(
        self,
        message: discord.Message,
        replied: discord.Message | None,
    ) -> list[tuple[bytes, str]]:
        images: list[tuple[bytes, str]] = []
        sources = [message]
        if replied is not None:
            sources.append(replied)
        for source in sources:
            for attachment in source.attachments:
                media = image_media_type(attachment.filename, attachment.content_type)
                if media is None:
                    continue
                if attachment.size and attachment.size > MAX_VISION_BYTES:
                    continue
                try:
                    data = await attachment.read()
                except discord.HTTPException:
                    log.warning("Failed to read attachment %s", attachment.filename)
                    continue
                if len(data) > MAX_VISION_BYTES:
                    continue
                images.append((data, media))
                if len(images) >= MAX_VISION_IMAGES:
                    return images
        return images

    async def _send_plain(self, message: discord.Message, text: str) -> None:
        chunks = split_message(text)
        try:
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk, mention_author=False)
                else:
                    await message.channel.send(chunk)
        except discord.HTTPException:
            log.exception("Failed to send Discord reply")


def run(config: Config) -> None:
    bot = FacetBot(config)
    bot.run(config.discord_token, log_handler=None)
