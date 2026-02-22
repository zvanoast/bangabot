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


# Register migrations in order. Each entry is (name, function).
MIGRATIONS = [
    ("0001_sentiment_score_to_float",
     migration_0001_sentiment_score_to_float),
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
