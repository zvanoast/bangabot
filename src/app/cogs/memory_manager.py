"""
Memory manager: embeddings, vector search, episodic summaries,
and similarity-based deduplication.

Uses sentence-transformers with all-MiniLM-L6-v2 for local
embeddings (384 dims). No external API key required.
"""
import time
import asyncio
import logging
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger('bangabot')

# Local embedding model (lazy-initialized)
_model = None
_model_failed = False


def _get_model():
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info(
            "Loaded embedding model: all-MiniLM-L6-v2 "
            "(384 dims)"
        )
        return _model
    except Exception as e:
        _model_failed = True
        logger.error(f"Failed to load embedding model: {e}")
        return None


def estimate_tokens(text_str):
    """Estimate token count. Overestimates for safety."""
    return len(text_str) // 4


# --- Embedding ---

# Cache: channel_id -> (timestamp, embedding_vector)
_embedding_cache = {}
_CACHE_TTL = 60  # seconds


async def embed_text(text_str):
    """Embed a text string locally. Returns list[float] or None."""
    model = _get_model()
    if not model:
        return None
    try:
        vec = await asyncio.to_thread(
            model.encode, text_str
        )
        return vec.tolist()
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return None


async def get_conversation_embedding(channel_id, messages):
    """Get embedding for conversation context, with 60s cache."""
    now = time.time()
    cached = _embedding_cache.get(channel_id)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    context = "\n".join(
        f"{msg.author.display_name}: {msg.content}"
        for msg in messages[-5:]
        if msg.content.strip()
    )
    if not context:
        return None

    vec = await embed_text(context)
    if vec:
        _embedding_cache[channel_id] = (now, vec)
    return vec


# --- Embedding storage (background tasks) ---

async def store_embedding_for_memory(db, memory_row, table_name):
    """Compute and store an embedding for a memory row."""
    vec = await embed_text(memory_row.fact)
    if vec is None:
        return
    try:
        await asyncio.to_thread(
            _store_embedding_sync, db, table_name,
            memory_row.id, vec
        )
    except Exception as e:
        logger.error(
            f"Failed to store embedding for {table_name} "
            f"id={memory_row.id}: {e}"
        )


def _store_embedding_sync(db, table_name, row_id, vec):
    """Synchronous helper to store embedding via raw SQL."""
    from database.database import engine
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {table_name} SET embedding = :vec "
                f"WHERE id = :id"
            ),
            {"vec": vec_str, "id": row_id}
        )


async def store_embedding_for_summary(db, summary_row):
    """Compute and store an embedding for an episodic summary."""
    vec = await embed_text(summary_row.summary)
    if vec is None:
        return
    try:
        await asyncio.to_thread(
            _store_embedding_sync, db, 'episodic_summaries',
            summary_row.id, vec
        )
    except Exception as e:
        logger.error(
            f"Failed to store embedding for summary "
            f"id={summary_row.id}: {e}"
        )


# --- Vector search ---

def _vector_search_sync(db, table_name, query_vec, limit=15):
    """Run a vector similarity search. Returns list of row IDs."""
    from database.database import engine
    vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"SELECT id FROM {table_name} "
                f"WHERE embedding IS NOT NULL "
                f"ORDER BY embedding <=> :vec "
                f"LIMIT :lim"
            ),
            {"vec": vec_str, "lim": limit}
        )
        return [row[0] for row in result.fetchall()]


async def vector_search(db, table_name, query_vec, limit=15):
    """Async vector similarity search. Returns list of row IDs."""
    if query_vec is None:
        return []
    try:
        return await asyncio.to_thread(
            _vector_search_sync, db, table_name, query_vec,
            limit
        )
    except Exception as e:
        logger.error(f"Vector search on {table_name} failed: {e}")
        return []


# --- Retrieval ---

