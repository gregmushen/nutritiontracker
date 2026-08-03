"""Add per-user identities and custom-food ownership.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-01
"""
import os

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _default_user_id() -> int:
    """The id the application will attribute pre-existing rows to.

    Read from the environment rather than app.config so this migration stays
    importable without the application package, matching how env.py resolves
    the database path. Seeding a different id than the app is configured for
    would leave every legacy row pointing at a user that does not exist.
    """
    raw = os.environ.get("NT_DEFAULT_USER_ID", "1")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"NT_DEFAULT_USER_ID must be an integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"NT_DEFAULT_USER_ID must be a positive rowid, got {value}")
    return value


def upgrade() -> None:
    default_user_id = _default_user_id()
    op.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            token_hash TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute(f"INSERT INTO users (id, name) VALUES ({default_user_id}, 'Default user')")
    op.execute("ALTER TABLE foods ADD COLUMN owner_user_id INTEGER REFERENCES users(id)")
    op.execute(
        f"UPDATE foods SET owner_user_id = {default_user_id} "
        "WHERE source IN ('custom', 'recipe')"
    )
    op.execute("CREATE INDEX idx_foods_owner ON foods(owner_user_id)")
    op.execute("DROP INDEX IF EXISTS idx_foods_source_code_unique")
    op.execute(
        "CREATE UNIQUE INDEX idx_foods_shared_source_code_unique "
        "ON foods(source, source_code) "
        "WHERE source_code IS NOT NULL AND owner_user_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_foods_owned_source_code_unique "
        "ON foods(owner_user_id, source, source_code) "
        "WHERE source_code IS NOT NULL AND owner_user_id IS NOT NULL"
    )


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported for this migration")
