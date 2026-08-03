"""Add the food source registry and make unknown nutrient values NULL.

Two related provenance changes:

1. `food_sources` records who published each dataset, its licence, citation
   text and a quality tier. `foods.source` becomes a foreign key onto it, so
   registering a new dataset no longer needs a schema migration.
2. Nutrient columns lose `DEFAULT 0`. A missing nutrient used to be stored as
   0, which is indistinguishable from a measured zero — spinach with no
   vitamin K assay looked identical to a food that genuinely contains none.
   NULL now means "not known", 0 means "measured as zero".

Existing rows keep whatever values they already have; re-importing a dataset
replaces the placeholder zeros with NULLs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


NUTRIENT_COLUMNS = (
    "calories_kcal", "protein_g", "carbs_g", "fat_g", "sugar_g", "added_sugar_g",
    "saturated_fat_g", "trans_fat_g", "monounsaturated_fat_g",
    "polyunsaturated_fat_g", "fiber_g", "cholesterol_mg", "caffeine_mg",
    "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg",
    "zinc_mg", "phosphorus_mg", "copper_mg", "manganese_mg", "selenium_ug",
    "chromium_ug", "iodine_ug", "vitamin_a_ug", "vitamin_c_mg", "vitamin_d_ug",
    "vitamin_e_mg", "vitamin_k_ug", "thiamin_mg", "riboflavin_mg",
    "vitamin_b6_mg", "vitamin_b12_ug", "niacin_mg", "pantothenic_acid_mg",
    "biotin_ug", "folate_ug", "folic_acid_ug", "choline_mg",
)

BASE_COLUMNS = (
    "id", "source", "source_code", "owner_user_id", "name", "brand", "barcode",
    "image_url", "serving_quantity", "serving_unit", "serving_size_text",
    "ingredients_text", "allergens_tags", "dietary_tags", "categories_tags",
    "labels_tags", "countries_tags", "nutriscore_grade", "nova_group",
    "product_quantity", "product_quantity_unit", "base_quantity", "base_unit",
    "density_g_per_ml",
)

# (code, label, publisher, tier, license, url, citation, dataset_version)
USDA_PUBLISHER = "U.S. Department of Agriculture, Agricultural Research Service"
USDA_LICENSE = "Public domain (U.S. Government work)"
USDA_URL = "https://fdc.nal.usda.gov/"

SEED_SOURCES = (
    ("custom", "Custom food", "User", 0, "Private to the owning user", "", None, None),
    ("recipe", "Recipe", "User", 0, "Private to the owning user", "", None, None),
    (
        "usda_fndds",
        "USDA Food and Nutrient Database for Dietary Studies (FNDDS)",
        USDA_PUBLISHER,
        1,
        USDA_LICENSE,
        USDA_URL,
        (
            "U.S. Department of Agriculture, Agricultural Research Service. Food "
            "and Nutrient Database for Dietary Studies. FoodData Central, "
            "fdc.nal.usda.gov."
        ),
        None,
    ),
    (
        "usda_foundation",
        "USDA FoodData Central Foundation Foods",
        USDA_PUBLISHER,
        2,
        USDA_LICENSE,
        "https://fdc.nal.usda.gov/food-search?type=Foundation",
        (
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central: Foundation Foods, fdc.nal.usda.gov."
        ),
        None,
    ),
    (
        "usda_sr_legacy",
        "USDA National Nutrient Database for Standard Reference (SR Legacy)",
        USDA_PUBLISHER,
        3,
        USDA_LICENSE,
        USDA_URL,
        (
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "National Nutrient Database for Standard Reference, Legacy (2018). "
            "FoodData Central, fdc.nal.usda.gov."
        ),
        "SR Legacy (final release, 2018)",
    ),
    (
        "food_data_central",
        "USDA FoodData Central (unspecified dataset)",
        USDA_PUBLISHER,
        3,
        USDA_LICENSE,
        USDA_URL,
        (
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central, fdc.nal.usda.gov."
        ),
        "Legacy import — re-import to resolve the exact dataset",
    ),
    (
        "usda_branded",
        "USDA FoodData Central Branded Foods",
        "U.S. Department of Agriculture / food industry data owners",
        4,
        USDA_LICENSE,
        USDA_URL,
        (
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central: Branded Foods, fdc.nal.usda.gov."
        ),
        None,
    ),
    (
        "open_food_facts",
        "Open Food Facts",
        "Open Food Facts contributors",
        4,
        "Open Database License (ODbL) v1.0; contents under DbCL v1.0",
        "https://world.openfoodfacts.org/",
        (
            "Open Food Facts contributors. Open Food Facts database, "
            "openfoodfacts.org, made available under the Open Database License."
        ),
        None,
    ),
)


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS food_sources (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            publisher TEXT NOT NULL,
            tier INTEGER NOT NULL,
            license TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            citation TEXT,
            dataset_version TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    for row in SEED_SOURCES:
        values = ", ".join(_sql_literal(v) for v in row)
        op.execute(
            "INSERT OR IGNORE INTO food_sources "
            "(code, label, publisher, tier, license, url, citation, dataset_version) "
            f"VALUES ({values})"
        )

    # Any source code already in use but not registered (e.g. a hand-edited
    # database) has to exist before the foreign key is enforced.
    op.execute("""
        INSERT OR IGNORE INTO food_sources (code, label, publisher, tier, license)
        SELECT DISTINCT source, source, 'Unknown', 99, 'Unknown'
        FROM foods
    """)

    op.execute("DROP TRIGGER IF EXISTS foods_ai")
    op.execute("DROP TRIGGER IF EXISTS foods_ad")
    op.execute("DROP TRIGGER IF EXISTS foods_au")

    nutrient_ddl = ",\n            ".join(f"{c} REAL" for c in NUTRIENT_COLUMNS)
    op.execute(f"""
        CREATE TABLE foods_rebuilt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL REFERENCES food_sources(code),
            source_code TEXT,
            owner_user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            brand TEXT,
            barcode TEXT,
            image_url TEXT,
            serving_quantity REAL,
            serving_unit TEXT,
            serving_size_text TEXT,
            ingredients_text TEXT,
            allergens_tags TEXT NOT NULL DEFAULT '[]',
            dietary_tags TEXT NOT NULL DEFAULT '[]',
            categories_tags TEXT NOT NULL DEFAULT '[]',
            labels_tags TEXT NOT NULL DEFAULT '[]',
            countries_tags TEXT NOT NULL DEFAULT '[]',
            nutriscore_grade TEXT,
            nova_group INTEGER,
            product_quantity REAL,
            product_quantity_unit TEXT,
            base_quantity REAL NOT NULL DEFAULT 100,
            base_unit TEXT NOT NULL DEFAULT 'g',
            density_g_per_ml REAL,
            {nutrient_ddl},
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    columns = ", ".join(BASE_COLUMNS + NUTRIENT_COLUMNS + ("created_at", "updated_at"))
    op.execute(f"INSERT INTO foods_rebuilt ({columns}) SELECT {columns} FROM foods")
    op.execute("DROP TABLE foods")
    op.execute("ALTER TABLE foods_rebuilt RENAME TO foods")

    op.execute("CREATE INDEX idx_foods_barcode ON foods(barcode)")
    op.execute("CREATE INDEX idx_foods_source ON foods(source)")
    op.execute("CREATE INDEX idx_foods_owner ON foods(owner_user_id)")
    op.execute("CREATE INDEX idx_foods_source_code ON foods(source, source_code)")
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

    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
            name, brand, content='foods', content_rowid='id',
            tokenize='porter unicode61'
        )
    """)
    op.execute("""
        CREATE TRIGGER foods_ai AFTER INSERT ON foods BEGIN
            INSERT INTO foods_fts(rowid, name, brand)
            VALUES (new.id, new.name, new.brand);
        END
    """)
    op.execute("""
        CREATE TRIGGER foods_ad AFTER DELETE ON foods BEGIN
            INSERT INTO foods_fts(foods_fts, rowid, name, brand)
            VALUES ('delete', old.id, old.name, old.brand);
        END
    """)
    op.execute("""
        CREATE TRIGGER foods_au AFTER UPDATE ON foods BEGIN
            INSERT INTO foods_fts(foods_fts, rowid, name, brand)
            VALUES ('delete', old.id, old.name, old.brand);
            INSERT INTO foods_fts(rowid, name, brand)
            VALUES (new.id, new.name, new.brand);
        END
    """)


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported for this migration")