async def retrieve_memories(db, participants, history,
                            channel_id):
    """Build token-budgeted memory lines for the system prompt.

    Returns (memory_lines, summary_lines) where each is a list
    of formatted strings ready for injection.
    """
    from database.orm import UserMemory, BotMemory

    MEMORY_BUDGET = 1000
    SUMMARY_BUDGET = 500
    memory_lines = []
    token_count = 0

    # Get conversation embedding for vector search
    conv_vec = await get_conversation_embedding(
        channel_id, history
    )

    # --- Tier 1: Core facts ---

    # Importance-sorted user memories
    importance_rows = {}  # id -> (line, importance)
    for uid, name in participants.items():
        try:
            rows = await asyncio.to_thread(
                lambda u=uid: db.query(UserMemory)
                .filter(UserMemory.user_id == u)
                .order_by(
                    UserMemory.importance.desc(),
                    UserMemory.updated_at.desc()
                )
                .limit(50)
                .all()
            )
            for row in rows:
                imp = row.importance or 2
                if imp == 3:
                    line = (
                        f"- About {name} "
                        f"(importance: high): {row.fact}"
                    )
                else:
                    line = f"- About {name}: {row.fact}"
                importance_rows[row.id] = (line, imp, 'user')
        except Exception as e:
            logger.error(
                f"Error fetching user memories for {uid}: {e}"
            )

    # Importance-sorted bot memories
    try:
        bot_rows = await asyncio.to_thread(
            lambda: db.query(BotMemory)
            .order_by(
                BotMemory.importance.desc(),
                BotMemory.updated_at.desc()
            )
            .limit(50)
            .all()
        )
        for row in bot_rows:
            line = f"- [{row.category}] {row.fact}"
            importance_rows[('bot', row.id)] = (
                line, row.importance or 2, 'bot'
            )
    except Exception as e:
        logger.error(f"Error fetching bot memories: {e}")

    # Vector-retrieved IDs
    vec_user_ids = set()
    vec_bot_ids = set()
    if conv_vec:
        vec_user_ids = set(await vector_search(
            db, 'user_memories', conv_vec, 15
        ))
        vec_bot_ids = set(await vector_search(
            db, 'bot_memories', conv_vec, 15
        ))

    # Merge: importance-3 first, then vector-top, then
    # importance-2, then importance-1
    seen_ids = set()
    buckets = {3: [], 'vec': [], 2: [], 1: []}

    for key, (line, imp, source) in importance_rows.items():
        row_id = key if source == 'user' else key[1]
        full_key = (source, row_id)

        is_vec = (
            (source == 'user' and row_id in vec_user_ids) or
            (source == 'bot' and row_id in vec_bot_ids)
        )

        if imp == 3:
            buckets[3].append((full_key, line))
        elif is_vec:
            buckets['vec'].append((full_key, line))
        elif imp == 2:
            buckets[2].append((full_key, line))
        else:
            buckets[1].append((full_key, line))

    # Also add vector results not in importance_rows
    # (could be lower importance but semantically relevant)
    for vid in vec_user_ids:
        fk = ('user', vid)
        all_keys = {
            b[0] for bucket in buckets.values()
            for b in bucket
        }
        if fk not in all_keys:
            # Fetch the row
            try:
                row = await asyncio.to_thread(
                    lambda v=vid: db.query(UserMemory)
                    .filter(UserMemory.id == v).first()
                )
                if row:
                    name = participants.get(
                        row.user_id, row.user_name
                    )
                    line = f"- About {name}: {row.fact}"
                    buckets['vec'].append((fk, line))
            except Exception:
                pass

    for vid in vec_bot_ids:
        fk = ('bot', vid)
        all_keys = {
            b[0] for bucket in buckets.values()
            for b in bucket
        }
        if fk not in all_keys:
            try:
                row = await asyncio.to_thread(
                    lambda v=vid: db.query(BotMemory)
                    .filter(BotMemory.id == v).first()
                )
                if row:
                    line = f"- [{row.category}] {row.fact}"
                    buckets['vec'].append((fk, line))
            except Exception:
                pass

    # Assemble with budget
    for bucket_key in [3, 'vec', 2, 1]:
        for full_key, line in buckets[bucket_key]:
            if full_key in seen_ids:
                continue
            cost = estimate_tokens(line)
            if token_count + cost > MEMORY_BUDGET:
                continue
            memory_lines.append(line)
            token_count += cost
            seen_ids.add(full_key)

    # --- Tier 2: Episodic summaries ---
    summary_lines = await retrieve_summaries(
        db, channel_id, participants, conv_vec,
        SUMMARY_BUDGET
    )

    return memory_lines, summary_lines


async def retrieve_summaries(db, channel_id, participants,
                             conv_vec, budget):
    """Retrieve episodic summaries with token budget."""
    from database.orm import EpisodicSummary

    lines = []
    token_count = 0
    seen_ids = set()

    # Recent from current channel
    try:
        channel_rows = await asyncio.to_thread(
            lambda: db.query(EpisodicSummary)
            .filter(EpisodicSummary.channel_id == str(
                channel_id))
            .order_by(EpisodicSummary.ended_at.desc())
            .limit(3)
            .all()
        )
        for row in channel_rows:
            age = _format_age(row.ended_at)
            line = f"- In this channel ({age}): {row.summary}"
            cost = estimate_tokens(line)
            if token_count + cost > budget:
                break
            lines.append(line)
            token_count += cost
            seen_ids.add(row.id)
    except Exception as e:
        logger.error(f"Error fetching channel summaries: {e}")

    # Vector-similar from any channel
    if conv_vec:
        vec_ids = await vector_search(
            db, 'episodic_summaries', conv_vec, 5
        )
        for sid in vec_ids:
            if sid in seen_ids:
                continue
            try:
                row = await asyncio.to_thread(
                    lambda s=sid: db.query(EpisodicSummary)
                    .filter(EpisodicSummary.id == s).first()
                )
                if not row:
                    continue
                age = _format_age(row.ended_at)
                line = (
                    f"- In another channel ({age}): "
                    f"{row.summary}"
                )
                cost = estimate_tokens(line)
                if token_count + cost > budget:
                    break
                lines.append(line)
                token_count += cost
                seen_ids.add(row.id)
            except Exception:
                pass

    return lines


