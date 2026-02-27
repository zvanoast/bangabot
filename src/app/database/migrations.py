"""
Lightweight database migration runner.

Each migration is a function named `migration_NNNN_description` that
receives a SQLAlchemy connection. Migrations run inside a transaction
and are tracked in a `schema_migrations` table so they only execute
once. Add new migrations to the MIGRATIONS list at the bottom.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger('bangabot')


def _ensure_migrations_table(conn):
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  id SERIAL PRIMARY KEY,"
        "  name VARCHAR(255) UNIQUE NOT NULL,"
        "  applied_at TIMESTAMP DEFAULT NOW()"
        ")"
    ))


def _already_applied(conn, name):
    result = conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE name = :name"),
        {"name": name}
    )
    return result.fetchone() is not None


def _mark_applied(conn, name):
    conn.execute(
        text("INSERT INTO schema_migrations (name) VALUES (:name)"),
        {"name": name}
    )


# --- Migrations ---

def migration_0001_sentiment_score_to_float(conn):
    """Change user_sentiments.score from integer to double precision."""
    result = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'user_sentiments' "
        "AND column_name = 'score'"
    ))
    row = result.fetchone()
    if row and row[0] == 'integer':
        conn.execute(text(
            "ALTER TABLE user_sentiments "
            "ALTER COLUMN score TYPE DOUBLE PRECISION"
        ))
        logger.info(
            "Migrated user_sentiments.score from integer to float"
        )


def migration_0002_user_memory_importance(conn):
    """Add importance column to user_memories."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'user_memories' "
        "AND column_name = 'importance'"
    ))
    if not result.fetchone():
        conn.execute(text(
            "ALTER TABLE user_memories "
            "ADD COLUMN importance INTEGER DEFAULT 2"
        ))
        logger.info("Added importance column to user_memories")


def migration_0003_bot_memory_importance(conn):
    """Add importance column to bot_memories."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'bot_memories' "
        "AND column_name = 'importance'"
    ))
    if not result.fetchone():
        conn.execute(text(
            "ALTER TABLE bot_memories "
            "ADD COLUMN importance INTEGER DEFAULT 2"
        ))
        logger.info("Added importance column to bot_memories")


def migration_0004_enable_pgvector(conn):
    """Enable the pgvector extension."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    logger.info("Enabled pgvector extension")


def migration_0005_user_memory_embedding(conn):
    """Add embedding column to user_memories."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'user_memories' "
        "AND column_name = 'embedding'"
    ))
    if not result.fetchone():
        conn.execute(text(
            "ALTER TABLE user_memories "
            "ADD COLUMN embedding vector(384)"
        ))
        logger.info("Added embedding column to user_memories")


def migration_0006_bot_memory_embedding(conn):
    """Add embedding column to bot_memories."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'bot_memories' "
        "AND column_name = 'embedding'"
    ))
    if not result.fetchone():
        conn.execute(text(
            "ALTER TABLE bot_memories "
            "ADD COLUMN embedding vector(384)"
        ))
        logger.info("Added embedding column to bot_memories")


def migration_0007_create_episodic_summaries(conn):
    """Create the episodic_summaries table."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'episodic_summaries'"
    ))
    if not result.fetchone():
        conn.execute(text(
            "CREATE TABLE episodic_summaries ("
            "  id SERIAL PRIMARY KEY,"
            "  channel_id VARCHAR NOT NULL,"
            "  summary TEXT NOT NULL,"
            "  participant_ids VARCHAR,"
            "  message_count INTEGER,"
            "  started_at TIMESTAMP,"
            "  ended_at TIMESTAMP,"
            "  embedding vector(384),"
            "  created_at TIMESTAMP DEFAULT NOW()"
            ")"
        ))
        conn.execute(text(
            "CREATE INDEX ix_episodic_channel "
            "ON episodic_summaries (channel_id)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_episodic_ended "
            "ON episodic_summaries (ended_at DESC)"
        ))
        logger.info("Created episodic_summaries table")


# Register migrations in order. Each entry is (name, function).
MIGRATIONS = [
    ("0001_sentiment_score_to_float",
     migration_0001_sentiment_score_to_float),
    ("0002_user_memory_importance",
     migration_0002_user_memory_importance),
    ("0003_bot_memory_importance",
     migration_0003_bot_memory_importance),
    ("0004_enable_pgvector",
     migration_0004_enable_pgvector),
    ("0005_user_memory_embedding",
     migration_0005_user_memory_embedding),
    ("0006_bot_memory_embedding",
     migration_0006_bot_memory_embedding),
    ("0007_create_episodic_summaries",
     migration_0007_create_episodic_summaries),
]


def run_migrations(engine):
    """Run all pending migrations."""
    with engine.begin() as conn:
        _ensure_migrations_table(conn)
        for name, func in MIGRATIONS:
            if _already_applied(conn, name):
                continue
            logger.info(f"Running migration: {name}")
            func(conn)
            _mark_applied(conn, name)
            logger.info(f"Migration complete: {name}")
