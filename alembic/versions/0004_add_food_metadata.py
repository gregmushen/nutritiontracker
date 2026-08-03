"""Add compact product metadata from food source catalogs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE foods ADD COLUMN ingredients_text TEXT")
    for column in (
        "allergens_tags",
        "dietary_tags",
        "categories_tags",
        "labels_tags",
        "countries_tags",
    ):
        op.execute(f"ALTER TABLE foods ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE foods ADD COLUMN nutriscore_grade TEXT")
    op.execute("ALTER TABLE foods ADD COLUMN nova_group INTEGER")
    op.execute("ALTER TABLE foods ADD COLUMN product_quantity REAL")
    op.execute("ALTER TABLE foods ADD COLUMN product_quantity_unit TEXT")


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported for this migration")
