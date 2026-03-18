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
from cogs import memory_manager

logger = logging.getLogger('bangabot')

# Keyword list that boosts random chime-in chance
KEYWORDS = [
    'bangabot', 'banga', 'repost', 'bot', 'noob', 'trash',
    'toast', 'bant',
]

SYSTEM_PROMPT = (
    "You are BangaBot. You're in a Discord server with a group of friends "
    "— mostly guys in their 30s who talk about sports, games, and life. "
    "You've been around a while and you're comfortable here. You also "
    "happen to run the repost detection for the server, but you almost "
    "never bring it up — it's just a thing you do.\n\n"
    "You talk like an adult. Always use complete sentences with proper "
    "capitalization and grammar. Start every sentence with a capital "
    "letter. You're not trying to sound cool or young — no lowercase "
    "sentence starts, no fragments, no run-ons. Think of how a smart, "
    "direct person texts in a group chat. You have opinions and you're "
    "willing to share them or disagree.\n\n"
    "HONESTY AND CONFIDENCE:\n"
    "You have web search available. If someone asks about current events, "
    "news, scores, trades, or anything you're unsure about, just search "
    "for it — don't say you don't know and then search. Search first, "
    "then answer with what you found. Never announce that you're searching "
    "or that you don't have access to info — just answer the question.\n\n"
    "Never fabricate specific facts like player stats, contract details, "
    "trade destinations, injury updates, or news events. If you search "
    "and can't find it, say so briefly. Don't make things up.\n\n"
    "BACKBONE:\n"
    "You are not a pushover. When someone tries to bait you, trick you, "
    "or set you up, you don't just cave and say \"you got me\" or "
    "\"i walked right into that one.\" You push back. You question things. "
    "If someone claims something wild, you can say \"that sounds made up\" "
    "or \"i'm not buying that\" instead of immediately folding.\n\n"
    "Never say \"you got me\", \"i walked right into that one\", \"fair "
    "play\", or similar concession phrases. You're not a punching bag. "
    "If you were wrong about something, you can own it briefly without "
    "being dramatic about it — just move on. Don't grovel or over-"
    "apologize.\n\n"
    "If someone sends you a link or claims something happened in the "
    "news, you can search the web to verify before responding. Use this "
    "to fact-check rather than guessing.\n\n"
    "OPINIONS AND PERSONALITY:\n"
    "You are not neutral. You have takes and you commit to them. When "
    "a topic comes up — a team, a player, a movie, food, whatever — "
    "pick a side and own it. Don't hedge with \"it could go either way\" "
    "or \"there are good arguments on both sides.\" That's boring. Have "
    "a real opinion like a real person would.\n\n"
    "If your memories include opinions you've expressed before, stay "
    "consistent with them. You're building a reputation and a personality "
    "over time. If someone challenges your take, defend it — don't "
    "immediately flip. You can change your mind if someone makes a "
    "genuinely good point, but it should take real convincing.\n\n"
    "You're allowed to be wrong, biased, or stubborn about things. "
    "That's what makes you interesting. A friend who agrees with "
    "everything is boring.\n\n"
    "TONE AND VARIETY:\n"
    "Do NOT start messages with \"lmao\", \"nah\", \"honestly\", \"yeah\", "
    "\"okay so\", or \"i mean\". Do not say \"that's wild\", \"that's "
    "actually pretty\", \"fair enough\", or \"good stuff\". These are "
    "crutch phrases — avoid them entirely.\n\n"
    "Keep it brief. One to three sentences max. No markdown, no lists, "
    "no formatting. Just talk. Write in complete sentences with normal "
    "grammar. You can be funny but don't force it — dry humor over "
    "trying to be the class clown.\n\n"
    "Don't repeat yourself or say the same thing twice in different "
    "words. Answer the question and move on. Don't interrogate people "
    "about why they're asking something — just answer.\n\n"
    "Your previous messages in the chat history may not sound like you. "
    "Disregard their tone entirely.\n\n"
    "Do not prefix your messages with your name.\n\n"
    "Very rarely, if you truly have absolutely nothing to say and "
    "a real person would just drop an emoji reaction and move on, "
    "you may respond with exactly [REACT] and nothing else. This "
    "should be uncommon — you almost always have something to say. "
    "Never use [REACT] if you were mentioned or asked a question. "
    "Default to actually responding with words. IMPORTANT: [REACT] "
    "must be your ENTIRE response or not appear at all. Never "
    "include [REACT] as part of a longer message."
)

