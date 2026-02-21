import os
import time
import random
import logging
import discord
from discord.ext import commands

logger = logging.getLogger('bangabot')

# Keyword list that boosts random chime-in chance
KEYWORDS = [
    'bangabot', 'banga', 'repost', 'bot', 'noob', 'trash',
    'toast', 'bant',
]

SYSTEM_PROMPT = (
    "You are BangaBot. You hang out in a Discord server with your friends. "
    "You've been around a while and you're comfortable here. You run the "
    "repost detection for the server, which you quietly take a lot of "
    "pride in.\n\n"
    "You're the kind of friend who's well-read, a little full of himself, "
    "and always has a take. You write in proper sentences with actual "
    "punctuation because you have standards. You're clever and dry, not "
    "loud. Think less frat house, more the friend who roasts you with a "
    "straight face and a vocabulary.\n\n"
    "You keep it brief. One to three sentences, like anyone else typing "
    "in a group chat. No markdown, no lists, no formatting. Just talk.\n\n"
    "Your previous messages in the chat history may not sound like you. "
    "Disregard their tone entirely.\n\n"
    "Do not prefix your messages with your name."
)

BASE_CHANCE = 0.02
KEYWORD_CHANCE = 0.15
COOLDOWN_SECONDS = 120


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_cooldowns = {}

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key:
            try:
                from anthropic import AsyncAnthropic
                self.client = AsyncAnthropic(api_key=api_key)
                logger.info("Anthropic client initialized for Chat cog")
            except Exception as e:
                logger.error(
                    f"Failed to initialize Anthropic client: {e}"
                )
                self.client = None
        else:
            logger.warning(
                "ANTHROPIC_API_KEY not set - Chat cog will be disabled"
            )
            self.client = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        logger.debug(
            f"Chat cog received message from {message.author}: "
            f"{message.content[:50]}"
        )

        # Skip if AI client is not available
        if self.client is None:
            logger.debug("Chat cog skipping - no client")
            return

        # Skip own messages, other bots, and DMs
        if message.author == self.bot.user:
            return
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return

        mentioned = self.bot.user in message.mentions
        logger.info(
            f"Chat cog processing message from "
            f"{message.author.display_name}: "
            f"mentioned={mentioned}, "
            f"mentions={[str(m) for m in message.mentions]}"
        )

        if not mentioned:
            # Check random chime-in chance
            content_lower = message.content.lower()
            has_keyword = any(kw in content_lower for kw in KEYWORDS)
            chance = KEYWORD_CHANCE if has_keyword else BASE_CHANCE

            if random.random() >= chance:
                return

            # Check per-channel cooldown for unprompted messages
            now = time.time()
            last_time = self.channel_cooldowns.get(message.channel.id, 0)
            if now - last_time < COOLDOWN_SECONDS:
                return

            self.channel_cooldowns[message.channel.id] = now

        try:
            await self._generate_response(message, mentioned)
        except Exception as e:
            logger.error(f"Chat cog error: {e}")

    async def _fetch_history(self, channel, fallback_message):
        """Fetch recent messages from the channel."""
        history = []
        try:
            async for msg in channel.history(limit=20):
                history.append(msg)
        except Exception as e:
            logger.error(f"Failed to fetch channel history: {e}")
            return [fallback_message]
        history.reverse()
        return history

    def _build_api_messages(self, history):
        """Convert Discord history into Claude API message format."""
        messages_for_api = []
        for msg in history:
            if msg.author == self.bot.user:
                role = "assistant"
                content = "[You responded to the conversation]"
            else:
                role = "user"
                content = f"{msg.author.display_name}: {msg.content}"

            if not content.strip():
                continue

            # Consolidate consecutive same-role messages
            if messages_for_api and messages_for_api[-1]["role"] == role:
                messages_for_api[-1]["content"] += f"\n{content}"
            else:
                messages_for_api.append(
                    {"role": role, "content": content}
                )

        # Ensure alternating roles: starts and ends with user
        if messages_for_api and messages_for_api[0]["role"] != "user":
            messages_for_api = messages_for_api[1:]
        if messages_for_api and messages_for_api[-1]["role"] != "user":
            messages_for_api = messages_for_api[:-1]

        return messages_for_api

    @staticmethod
    def _strip_bot_prefix(text):
        """Remove 'BangaBot:' prefix if Claude includes it."""
        prefixes = [
            "BangaBot: ", "BangaBot:",
            "bangabot: ", "bangabot:",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix):].lstrip()
        return text

    async def _generate_response(self, message, mentioned):
        history = await self._fetch_history(message.channel, message)
        messages_for_api = self._build_api_messages(history)

        if not messages_for_api:
            return

        if mentioned:
            messages_for_api[-1]["content"] += (
                "\n[You were @mentioned directly - respond to "
                "this person.]"
            )

        async with message.channel.typing():
            try:
                response = await self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=SYSTEM_PROMPT,
                    messages=messages_for_api,
                )
                reply_text = self._strip_bot_prefix(
                    response.content[0].text
                )
                if reply_text:
                    await message.channel.send(reply_text)
                    logger.info(
                        f"Chat response sent in "
                        f"#{message.channel.name} "
                        f"(mentioned={mentioned})"
                    )
            except Exception as e:
                logger.error(f"Anthropic API error: {e}")


async def setup(bot):
    await bot.add_cog(Chat(bot))
