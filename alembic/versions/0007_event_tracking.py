"""Add user-defined event types and the events logged against them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-02
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE event_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            unit TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Scoped to the user, not global: two people tracking "Sauna" are tracking
    # their own thing, and one naming a type must not collide with the other.
    op.execute(
        "CREATE UNIQUE INDEX idx_event_types_user_name ON event_types(user_id, name)"
    )
    op.execute("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            event_type_id INTEGER NOT NULL REFERENCES event_types(id),
            date TEXT NOT NULL,
            at TEXT,
            value REAL,
            unit TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute("CREATE INDEX idx_events_user_date ON events(user_id, date)")
    op.execute("CREATE INDEX idx_events_type ON events(event_type_id)")


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported for this migration")
