import sqlite3
from pathlib import Path

from app.config import settings
from app.sources import FOOD_SOURCES


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            token_hash TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

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
        );

        CREATE TABLE IF NOT EXISTS foods (
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
            calories_kcal REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            sugar_g REAL,
            added_sugar_g REAL,
            saturated_fat_g REAL,
            trans_fat_g REAL,
            monounsaturated_fat_g REAL,
            polyunsaturated_fat_g REAL,
            fiber_g REAL,
            cholesterol_mg REAL,
            caffeine_mg REAL,
            sodium_mg REAL,
            potassium_mg REAL,
            calcium_mg REAL,
            iron_mg REAL,
            magnesium_mg REAL,
            zinc_mg REAL,
            phosphorus_mg REAL,
            copper_mg REAL,
            manganese_mg REAL,
            selenium_ug REAL,
            chromium_ug REAL,
            iodine_ug REAL,
            vitamin_a_ug REAL,
            vitamin_c_mg REAL,
            vitamin_d_ug REAL,
            vitamin_e_mg REAL,
            vitamin_k_ug REAL,
            thiamin_mg REAL,
            riboflavin_mg REAL,
            vitamin_b6_mg REAL,
            vitamin_b12_ug REAL,
            niacin_mg REAL,
            pantothenic_acid_mg REAL,
            biotin_ug REAL,
            folate_ug REAL,
            folic_acid_ug REAL,
            choline_mg REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS diary_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK(meal_type IN ('breakfast','lunch','dinner','snack')),
            food_id INTEGER NOT NULL REFERENCES foods(id),
            food_snapshot TEXT NOT NULL,
            food_name TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL,
            unit TEXT NOT NULL,
            grams REAL NOT NULL,
            nutrients_total TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            servings REAL NOT NULL,
            total_weight_g REAL NOT NULL,
            ingredients TEXT NOT NULL,
            nutrients_per_100 TEXT NOT NULL,
            nutrients_per_serving TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kitchen_inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            canonical_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('have','use_soon','maybe','out','staple')),
            location TEXT CHECK(location IN ('fridge','freezer','pantry','other')),
            category TEXT,
            notes TEXT,
            last_confirmed_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, canonical_name)
        );

        CREATE TABLE IF NOT EXISTS favorite_meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            prep_time_minutes INTEGER,
            effort TEXT CHECK(effort IN ('low','medium','high')),
            favorite_score INTEGER NOT NULL DEFAULT 0,
            nutrition_template_id INTEGER,
            last_made_at TEXT,
            times_made INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS favorite_meal_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER NOT NULL REFERENCES favorite_meals(id) ON DELETE CASCADE,
            canonical_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('required','optional','substitution')),
            category TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            canonical_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            checked INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL CHECK(source IN ('manual','meal_plan','inventory','staple_refresh','suggestion')),
            linked_meal_ids TEXT NOT NULL DEFAULT '[]',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, canonical_name)
        );

        CREATE INDEX IF NOT EXISTS idx_kitchen_inventory_user_status
            ON kitchen_inventory_items(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_favorite_meals_user
            ON favorite_meals(user_id);
        CREATE INDEX IF NOT EXISTS idx_favorite_meal_ingredients_meal
            ON favorite_meal_ingredients(meal_id);
        CREATE INDEX IF NOT EXISTS idx_shopping_list_user_checked
            ON shopping_list_items(user_id, checked);

        CREATE TABLE IF NOT EXISTS weight_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_foods_barcode ON foods(barcode);
        CREATE INDEX IF NOT EXISTS idx_foods_source ON foods(source);
        CREATE INDEX IF NOT EXISTS idx_foods_owner ON foods(owner_user_id);
        CREATE INDEX IF NOT EXISTS idx_foods_source_code ON foods(source, source_code);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_shared_source_code_unique
            ON foods(source, source_code)
            WHERE source_code IS NOT NULL AND owner_user_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_owned_source_code_unique
            ON foods(owner_user_id, source, source_code)
            WHERE source_code IS NOT NULL AND owner_user_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_diary_user_date ON diary_entries(user_id, date);
        CREATE INDEX IF NOT EXISTS idx_diary_food_name ON diary_entries(user_id, food_name);
        CREATE INDEX IF NOT EXISTS idx_weight_user_date ON weight_entries(user_id, date);

        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            body TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            mood_score INTEGER,
            stress_score INTEGER,
            sleep_quality INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_journal_user_date ON journal_entries(user_id, date);

        CREATE TABLE IF NOT EXISTS step_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            local_date TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            steps_total_today INTEGER NOT NULL,
            timezone TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            steps INTEGER NOT NULL,
            last_observed_at TEXT NOT NULL,
            anomaly_flag INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, date, source)
        );

        CREATE INDEX IF NOT EXISTS idx_step_obs_user_date ON step_observations(user_id, local_date);
        CREATE INDEX IF NOT EXISTS idx_daily_activity_user_date ON daily_activity(user_id, date);
    """)
    seed_default_user(conn)
    seed_food_sources(conn)


def seed_default_user(conn: sqlite3.Connection) -> None:
    """Ensure the user every unowned row is attributed to actually exists.

    Owned rows carry ``owner_user_id = settings.default_user_id``, and that
    column has a foreign key onto ``users``. Seeding a hardcoded id 1 while the
    deployment is configured for a different one leaves the configured user
    missing, so every write fails the constraint.
    """
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name) VALUES (?, 'Default user')",
        (settings.default_user_id,),
    )
    conn.commit()


def seed_food_sources(conn: sqlite3.Connection) -> None:
    """Upsert the built-in data-source registry.

    Runs on every startup so a deployment picks up newly registered sources
    and refreshed licence or dataset-version metadata without a migration.
    """
    conn.executemany(
        """
        INSERT INTO food_sources
            (code, label, publisher, tier, license, url, citation, dataset_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            label = excluded.label,
            publisher = excluded.publisher,
            tier = excluded.tier,
            license = excluded.license,
            url = excluded.url,
            citation = excluded.citation,
            dataset_version = excluded.dataset_version,
            updated_at = datetime('now')
        """,
        [
            (
                s.code, s.label, s.publisher, s.tier, s.license,
                s.url, s.citation, s.dataset_version,
            )
            for s in FOOD_SOURCES
        ],
    )
    conn.commit()