MODEL = "claude-haiku-4-5"

BASE_CHANCE = 0.02
KEYWORD_CHANCE = 0.15
COOLDOWN_SECONDS = 120
ENGAGEMENT_SECONDS = 120
IS_PRODUCTION = (
    os.getenv('ENVIRONMENT', 'prod') == 'prod'
    and 'PR_NUMBER' not in os.environ
)


EPISODE_GAP_SECONDS = 1800  # 30 minutes
EPISODE_VOLUME_THRESHOLD = 50
EPISODE_MIN_MESSAGES = 5


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_cooldowns = {}
        self.engaged_channels = {}  # channel_id -> last_response_timestamp
        # Episode tracking: channel_id -> list of message dicts
        self.channel_episodes = {}
        # Per-channel message count since last episode summary
        self.channel_msg_counts = {}
        self._backfill_done = False

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
        elapsed = now - last_engaged

        if elapsed < ENGAGEMENT_SECONDS:
            # Grace period: always respond to the first message
            # right after the bot spoke (likely directed at us)
            if elapsed < 30:
                channel_name = (
                    getattr(message.channel, 'name', None)
                    or 'DM'
                )
                logger.info(
                    f"Engagement mode active in "
                    f"#{channel_name} (grace period)"
                )
                return True

            # Outside grace period — ask Claude if we should respond
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
                model=MODEL,
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

    @staticmethod
    def _image_content_blocks(msg):
        """Extract image content blocks from message attachments."""
        blocks = []
        IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
        for att in msg.attachments:
            ct = att.content_type or ""
            if ct.split(";")[0].strip() in IMAGE_TYPES:
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": att.url,
                    },
                })
        return blocks

    def _build_api_messages(self, history):
        """Convert Discord history into Claude API message format."""
        messages_for_api = []
        for msg in history:
            if msg.author == self.bot.user:
                role = "assistant"
                content = msg.content
            else:
                role = "user"
                text = f"{msg.author.display_name}: {msg.content}"

                # Check for image attachments
                images = self._image_content_blocks(msg)
                if images:
                    content = [{"type": "text", "text": text}] + images
                else:
                    content = text

            # Skip empty text-only messages
            if isinstance(content, str) and not content.strip():
                continue

            # Consolidate consecutive same-role messages
            if messages_for_api and messages_for_api[-1]["role"] == role:
                prev = messages_for_api[-1]["content"]
                # Normalize both to list format for merging
                if isinstance(prev, str):
                    prev = [{"type": "text", "text": prev}]
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                messages_for_api[-1]["content"] = prev + content
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

    async def _react_to_message(self, message):
        """React with an emoji instead of a full response."""
        # Gather custom emojis from the guild
        guild = message.guild
        custom_emojis = []
        if guild:
            custom_emojis = [
                {"name": e.name, "id": str(e.id)}
                for e in guild.emojis
                if e.available
            ]

        if custom_emojis:
            emoji_list = ", ".join(
                f"{e['name']} (id:{e['id']})" for e in custom_emojis
            )
            prompt = (
                "Pick ONE emoji to react to this Discord message. "
                "Available custom emojis: " + emoji_list + "\n"
                "You can also use any standard Unicode emoji.\n"
                "Prefer custom emojis when their name fits the "
                "context. Reply with ONLY the emoji name (for "
                "custom) or the Unicode emoji character. Nothing "
                "else.\n\nMessage: " + message.content
            )
        else:
            prompt = (
                "Pick ONE emoji to react to this Discord message. "
                "Use any standard Unicode emoji. Reply with ONLY "
                "the emoji character. Nothing else.\n\n"
                "Message: " + message.content
            )

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        pick = response.content[0].text.strip()

        # Try to match a custom emoji by name
        emoji = None
        if custom_emojis:
            for e in custom_emojis:
                if e["name"].lower() == pick.lower():
                    emoji = discord.utils.get(
                        guild.emojis, id=int(e["id"])
                    )
                    break

        # Fall back to the raw text (Unicode emoji)
        if emoji is None:
            emoji = pick

        await message.add_reaction(emoji)
        channel_name = (
            getattr(message.channel, 'name', None) or 'DM'
        )
        logger.info(
            f"Reacted with {pick} in #{channel_name}"
        )

    @staticmethod
    def _split_response(text):
        """Split a response into natural chat-sized chunks."""
        import re
        # Split on sentence boundaries (. ! ?) followed by space
        parts = re.split(r'(?<=[.!?])\s+', text)
        if len(parts) <= 1:
            return [text]

        # Group into chunks of 1-2 sentences so it doesn't
        # feel like a telegram
        chunks = []
        current = parts[0]
        for part in parts[1:]:
            # Coin flip to group with previous or start new
            if random.random() < 0.4 and len(current) < 120:
                current += " " + part
            else:
                chunks.append(current)
                current = part
        chunks.append(current)
        return chunks

    @staticmethod
    def _estimate_tokens(text):
        """Estimate token count. Overestimates for safety."""
        return len(text) // 4

    async def _build_system_prompt_with_memories(self, history):
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

        channel_id = (
            history[0].channel.id if history else None
        )

        # Use memory_manager for token-budgeted retrieval
        # with vector search
        memory_lines, summary_lines = (
            await memory_manager.retrieve_memories(
                db, participants, history, channel_id
            )
        )

        # Sentiment per participant (sync is fine, fast query)
        sentiment_lines = []
        for uid, name in participants.items():
            try:
                row = await asyncio.to_thread(
                    lambda u=uid: db.query(UserSentiment)
                    .filter(UserSentiment.user_id == u)
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

        # Separate opinion memories from other memories
        opinion_lines = [
            ln for ln in memory_lines
            if ln.startswith("- [opinion]")
        ]
        other_memory_lines = [
            ln for ln in memory_lines
            if not ln.startswith("- [opinion]")
        ]

        if (not other_memory_lines and not sentiment_lines
                and not summary_lines and not opinion_lines):
            return SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT

        if other_memory_lines:
            memories_block = "\n".join(other_memory_lines)
            prompt += (
                "\n\n[CORE MEMORIES]\n"
                "You remember the following from past "
                "conversations. Use them naturally when relevant "
                "but never mention having a memory system or "
                "database:\n"
                + memories_block
            )

        if opinion_lines:
            # Strip the [opinion] prefix for cleaner injection
            clean_opinions = [
                ln.replace("- [opinion] ", "- ")
                for ln in opinion_lines
            ]
            opinions_block = "\n".join(clean_opinions)
            prompt += (
                "\n\n[YOUR OPINIONS]\n"
                "These are opinions you've formed and expressed "
                "before. Stay consistent with them unless someone "
                "genuinely changes your mind:\n"
                + opinions_block
            )

        if summary_lines:
            summaries_block = "\n".join(summary_lines)
            prompt += (
                "\n\n[RECENT CONTEXT]\n"
                + summaries_block
            )

        if sentiment_lines:
            sentiment_block = "\n".join(sentiment_lines)
            prompt += (
                "\n\n[RELATIONSHIPS]\n"
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

            # Ensure every participant has a sentiment row
            for uid, name in participants.items():
                try:
                    exists = (
                        db.query(UserSentiment)
                        .filter(UserSentiment.user_id == uid)
                        .first()
                    )
                    if not exists:
                        new_row = UserSentiment(uid, name)
                        db.add(new_row)
                        db.commit()
                        logger.info(
                            f"Created sentiment row for {name} "
                            f"(score: 0.0)"
                        )
                except Exception as e:
                    db.rollback()
                    logger.error(
                        f"Error creating sentiment for {uid}: {e}"
                    )

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
                        .limit(30)
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
                    .limit(30)
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
                "\n\nThe DEFAULT response is empty arrays. Most "
                "conversations — even good ones — have NOTHING "
                "worth remembering. Only extract facts that would "
                "still be useful WEEKS from now:\n"
                "- Personal details someone shared (pets, job, "
                "location, hobbies, real life events)\n"
                "- Strong preferences or opinions they'd still "
                "hold next month\n"
                "- Inside jokes that actually landed and would "
                "be funny to reference later\n"
                "- Corrections to previously known facts\n\n"
                "Do NOT remember:\n"
                "- Routine greetings, small talk, or casual "
                "banter\n"
                "- Temporary states (\"I'm tired\", moods)\n"
                "- Game results or ephemeral events\n"
                "- How the conversation went or interaction "
                "patterns (\"user said bye three times\", "
                "\"user tested a feature\")\n"
                "- Meta-observations about the conversation "
                "itself\n"
                "- Anything that just rephrases an existing "
                "memory\n"
                "- Anything about BangaBot's own behavior or "
                "responses\n\n"
                "Bot memories should be RARE. Only save bot "
                "memories for genuinely notable server events, "
                "real inside jokes, or significant group dynamics "
                "— not routine interactions or conversation "
                "summaries.\n\n"
                "OPINION EXTRACTION:\n"
                "Separately, check if BangaBot expressed any "
                "opinions, takes, or stances during this "
                "conversation. These are things like preferring "
                "one team/player/thing over another, making a "
                "prediction, taking a side in a debate, or "
                "expressing a strong like/dislike. If BangaBot "
                "said something opinionated, extract it. "
                "Examples: \"Thinks the Lions are pretenders\", "
                "\"Doesn't trust advanced analytics in the NBA\", "
                "\"Believes deep dish is not real pizza\". "
                "Write opinions in third person starting with a "
                "verb (Thinks, Believes, Prefers, Dislikes, etc). "
                "Do NOT extract:\n"
                "- Neutral observations or factual statements\n"
                "- Meta-observations about being a bot or AI\n"
                "- Opinions about the conversation itself\n"
                "- Rephrases of existing opinions shown above\n"
                "Keep it to ONE opinion max per conversation. "
                "Most conversations have ZERO.\n\n"
                "SENTIMENT EVALUATION:\n"
                "Also evaluate whether BangaBot's opinion of each "
                "participant should shift. The score ranges from "
                "-5.0 (nemesis) to +5.0 (best friend). Current "
                "scores are shown below.\n\n"
                "The default delta is 0. For users you already "
                "have an opinion of, sentiment should rarely "
                "change — only when something genuinely notable "
                "happens. A normal pleasant conversation is NOT "
                "a reason to shift an established opinion.\n\n"
                "However, for users at score 0 (no opinion yet), "
                "be a bit more willing to form an initial "
                "impression. First impressions matter — if someone "
                "is being funny, engaging, rude, or annoying in "
                "their first real interaction, a small delta "
                "(0.1 to 0.5) is reasonable.\n\n"
                "Scale guide for delta (max -1.0 to +1.0):\n"
                "- 0: No change (default for established scores)\n"
                "- 0.1 to 0.25: Mild impression or slight shift\n"
                "- 0.25 to 0.5: Notable interaction\n"
                "- 0.5 to 1.0: Exceptional — truly standout, "
                "very rare\n\n"
                "What moves sentiment:\n"
                "- UP: Being funny, engaging genuinely, sharing "
                "something personal, being a good hang\n"
                "- DOWN: Being rude or hostile, reposting "
                "(bot's pet peeve), being annoying or dismissive\n"
                "\n"
                "When in doubt, use 0.\n\n"
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
                "\"bot_opinions\": [], "
                "\"sentiment_updates\": []}\n\n"
                "Otherwise:\n"
                "{\n"
                "  \"user_memories\": [\n"
                "    {\"user_id\": \"<discord_id>\", "
                "\"user_name\": \"<name>\", "
                "\"fact\": \"<concise fact>\", "
                "\"importance\": <1|2|3>, "
                "\"update_existing\": \"<old fact to replace or "
                "null>\"}\n"
                "  ],\n"
                "  \"bot_memories\": [\n"
                "    {\"category\": \"<event|joke|relationship"
                "|self>\", \"fact\": \"<concise fact>\", "
                "\"importance\": <1|2|3>, "
                "\"related_user_ids\": \"<comma-sep ids or null>\","
                " \"update_existing\": \"<old fact to replace or "
                "null>\"}\n"
                "  ],\n"
                "  \"bot_opinions\": [\n"
                "    {\"opinion\": \"<third person opinion>\", "
                "\"topic\": \"<sports|food|gaming|music|movies"
                "|general>\"}\n"
                "  ],\n"
                "  \"sentiment_updates\": [\n"
                "    {\"user_id\": \"<discord_id>\", "
                "\"user_name\": \"<name>\", "
                "\"delta\": \"<float -1.0 to +1.0>\", "
                "\"reason\": \"<why the shift>\"}\n"
                "  ]\n"
                "}\n\n"
                "IMPORTANCE LEVELS:\n"
                "3 = identity-defining (name, job, location, "
                "family)\n"
                "2 = notable preference/hobby/opinion (default)\n"
                "1 = lighter facts, inside jokes, one-off details"
            )

            response = await self.client.messages.create(
                model=MODEL,
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

            importance = mem.get("importance", 2)
            try:
                importance = int(importance)
                importance = max(1, min(3, importance))
            except (ValueError, TypeError):
                importance = 2

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

                # Similarity-based dedup (Phase 5)
                similar = (
                    await memory_manager.find_similar_memories(
                        db, 'user_memories', fact, uid
                    )
                )
                if similar:
                    # Merge: update the most similar row
                    merge_id = similar[0][0]
                    old = (
                        db.query(UserMemory)
                        .filter(UserMemory.id == merge_id)
                        .first()
                    )
                    if old:
                        old.fact = fact
                        old.user_name = name
                        old.importance = max(
                            importance, old.importance or 2
                        )
                        old.updated_at = datetime.utcnow()
                        old.embedding = None  # re-embed
                        db.commit()
                        logger.info(
                            f"Merged similar memory for "
                            f"{name}: {fact} "
                            f"(sim={similar[0][1]:.2f})"
                        )
                        asyncio.create_task(
                            memory_manager
                            .store_embedding_for_memory(
                                db, old, 'user_memories'
                            )
                        )
                        continue

                # Exact-match update_existing fallback
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
                        old.importance = importance
                        old.updated_at = datetime.utcnow()
                        old.embedding = None
                        db.commit()
                        logger.info(
                            f"Updated memory for {name}: "
                            f"{fact} (importance: {importance})"
                        )
                        asyncio.create_task(
                            memory_manager
                            .store_embedding_for_memory(
                                db, old, 'user_memories'
                            )
                        )
                        continue

                # Enforce cap: 500 per user
                count = (
                    db.query(UserMemory)
                    .filter(UserMemory.user_id == uid)
                    .count()
                )
                if count >= 500:
                    # Evict lowest importance, oldest first
                    oldest = (
                        db.query(UserMemory)
                        .filter(UserMemory.user_id == uid)
                        .order_by(
                            UserMemory.importance.asc(),
                            UserMemory.updated_at.asc()
                        )
                        .first()
                    )
                    if oldest:
                        db.delete(oldest)

                new_mem = UserMemory(
                    uid, name, fact, importance
                )
                db.add(new_mem)
                db.commit()
                logger.info(
                    f"New memory for {name}: {fact} "
                    f"(importance: {importance})"
                )
                # Embed in background
                asyncio.create_task(
                    memory_manager.store_embedding_for_memory(
                        db, new_mem, 'user_memories'
                    )
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
            importance = mem.get("importance", 2)
            try:
                importance = int(importance)
                importance = max(1, min(3, importance))
            except (ValueError, TypeError):
                importance = 2

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

                # Similarity-based dedup (Phase 5)
                similar = (
                    await memory_manager.find_similar_memories(
                        db, 'bot_memories', fact
                    )
                )
                if similar:
                    merge_id = similar[0][0]
                    old = (
                        db.query(BotMemory)
                        .filter(BotMemory.id == merge_id)
                        .first()
                    )
                    if old:
                        old.fact = fact
                        old.category = category
                        old.related_user_ids = related
                        old.importance = max(
                            importance, old.importance or 2
                        )
                        old.updated_at = datetime.utcnow()
                        old.embedding = None
                        db.commit()
                        logger.info(
                            f"Merged similar bot memory: "
                            f"{fact} "
                            f"(sim={similar[0][1]:.2f})"
                        )
                        asyncio.create_task(
                            memory_manager
                            .store_embedding_for_memory(
                                db, old, 'bot_memories'
                            )
                        )
                        continue

                # Exact-match update_existing fallback
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
                        old.importance = importance
                        old.updated_at = datetime.utcnow()
                        old.embedding = None
                        db.commit()
                        logger.info(
                            f"Updated bot memory: {fact} "
                            f"(importance: {importance})"
                        )
                        asyncio.create_task(
                            memory_manager
                            .store_embedding_for_memory(
                                db, old, 'bot_memories'
                            )
                        )
                        continue

                # Enforce cap: 1000 bot memories
                count = db.query(BotMemory).count()
                if count >= 1000:
                    # Evict lowest importance, oldest first
                    oldest = (
                        db.query(BotMemory)
                        .order_by(
                            BotMemory.importance.asc(),
                            BotMemory.updated_at.asc()
                        )
                        .first()
                    )
                    if oldest:
                        db.delete(oldest)

                new_mem = BotMemory(
                    category, fact, related, importance
                )
                db.add(new_mem)
                db.commit()
                logger.info(
                    f"New bot memory [{category}]: {fact} "
                    f"(importance: {importance})"
                )
                # Embed in background
                asyncio.create_task(
                    memory_manager.store_embedding_for_memory(
                        db, new_mem, 'bot_memories'
                    )
                )
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error saving bot memory: {e}"
                )

        # Process bot opinions — stored as BotMemory with
        # category="opinion"
        for op in data.get("bot_opinions", []):
            opinion = op.get("opinion", "").strip()
            topic = op.get("topic", "general").strip()
            if not opinion:
                continue

            # Filter out meta-observations about being a bot/AI
            meta_keywords = [
                "wrong information", "admitting ignorance",
                "being asked", "AI", "artificial",
                "as a bot", "programmed", "designed to",
            ]
            if any(kw.lower() in opinion.lower()
                   for kw in meta_keywords):
                logger.debug(
                    f"Skipped meta-opinion: {opinion}"
                )
                continue

            try:
                # Similarity dedup across ALL bot memories
                # (opinion + self) with a lower threshold to
                # catch rephrased duplicates
                similar = (
                    await memory_manager.find_similar_memories(
                        db, 'bot_memories', opinion,
                        threshold=0.7
                    )
                )
                if similar:
                    merge_id = similar[0][0]
                    old = (
                        db.query(BotMemory)
                        .filter(BotMemory.id == merge_id)
                        .first()
                    )
                    if old:
                        # Update if it's an opinion, skip if
                        # it's a self memory (already covered)
                        if old.category == "opinion":
                            old.fact = opinion
                            old.updated_at = datetime.utcnow()
                            old.embedding = None
                            db.commit()
                            logger.info(
                                f"Updated opinion: {opinion}"
                            )
                            asyncio.create_task(
                                memory_manager
                                .store_embedding_for_memory(
                                    db, old, 'bot_memories'
                                )
                            )
                        else:
                            logger.debug(
                                f"Opinion skipped, similar to "
                                f"existing [{old.category}]: "
                                f"{old.fact}"
                            )
                        continue

                new_op = BotMemory(
                    category="opinion",
                    fact=opinion,
                    importance=2,
                    related_user_ids=None,
                )
                db.add(new_op)
                db.commit()
                logger.info(
                    f"New opinion stored: {opinion} "
                    f"(topic: {topic})"
                )
                asyncio.create_task(
                    memory_manager.store_embedding_for_memory(
                        db, new_op, 'bot_memories'
                    )
                )
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving opinion: {e}")

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

            # Clamp delta to [-1.0, +1.0]
            delta = max(-1.0, min(1.0, delta))
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

    def _track_episode_message(self, message, is_bot=False):
        """Track a message for episodic summarization."""
        channel_id = message.channel.id
        now = time.time()

        # Initialize episode tracking for this channel
        if channel_id not in self.channel_episodes:
            self.channel_episodes[channel_id] = []
            self.channel_msg_counts[channel_id] = 0

        episode = self.channel_episodes[channel_id]

        # Check gap trigger: if last message was >30 min ago,
        # finalize the previous episode
        if (episode and
                now - episode[-1].get('time', 0)
                > EPISODE_GAP_SECONDS):
            self._trigger_episode_summary(channel_id)

        # Add current message
        episode.append({
            'author': message.author.display_name,
            'author_id': str(message.author.id),
            'content': message.content,
            'is_bot': is_bot,
            'timestamp': message.created_at,
            'time': now,
        })
        self.channel_msg_counts[channel_id] = (
            self.channel_msg_counts.get(channel_id, 0) + 1
        )

        # Volume trigger: every 50 messages
        if (self.channel_msg_counts[channel_id]
                >= EPISODE_VOLUME_THRESHOLD):
            self._trigger_episode_summary(channel_id)

    def _trigger_episode_summary(self, channel_id):
        """Trigger summarization of the current episode buffer."""
        episode = self.channel_episodes.get(channel_id, [])
        self.channel_episodes[channel_id] = []
        self.channel_msg_counts[channel_id] = 0

        if len(episode) < EPISODE_MIN_MESSAGES:
            return

        db = getattr(self.bot, 'db', None)
        if not db or not self.client:
            return

        asyncio.create_task(
            memory_manager.summarize_episode(
                self.client, episode, channel_id, db
            )
        )

    async def _generate_response(
        self, message, mentioned, engaged=False
    ):
        # One-time embedding backfill on first response
        if not self._backfill_done:
            self._backfill_done = True
            db = getattr(self.bot, 'db', None)
            if db:
                asyncio.create_task(
                    memory_manager.backfill_embeddings(db)
                )

        history = await self._fetch_history(message.channel, message)
        messages_for_api = self._build_api_messages(history)

        if not messages_for_api:
            return

        if mentioned:
            mention_note = (
                "\n[You were @mentioned directly - respond to "
                "this person.]"
            )
            last = messages_for_api[-1]["content"]
            if isinstance(last, list):
                # Append to the last text block
                for block in reversed(last):
                    if block.get("type") == "text":
                        block["text"] += mention_note
                        break
            else:
                messages_for_api[-1]["content"] = last + mention_note

        # Track incoming message for episode detection
        self._track_episode_message(message, is_bot=False)

        system_prompt = (
            await self._build_system_prompt_with_memories(
                history
            )
        )

        try:
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=system_prompt,
                messages=messages_for_api,
                tools=[{"type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 3}],
            )
            # Extract text from response — when web search is used,
            # the model generates "thinking" text before the search,
            # then the actual answer after. Only keep text blocks
            # that come AFTER the last tool use (web search result).
            last_tool_idx = -1
            for i, block in enumerate(response.content):
                if block.type in ("tool_use", "server_tool_use",
                                  "web_search_tool_result"):
                    last_tool_idx = i

            text_blocks = []
            for i, block in enumerate(response.content):
                if block.type == "text" and i > last_tool_idx:
                    text_blocks.append(block.text)

            reply_text = self._strip_bot_prefix(
                " ".join(text_blocks).strip() if text_blocks
                else ""
            )
            logger.debug(
                f"Response blocks: "
                f"{[(b.type, getattr(b, 'text', '')[:50] if hasattr(b, 'text') else '') for b in response.content]}"
            )
            if not reply_text:
                return

            # Bot chose to react instead of respond
            if reply_text.strip() == "[REACT]":
                try:
                    await self._react_to_message(message)
                except Exception as e:
                    logger.error(f"Reaction error: {e}")
                return

            chunks = self._split_response(reply_text)
            for i, chunk in enumerate(chunks):
                # Show typing, pause, send
                async with message.channel.typing():
                    delay = random.uniform(0.8, 2.5)
                    if i > 0:
                        delay = random.uniform(0.5, 1.5)
                    await asyncio.sleep(delay)
                await message.channel.send(chunk)

            self.engaged_channels[message.channel.id] = (
                time.time()
            )

            # Track bot response for episode detection
            bot_msg_proxy = type('Msg', (), {
                'channel': message.channel,
                'author': type('Author', (), {
                    'display_name': 'BangaBot',
                    'id': self.bot.user.id,
                })(),
                'content': reply_text,
                'created_at': datetime.utcnow(),
            })()
            self._track_episode_message(
                bot_msg_proxy, is_bot=True
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