def _format_age(dt):
    """Format a datetime as a human-readable age string."""
    if not dt:
        return "recently"
    now = datetime.utcnow()
    delta = now - dt
    if delta.days > 7:
        return f"{delta.days // 7} weeks ago"
    elif delta.days > 0:
        return f"{delta.days} days ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600} hours ago"
    else:
        return "recently"


# --- Episodic summarization ---

async def summarize_episode(client, messages, channel_id, db):
    """Summarize a conversation episode and store it."""
    from database.orm import EpisodicSummary

    if not messages or len(messages) < 5:
        return

    # Check bot participation
    bot_participated = any(
        msg.get('is_bot', False) for msg in messages
    )
    if not bot_participated:
        return

    convo_text = "\n".join(
        f"{msg['author']}: {msg['content']}"
        for msg in messages if msg['content'].strip()
    )

    participant_ids = list(set(
        msg['author_id'] for msg in messages
        if not msg.get('is_bot', False)
    ))

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=(
                "Summarize this Discord conversation in 2-4 "
                "sentences. Note who said what notable things, "
                "any decisions made, and the emotional tone. "
                "Be concise."
            ),
            messages=[{
                "role": "user",
                "content": convo_text
            }],
        )
        summary = response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Episode summarization failed: {e}")
        return

    started_at = messages[0].get('timestamp')
    ended_at = messages[-1].get('timestamp')

    try:
        new_summary = EpisodicSummary(
            channel_id=str(channel_id),
            summary=summary,
            participant_ids=",".join(participant_ids),
            message_count=len(messages),
            started_at=started_at,
            ended_at=ended_at,
        )
        db.add(new_summary)
        db.commit()
        logger.info(
            f"Episodic summary stored for channel "
            f"{channel_id}: {summary[:80]}..."
        )

        # Enforce cap: 200 summaries
        count = db.query(EpisodicSummary).count()
        if count > 200:
            oldest = (
                db.query(EpisodicSummary)
                .order_by(EpisodicSummary.created_at.asc())
                .first()
            )
            if oldest:
                db.delete(oldest)
                db.commit()

        # Store embedding in background
        asyncio.create_task(
            store_embedding_for_summary(db, new_summary)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving episodic summary: {e}")


# --- Similarity dedup ---

def _cosine_similarity_sync(db, table_name, row_embedding,
                            exclude_id=None, threshold=0.85,
                            filter_col=None, filter_val=None):
    """Find rows with cosine similarity > threshold."""
    from database.database import engine
    vec_str = "[" + ",".join(str(v) for v in row_embedding) + "]"

    where_clauses = ["embedding IS NOT NULL"]
    params = {"vec": vec_str, "threshold": threshold}

    if exclude_id is not None:
        where_clauses.append("id != :exclude_id")
        params["exclude_id"] = exclude_id
    if filter_col and filter_val:
        where_clauses.append(f"{filter_col} = :fval")
        params["fval"] = filter_val

    where = " AND ".join(where_clauses)

    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"SELECT id, 1 - (embedding <=> :vec) as sim "
                f"FROM {table_name} "
                f"WHERE {where} "
                f"AND 1 - (embedding <=> :vec) > :threshold "
                f"ORDER BY sim DESC LIMIT 5"
            ),
            params
        )
        return [(row[0], row[1]) for row in result.fetchall()]


async def find_similar_memories(db, table_name, fact_text,
                                user_id=None):
    """Find memories similar to fact_text (>0.85 cosine sim).

    Returns list of (row_id, similarity_score) tuples,
    or empty list if no embeddings available.
    """
    vec = await embed_text(fact_text)
    if vec is None:
        return []
    try:
        filter_col = 'user_id' if user_id else None
        return await asyncio.to_thread(
            _cosine_similarity_sync, db, table_name, vec,
            None, 0.85, filter_col, user_id
        )
    except Exception as e:
        logger.error(f"Similarity search failed: {e}")
        return []


# --- Backfill ---

async def backfill_embeddings(db):
    """Backfill embeddings for rows that have none.
    Called once on startup."""
    from database.orm import UserMemory, BotMemory, EpisodicSummary

    model = _get_model()
    if not model:
        logger.info(
            "Skipping embedding backfill - no model loaded"
        )
        return

    count = 0
    for Model, table_name in [
        (UserMemory, 'user_memories'),
        (BotMemory, 'bot_memories'),
        (EpisodicSummary, 'episodic_summaries'),
    ]:
        try:
            text_col = (
                'summary' if Model == EpisodicSummary
                else 'fact'
            )
            rows = (
                db.query(Model)
                .filter(Model.embedding.is_(None))
                .limit(200)
                .all()
            )
            for row in rows:
                content = getattr(row, text_col, None)
                if not content:
                    continue
                vec = await embed_text(content)
                if vec:
                    await asyncio.to_thread(
                        _store_embedding_sync, db,
                        table_name, row.id, vec
                    )
                    count += 1
                # Small yield to avoid blocking event loop
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(
                f"Backfill error for {table_name}: {e}"
            )

    if count > 0:
        logger.info(f"Backfilled {count} embeddings")
