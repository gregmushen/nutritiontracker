import sqlite3
from pathlib import Path

from app.config import settings


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
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL CHECK(source IN ('custom','open_food_facts','food_data_central','recipe')),
            source_code TEXT,
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
            calories_kcal REAL DEFAULT 0,
            protein_g REAL DEFAULT 0,
            carbs_g REAL DEFAULT 0,
            fat_g REAL DEFAULT 0,
            sugar_g REAL DEFAULT 0,
            added_sugar_g REAL DEFAULT 0,
            saturated_fat_g REAL DEFAULT 0,
            trans_fat_g REAL DEFAULT 0,
            monounsaturated_fat_g REAL DEFAULT 0,
            polyunsaturated_fat_g REAL DEFAULT 0,
            fiber_g REAL DEFAULT 0,
            cholesterol_mg REAL DEFAULT 0,
            caffeine_mg REAL DEFAULT 0,
            sodium_mg REAL DEFAULT 0,
            potassium_mg REAL DEFAULT 0,
            calcium_mg REAL DEFAULT 0,
            iron_mg REAL DEFAULT 0,
            magnesium_mg REAL DEFAULT 0,
            zinc_mg REAL DEFAULT 0,
            phosphorus_mg REAL DEFAULT 0,
            copper_mg REAL DEFAULT 0,
            manganese_mg REAL DEFAULT 0,
            selenium_ug REAL DEFAULT 0,
            chromium_ug REAL DEFAULT 0,
            iodine_ug REAL DEFAULT 0,
            vitamin_a_ug REAL DEFAULT 0,
            vitamin_c_mg REAL DEFAULT 0,
            vitamin_d_ug REAL DEFAULT 0,
            vitamin_e_mg REAL DEFAULT 0,
            vitamin_k_ug REAL DEFAULT 0,
            thiamin_mg REAL DEFAULT 0,
            riboflavin_mg REAL DEFAULT 0,
            vitamin_b6_mg REAL DEFAULT 0,
            vitamin_b12_ug REAL DEFAULT 0,
            niacin_mg REAL DEFAULT 0,
            pantothenic_acid_mg REAL DEFAULT 0,
            biotin_ug REAL DEFAULT 0,
            folate_ug REAL DEFAULT 0,
            folic_acid_ug REAL DEFAULT 0,
            choline_mg REAL DEFAULT 0,
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
        CREATE INDEX IF NOT EXISTS idx_foods_source_code ON foods(source, source_code);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_source_code_unique ON foods(source, source_code) WHERE source_code IS NOT NULL;
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
