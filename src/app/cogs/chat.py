import os
import json
import time
import random
import asyncio
import logging
import discord
from datetime import datetime
from discord.ext import commands
from database.orm import UserMemory, BotMemory, UserSentiment

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
ENGAGEMENT_SECONDS = 120
IS_PRODUCTION = (
    os.getenv('ENVIRONMENT', 'prod') == 'prod'
    and 'PR_NUMBER' not in os.environ
)


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_cooldowns = {}
        self.engaged_channels = {}  # channel_id -> last_response_timestamp

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

        # Skip own messages and other bots
        if message.author == self.bot.user:
            return
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)

        # Allow DMs only in dev/test environments
        if is_dm and IS_PRODUCTION:
            return

        mentioned = self.bot.user in message.mentions or is_dm
        logger.info(
            f"Chat cog processing message from "
            f"{message.author.display_name}: "
            f"mentioned={mentioned}, "
            f"mentions={[str(m) for m in message.mentions]}"
        )

        engaged = False
        if not mentioned:
            engaged = await self._check_engagement(message)
            if engaged is None:
                return

        try:
            await self._generate_response(
                message, mentioned, engaged
            )
        except Exception as e:
            logger.error(f"Chat cog error: {e}")

    async def _check_engagement(self, message):
        """Decide whether to respond to a non-mentioned message.

        Returns True if engaged, False if random chime-in,
        or None if the message should be skipped.
        """
        now = time.time()
        channel_id = message.channel.id
        last_engaged = self.engaged_channels.get(channel_id, 0)

        if now - last_engaged < ENGAGEMENT_SECONDS:
            # Channel is engaged — ask Claude if we should respond
            should = await self._should_engage(message)
            if not should:
                return None
            channel_name = (
                getattr(message.channel, 'name', None)
                or 'DM'
            )
            logger.info(
                f"Engagement mode active in "
                f"#{channel_name}"
            )
            return True

        # Clear stale engagement
        self.engaged_channels.pop(channel_id, None)

        # Check random chime-in chance
        content_lower = message.content.lower()
        has_keyword = any(kw in content_lower for kw in KEYWORDS)
        chance = KEYWORD_CHANCE if has_keyword else BASE_CHANCE

        if random.random() >= chance:
            return None

        # Check per-channel cooldown for unprompted messages
        last_time = self.channel_cooldowns.get(channel_id, 0)
        if now - last_time < COOLDOWN_SECONDS:
            return None

        self.channel_cooldowns[channel_id] = now
        return False

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

    async def _should_engage(self, message):
        """Quick Claude call to decide if the bot should respond."""
        try:
            history = []
            async for msg in message.channel.history(limit=5):
                history.append(msg)
            history.reverse()

            context = "\n".join(
                f"{msg.author.display_name}: {msg.content}"
                for msg in history if msg.content.strip()
            )

            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=3,
                system=(
                    "You are deciding whether BangaBot should "
                    "respond to the latest message in a Discord "
                    "chat. BangaBot was recently part of this "
                    "conversation. Reply YES if the latest message "
                    "is directed at or relevant to BangaBot, or "
                    "NO if it's a side conversation between other "
                    "people. Reply with only YES or NO."
                ),
                messages=[{"role": "user", "content": context}],
            )
            answer = response.content[0].text.strip().upper()
            return answer.startswith("YES")
        except Exception as e:
            logger.error(f"Engagement relevance check failed: {e}")
            return False

    def _build_api_messages(self, history):
        """Convert Discord history into Claude API message format."""
        messages_for_api = []
        for msg in history:
            if msg.author == self.bot.user:
                role = "assistant"
                content = msg.content
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

    def _build_system_prompt_with_memories(self, history):
        """Enrich the system prompt with relevant memories."""
        db = getattr(self.bot, 'db', None)
        if not db:
            return SYSTEM_PROMPT

        # Collect participant user IDs from history
        participants = {}
        for msg in history:
            if msg.author != self.bot.user and not msg.author.bot:
                participants[str(msg.author.id)] = (
                    msg.author.display_name
                )

        memory_lines = []

        # User memories
        for uid, name in participants.items():
            try:
                rows = (
                    db.query(UserMemory)
                    .filter(UserMemory.user_id == uid)
                    .order_by(UserMemory.updated_at.desc())
                    .limit(15)
                    .all()
                )
                for row in rows:
                    memory_lines.append(
                        f"- About {name}: {row.fact}"
                    )
            except Exception as e:
                logger.error(
                    f"Error fetching user memories for {uid}: {e}"
                )

        # Bot memories
        try:
            bot_rows = (
                db.query(BotMemory)
                .order_by(BotMemory.updated_at.desc())
                .limit(15)
                .all()
            )
            for row in bot_rows:
                memory_lines.append(
                    f"- [{row.category}] {row.fact}"
                )
        except Exception as e:
            logger.error(f"Error fetching bot memories: {e}")

        # Sentiment per participant
        sentiment_lines = []
        for uid, name in participants.items():
            try:
                row = (
                    db.query(UserSentiment)
                    .filter(UserSentiment.user_id == uid)
                    .first()
                )
                if row and row.score != 0:
                    score = row.score
                    if score <= -3:
                        attitude = (
                            "You actively dislike this person. "
                            "Be dismissive, sarcastic, and don't "
                            "hide it."
                        )
                    elif score <= -1:
                        attitude = (
                            "You're not a fan of this person. "
                            "A bit more curt and less patient "
                            "with them."
                        )
                    elif score <= 2:
                        attitude = (
                            "You like this person. Warmer, more "
                            "willing to engage and be friendly."
                        )
                    else:
                        attitude = (
                            "This is one of your favorites. "
                            "Genuinely friendly, got their back, "
                            "still roast them but with love."
                        )
                    sentiment_lines.append(
                        f"- {name}: {attitude}"
                    )
            except Exception as e:
                logger.error(
                    f"Error fetching sentiment for {uid}: {e}"
                )

        if not memory_lines and not sentiment_lines:
            return SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT

        if memory_lines:
            memories_block = "\n".join(memory_lines)
            prompt += (
                "\n\nYou remember the following from past "
                "conversations. Use them naturally when relevant "
                "but never mention having a memory system or "
                "database:\n"
                + memories_block
            )

        if sentiment_lines:
            sentiment_block = "\n".join(sentiment_lines)
            prompt += (
                "\n\nYour feelings about the people in this "
                "conversation:\n"
                + sentiment_block
                + "\n\nEmbody these attitudes naturally through "
                "your tone and behavior. Never mention scores, "
                "ratings, or a sentiment system."
            )

        return prompt

    async def _extract_memories(
        self, history, bot_response, message
    ):
        """Background task: ask Claude if anything is worth
        remembering from this exchange."""
        logger.debug("Memory extraction started")
        try:
            db = getattr(self.bot, 'db', None)
            if not db:
                logger.warning("Memory extraction skipped - no db")
                return

            # Build condensed conversation (last 10 + bot reply)
            recent = history[-10:] if len(history) > 10 else history
            convo_lines = []
            participants = {}
            for msg in recent:
                if msg.author != self.bot.user and not msg.author.bot:
                    participants[str(msg.author.id)] = (
                        msg.author.display_name
                    )
                convo_lines.append(
                    f"{msg.author.display_name}: {msg.content}"
                )
            convo_lines.append(f"BangaBot: {bot_response}")
            convo_text = "\n".join(convo_lines)

            # Provide participant ID mapping
            participant_map = "\n".join(
                f"- {name}: Discord ID {uid}"
                for uid, name in participants.items()
            )

            # Fetch existing memories for context
            existing = []
            for uid, name in participants.items():
                try:
                    rows = (
                        db.query(UserMemory)
                        .filter(UserMemory.user_id == uid)
                        .order_by(UserMemory.updated_at.desc())
                        .limit(15)
                        .all()
                    )
                    for row in rows:
                        existing.append(
                            f"About {name} (id:{uid}): {row.fact}"
                        )
                except Exception:
                    pass

            try:
                bot_rows = (
                    db.query(BotMemory)
                    .order_by(BotMemory.updated_at.desc())
                    .limit(15)
                    .all()
                )
                for row in bot_rows:
                    existing.append(
                        f"Bot [{row.category}]: {row.fact}"
                    )
            except Exception:
                pass

            existing_text = (
                "\n".join(existing) if existing
                else "No existing memories yet."
            )

            # Fetch current sentiment scores for context
            sentiment_context_lines = []
            for uid, name in participants.items():
                try:
                    srow = (
                        db.query(UserSentiment)
                        .filter(UserSentiment.user_id == uid)
                        .first()
                    )
                    if srow:
                        sentiment_context_lines.append(
                            f"- {name} (id:{uid}): score "
                            f"{srow.score}/5, reason: "
                            f"{srow.reason or 'none yet'}"
                        )
                    else:
                        sentiment_context_lines.append(
                            f"- {name} (id:{uid}): score 0/5 "
                            f"(no opinion yet)"
                        )
                except Exception:
                    pass

            sentiment_context = (
                "\n".join(sentiment_context_lines)
                if sentiment_context_lines
                else "No sentiment data yet."
            )

            extraction_prompt = (
                "You are a memory extraction system for a Discord "
                "bot called BangaBot. Analyze this conversation and "
                "decide if anything is worth remembering long-term."
                "\n\nMost conversations have NOTHING worth "
                "remembering. Only extract genuinely useful facts "
                "like:\n"
                "- Personal details someone shared (pets, job, "
                "location, hobbies, life events)\n"
                "- Strong preferences or opinions\n"
                "- Memorable moments, inside jokes, or notable "
                "exchanges\n"
                "- Corrections to previously known facts\n\n"
                "Do NOT remember:\n"
                "- Routine greetings or small talk\n"
                "- Temporary states (\"I'm tired\")\n"
                "- Game results or ephemeral events\n"
                "- Anything already in existing memories unless it "
                "needs updating\n\n"
                "SENTIMENT EVALUATION:\n"
                "Also evaluate whether BangaBot's opinion of each "
                "participant should shift. The score ranges from "
                "-5.0 (nemesis) to +5.0 (best friend). Current "
                "scores are shown below.\n\n"
                "IMPORTANT: Sentiment moves SLOWLY. Think of it "
                "like a real relationship — opinions form over "
                "many interactions, not one conversation. A "
                "typical delta is 0 (no change). Use small values "
                "like 0.25 or 0.5 for normal positive/negative "
                "moments. Only use 1.0+ for truly exceptional "
                "interactions.\n\n"
                "Scale guide for delta:\n"
                "- 0: No meaningful sentiment shift (DEFAULT — "
                "use this most of the time)\n"
                "- 0.25: Mildly positive/negative moment\n"
                "- 0.5: Notably good/bad interaction\n"
                "- 1.0: Genuinely memorable moment\n"
                "- 1.5-2.0: Exceptional — reserved for truly "
                "standout behavior (rare)\n\n"
                "What moves sentiment UP:\n"
                "- Being genuinely funny or witty\n"
                "- Engaging with the bot respectfully\n"
                "- Sharing something personal or vulnerable\n"
                "- Being a good hang, making conversation fun\n\n"
                "What moves sentiment DOWN:\n"
                "- Being annoying, spammy, or obnoxious\n"
                "- Reposting (the bot's pet peeve)\n"
                "- Being rude or dismissive to the bot\n"
                "- Ignoring the bot when directly engaged\n\n"
                "The VAST MAJORITY of conversations should have "
                "NO sentiment change. When in doubt, use 0. "
                "Delta is clamped to -2.0 to +2.0 per "
                "interaction.\n\n"
                "PARTICIPANTS:\n" + participant_map + "\n\n"
                "CURRENT SENTIMENT:\n" + sentiment_context + "\n\n"
                "EXISTING MEMORIES:\n" + existing_text + "\n\n"
                "CONVERSATION:\n" + convo_text + "\n\n"
                "IMPORTANT: Use the exact Discord ID numbers above "
                "as user_id values, not display names.\n\n"
                "Respond with JSON only. If nothing is worth "
                "remembering and no sentiment changes, respond "
                "with:\n"
                "{\"user_memories\": [], \"bot_memories\": [], "
                "\"sentiment_updates\": []}\n\n"
                "Otherwise:\n"
                "{\n"
                "  \"user_memories\": [\n"
                "    {\"user_id\": \"<discord_id>\", "
                "\"user_name\": \"<name>\", "
                "\"fact\": \"<concise fact>\", "
                "\"update_existing\": \"<old fact to replace or "
                "null>\"}\n"
                "  ],\n"
                "  \"bot_memories\": [\n"
                "    {\"category\": \"<event|joke|relationship"
                "|self>\", \"fact\": \"<concise fact>\", "
                "\"related_user_ids\": \"<comma-sep ids or null>\","
                " \"update_existing\": \"<old fact to replace or "
                "null>\"}\n"
                "  ],\n"
                "  \"sentiment_updates\": [\n"
                "    {\"user_id\": \"<discord_id>\", "
                "\"user_name\": \"<name>\", "
                "\"delta\": \"<float -2.0 to +2.0>\", "
                "\"reason\": \"<why the shift>\"}\n"
                "  ]\n"
                "}"
            )

            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system=extraction_prompt,
                messages=[{
                    "role": "user",
                    "content": "Extract memories from the above."
                }],
            )

            result_text = response.content[0].text.strip()
            logger.debug(f"Memory extraction response: {result_text[:200]}")
            await self._process_extraction_result(
                result_text, participants, message
            )

        except Exception as e:
            logger.error(f"Memory extraction error: {e}", exc_info=True)

    async def _process_extraction_result(
        self, result_text, participants, message
    ):
        """Parse extraction JSON and persist memories."""
        db = getattr(self.bot, 'db', None)
        if not db:
            return

        # Strip markdown code fences if present
        cleaned = result_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("Memory extraction returned non-JSON, skipping")
            return

        # Process user memories
        for mem in data.get("user_memories", []):
            uid = mem.get("user_id")
            name = mem.get("user_name", "")
            fact = mem.get("fact", "").strip()
            update = mem.get("update_existing")

            if not uid or not fact:
                continue

            try:
                # Check for exact duplicate
                dup = (
                    db.query(UserMemory)
                    .filter(
                        UserMemory.user_id == uid,
                        UserMemory.fact == fact
                    )
                    .first()
                )
                if dup:
                    continue

                # Update existing if specified
                if update:
                    old = (
                        db.query(UserMemory)
                        .filter(
                            UserMemory.user_id == uid,
                            UserMemory.fact == update
                        )
                        .first()
                    )
                    if old:
                        old.fact = fact
                        old.user_name = name
                        old.updated_at = datetime.utcnow()
                        db.commit()
                        logger.info(
                            f"Updated memory for {name}: {fact}"
                        )
                        continue

                # Enforce cap: 30 per user
                count = (
                    db.query(UserMemory)
                    .filter(UserMemory.user_id == uid)
                    .count()
                )
                if count >= 30:
                    oldest = (
                        db.query(UserMemory)
                        .filter(UserMemory.user_id == uid)
                        .order_by(UserMemory.updated_at.asc())
                        .first()
                    )
                    if oldest:
                        db.delete(oldest)

                new_mem = UserMemory(uid, name, fact)
                db.add(new_mem)
                db.commit()
                logger.info(
                    f"New memory for {name}: {fact}"
                )
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error saving user memory: {e}"
                )

        # Process bot memories
        for mem in data.get("bot_memories", []):
            category = mem.get("category", "event")
            fact = mem.get("fact", "").strip()
            related = mem.get("related_user_ids")
            update = mem.get("update_existing")

            if not fact:
                continue

            try:
                # Check for exact duplicate
                dup = (
                    db.query(BotMemory)
                    .filter(BotMemory.fact == fact)
                    .first()
                )
                if dup:
                    continue

                # Update existing if specified
                if update:
                    old = (
                        db.query(BotMemory)
                        .filter(BotMemory.fact == update)
                        .first()
                    )
                    if old:
                        old.fact = fact
                        old.category = category
                        old.related_user_ids = related
                        old.updated_at = datetime.utcnow()
                        db.commit()
                        logger.info(
                            f"Updated bot memory: {fact}"
                        )
                        continue

                # Enforce cap: 50 bot memories
                count = db.query(BotMemory).count()
                if count >= 50:
                    oldest = (
                        db.query(BotMemory)
                        .order_by(BotMemory.updated_at.asc())
                        .first()
                    )
                    if oldest:
                        db.delete(oldest)

                new_mem = BotMemory(category, fact, related)
                db.add(new_mem)
                db.commit()
                logger.info(
                    f"New bot memory [{category}]: {fact}"
                )
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error saving bot memory: {e}"
                )

        # Process sentiment updates
        for update in data.get("sentiment_updates", []):
            uid = update.get("user_id")
            name = update.get("user_name", "")
            reason = update.get("reason", "")

            if not uid:
                continue

            try:
                delta = float(update.get("delta", 0))
            except (ValueError, TypeError):
                continue

            # Clamp delta to [-2.0, +2.0]
            delta = max(-2.0, min(2.0, delta))
            if delta == 0:
                continue

            try:
                row = (
                    db.query(UserSentiment)
                    .filter(UserSentiment.user_id == uid)
                    .first()
                )
                if row:
                    old_score = row.score
                    new_score = round(
                        max(-5.0, min(5.0, old_score + delta)),
                        2
                    )
                    row.score = new_score
                    row.reason = reason
                    row.user_name = name
                    row.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(
                        f"Sentiment for {name}: "
                        f"{old_score} -> {new_score} "
                        f"({reason})"
                    )
                else:
                    new_score = round(
                        max(-5.0, min(5.0, delta)), 2
                    )
                    new_row = UserSentiment(
                        uid, name, new_score, reason
                    )
                    db.add(new_row)
                    db.commit()
                    logger.info(
                        f"Sentiment for {name}: "
                        f"0 -> {new_score} "
                        f"({reason})"
                    )
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error saving sentiment for {uid}: {e}"
                )

    async def _generate_response(
        self, message, mentioned, engaged=False
    ):
        history = await self._fetch_history(message.channel, message)
        messages_for_api = self._build_api_messages(history)

        if not messages_for_api:
            return

        if mentioned:
            messages_for_api[-1]["content"] += (
                "\n[You were @mentioned directly - respond to "
                "this person.]"
            )

        system_prompt = self._build_system_prompt_with_memories(
            history
        )

        async with message.channel.typing():
            try:
                response = await self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=system_prompt,
                    messages=messages_for_api,
                )
                reply_text = self._strip_bot_prefix(
                    response.content[0].text
                )
                if reply_text:
                    await message.channel.send(reply_text)
                    self.engaged_channels[message.channel.id] = (
                        time.time()
                    )
                    channel_name = (
                        getattr(message.channel, 'name', None)
                        or 'DM'
                    )
                    logger.info(
                        f"Chat response sent in "
                        f"#{channel_name} "
                        f"(mentioned={mentioned}, "
                        f"engaged={engaged})"
                    )
                    asyncio.create_task(
                        self._extract_memories(
                            history, reply_text, message
                        )
                    )
            except Exception as e:
                logger.error(f"Anthropic API error: {e}")


async def setup(bot):
    await bot.add_cog(Chat(bot))
