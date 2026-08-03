# Kitchen Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Kitchen Memory API that tracks presence-based kitchen inventory, favorite meals, meal recommendations, and shopping list generation without requiring exact ingredient quantities.

**Architecture:** Build this as a backend-only FastAPI feature in the existing SQLite/repository/route pattern. V1 adds kitchen tables, Pydantic models, repositories, deterministic scoring services, and `/kitchen/*` endpoints. Natural language and UI are deferred until this structured backend surface is stable.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, existing `app/database.py` schema initialization and repository pattern.

---

## File Structure

- Modify: `app/database.py` - add Kitchen Memory tables and indexes to `init_schema()`
- Create: `app/models/kitchen.py` - request/response models and literal types
- Create: `app/repositories/kitchen.py` - inventory, favorite meal, and shopping list persistence
- Create: `app/services/kitchen.py` - canonicalization, meal matching, shopping-list generation
- Create: `app/routes/kitchen.py` - `/kitchen/*` API endpoints
- Modify: `app/main.py` - include kitchen router
- Create: `tests/test_kitchen_repository.py` - repository behavior
- Create: `tests/test_kitchen_services.py` - scoring and list-generation behavior
- Create: `tests/test_routes_kitchen.py` - API behavior

V1 deliberately does not modify the existing `recipes` table. Favorite meals are stored separately so Kitchen Memory can work with named household meals before recipe import/template work is complete. Later, `favorite_meals.nutrition_template_id` can link to recipe or meal-template records.

---

### Task 1: Schema And Repository Foundation

**Files:**
- Modify: `app/database.py`
- Create: `app/repositories/kitchen.py`
- Create: `tests/test_kitchen_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/test_kitchen_repository.py`:

```python
from app.repositories.kitchen import KitchenRepository


def test_upsert_inventory_creates_item(db):
    repo = KitchenRepository(db)
    item = repo.upsert_inventory_item(
        user_id=1,
        display_name="Eggs",
        canonical_name="eggs",
        status="have",
        location="fridge",
        category="protein",
        notes=None,
    )
    assert item["display_name"] == "Eggs"
    assert item["canonical_name"] == "eggs"
    assert item["status"] == "have"
    assert item["location"] == "fridge"


def test_upsert_inventory_updates_existing_item(db):
    repo = KitchenRepository(db)
    first = repo.upsert_inventory_item(
        user_id=1,
        display_name="Spinach",
        canonical_name="spinach",
        status="have",
    )
    second = repo.upsert_inventory_item(
        user_id=1,
        display_name="Spinach",
        canonical_name="spinach",
        status="use_soon",
        location="fridge",
    )
    assert second["id"] == first["id"]
    assert second["status"] == "use_soon"
    assert second["location"] == "fridge"


def test_list_inventory_filters_by_status(db):
    repo = KitchenRepository(db)
    repo.upsert_inventory_item(user_id=1, display_name="Eggs", canonical_name="eggs", status="have")
    repo.upsert_inventory_item(user_id=1, display_name="Spinach", canonical_name="spinach", status="use_soon")
    results = repo.list_inventory(user_id=1, status="use_soon")
    assert [item["canonical_name"] for item in results] == ["spinach"]


def test_create_favorite_meal_with_ingredients(db):
    repo = KitchenRepository(db)
    meal = repo.create_favorite_meal(
        user_id=1,
        name="Egg Fried Rice",
        tags=["dinner", "low_effort"],
        prep_time_minutes=15,
        effort="low",
        favorite_score=4,
        ingredients=[
            {"display_name": "Eggs", "canonical_name": "eggs", "role": "required", "category": "protein"},
            {"display_name": "Rice", "canonical_name": "rice", "role": "required", "category": "grain"},
            {"display_name": "Spinach", "canonical_name": "spinach", "role": "optional", "category": "vegetable"},
        ],
    )
    assert meal["name"] == "Egg Fried Rice"
    assert meal["tags"] == ["dinner", "low_effort"]
    assert len(meal["ingredients"]) == 3


def test_mark_favorite_meal_made_updates_history(db):
    repo = KitchenRepository(db)
    meal = repo.create_favorite_meal(
        user_id=1,
        name="Chicken Rice Bowl",
        tags=[],
        ingredients=[],
    )
    updated = repo.mark_meal_made(user_id=1, meal_id=meal["id"], made_at="2026-05-25T12:00:00")
    assert updated["times_made"] == 1
    assert updated["last_made_at"] == "2026-05-25T12:00:00"


def test_upsert_shopping_list_item_merges_by_name(db):
    repo = KitchenRepository(db)
    first = repo.upsert_shopping_list_item(
        user_id=1,
        display_name="Tortillas",
        canonical_name="tortillas",
        source="manual",
        linked_meal_ids=[],
    )
    second = repo.upsert_shopping_list_item(
        user_id=1,
        display_name="Tortillas",
        canonical_name="tortillas",
        source="meal_plan",
        linked_meal_ids=[7],
    )
    assert second["id"] == first["id"]
    assert second["linked_meal_ids"] == [7]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_kitchen_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.repositories.kitchen'`.

- [ ] **Step 3: Add Kitchen Memory tables to `app/database.py`**

Inside `init_schema()` after the `recipes` table and before `weight_entries`, add:

```sql
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
```

- [ ] **Step 4: Create `app/repositories/kitchen.py`**

```python
import json
import sqlite3


class KitchenRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _inventory_row(self, row) -> dict | None:
        return dict(row) if row else None

    def _meal_row(self, row) -> dict | None:
        if not row:
            return None
        meal = dict(row)
        meal["tags"] = json.loads(meal["tags"])
        meal["ingredients"] = self.list_meal_ingredients(meal["id"])
        return meal

    def _shopping_row(self, row) -> dict | None:
        if not row:
            return None
        item = dict(row)
        item["checked"] = bool(item["checked"])
        item["linked_meal_ids"] = json.loads(item["linked_meal_ids"])
        return item

    def upsert_inventory_item(
        self,
        *,
        user_id: int,
        display_name: str,
        canonical_name: str,
        status: str,
        location: str | None = None,
        category: str | None = None,
        notes: str | None = None,
    ) -> dict:
        self.conn.execute(
            """INSERT INTO kitchen_inventory_items
               (user_id, canonical_name, display_name, status, location, category, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, canonical_name) DO UPDATE SET
                 display_name = excluded.display_name,
                 status = excluded.status,
                 location = excluded.location,
                 category = excluded.category,
                 notes = excluded.notes,
                 last_confirmed_at = datetime('now'),
                 updated_at = datetime('now')""",
            (user_id, canonical_name, display_name, status, location, category, notes),
        )
        self.conn.commit()
        return self.get_inventory_item(user_id=user_id, canonical_name=canonical_name)

    def get_inventory_item(self, *, user_id: int, canonical_name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM kitchen_inventory_items WHERE user_id = ? AND canonical_name = ?",
            (user_id, canonical_name),
        ).fetchone()
        return self._inventory_row(row)

    def list_inventory(
        self,
        *,
        user_id: int,
        status: str | None = None,
        location: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> list[dict]:
        clauses = ["user_id = ?"]
        values: list = [user_id]
        if status:
            clauses.append("status = ?")
            values.append(status)
        if location:
            clauses.append("location = ?")
            values.append(location)
        if category:
            clauses.append("category = ?")
            values.append(category)
        if query:
            clauses.append("LOWER(display_name) LIKE '%' || LOWER(?) || '%'")
            values.append(query)
        rows = self.conn.execute(
            f"""SELECT * FROM kitchen_inventory_items
                WHERE {' AND '.join(clauses)}
                ORDER BY status = 'use_soon' DESC, display_name ASC""",
            values,
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_inventory_item(self, *, user_id: int, item_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM kitchen_inventory_items WHERE user_id = ? AND id = ?",
            (user_id, item_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def create_favorite_meal(
        self,
        *,
        user_id: int,
        name: str,
        tags: list[str],
        ingredients: list[dict],
        prep_time_minutes: int | None = None,
        effort: str | None = None,
        favorite_score: int = 0,
        nutrition_template_id: int | None = None,
    ) -> dict:
        cur = self.conn.execute(
            """INSERT INTO favorite_meals
               (user_id, name, tags, prep_time_minutes, effort, favorite_score, nutrition_template_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, name, json.dumps(tags), prep_time_minutes, effort, favorite_score, nutrition_template_id),
        )
        meal_id = cur.lastrowid
        for ingredient in ingredients:
            self.conn.execute(
                """INSERT INTO favorite_meal_ingredients
                   (meal_id, canonical_name, display_name, role, category)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    meal_id,
                    ingredient["canonical_name"],
                    ingredient["display_name"],
                    ingredient["role"],
                    ingredient.get("category"),
                ),
            )
        self.conn.commit()
        return self.get_favorite_meal(user_id=user_id, meal_id=meal_id)

    def get_favorite_meal(self, *, user_id: int, meal_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM favorite_meals WHERE user_id = ? AND id = ?",
            (user_id, meal_id),
        ).fetchone()
        return self._meal_row(row)

    def list_favorite_meals(self, *, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM favorite_meals WHERE user_id = ? ORDER BY favorite_score DESC, name ASC",
            (user_id,),
        ).fetchall()
        return [self._meal_row(row) for row in rows]

    def list_meal_ingredients(self, meal_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM favorite_meal_ingredients WHERE meal_id = ? ORDER BY role, display_name",
            (meal_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_meal_made(self, *, user_id: int, meal_id: int, made_at: str) -> dict | None:
        self.conn.execute(
            """UPDATE favorite_meals
               SET last_made_at = ?, times_made = times_made + 1, updated_at = datetime('now')
               WHERE user_id = ? AND id = ?""",
            (made_at, user_id, meal_id),
        )
        self.conn.commit()
        return self.get_favorite_meal(user_id=user_id, meal_id=meal_id)

    def upsert_shopping_list_item(
        self,
        *,
        user_id: int,
        display_name: str,
        canonical_name: str,
        source: str,
        linked_meal_ids: list[int],
        notes: str | None = None,
    ) -> dict:
        self.conn.execute(
            """INSERT INTO shopping_list_items
               (user_id, canonical_name, display_name, source, linked_meal_ids, notes)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, canonical_name) DO UPDATE SET
                 display_name = excluded.display_name,
                 source = excluded.source,
                 linked_meal_ids = excluded.linked_meal_ids,
                 notes = excluded.notes,
                 checked = 0,
                 updated_at = datetime('now')""",
            (user_id, canonical_name, display_name, source, json.dumps(linked_meal_ids), notes),
        )
        self.conn.commit()
        return self.get_shopping_list_item(user_id=user_id, canonical_name=canonical_name)

    def get_shopping_list_item(self, *, user_id: int, canonical_name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM shopping_list_items WHERE user_id = ? AND canonical_name = ?",
            (user_id, canonical_name),
        ).fetchone()
        return self._shopping_row(row)

    def list_shopping_items(self, *, user_id: int, checked: bool | None = None) -> list[dict]:
        if checked is None:
            rows = self.conn.execute(
                "SELECT * FROM shopping_list_items WHERE user_id = ? ORDER BY checked ASC, display_name ASC",
                (user_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM shopping_list_items WHERE user_id = ? AND checked = ? ORDER BY display_name ASC",
                (user_id, int(checked)),
            ).fetchall()
        return [self._shopping_row(row) for row in rows]

    def set_shopping_item_checked(self, *, user_id: int, item_id: int, checked: bool) -> dict | None:
        self.conn.execute(
            """UPDATE shopping_list_items
               SET checked = ?, updated_at = datetime('now')
               WHERE user_id = ? AND id = ?""",
            (int(checked), user_id, item_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM shopping_list_items WHERE user_id = ? AND id = ?",
            (user_id, item_id),
        ).fetchone()
        return self._shopping_row(row)
```

- [ ] **Step 5: Run repository tests**

Run:

```bash
pytest tests/test_kitchen_repository.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/database.py app/repositories/kitchen.py tests/test_kitchen_repository.py
git commit -m "feat: add kitchen memory repository"
```

---

### Task 2: Service Layer For Canonicalization, Matching, And Shopping Lists

**Files:**
- Create: `app/services/kitchen.py`
- Create: `tests/test_kitchen_services.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_kitchen_services.py`:

```python
from app.services.kitchen import (
    canonicalize_ingredient_name,
    generate_shopping_items_for_meals,
    rank_favorite_meals,
)


def test_canonicalize_ingredient_name_trims_and_collapses_spaces():
    assert canonicalize_ingredient_name("  Frozen   Chicken  ") == "frozen chicken"


def test_rank_favorite_meals_prioritizes_use_soon_items():
    meals = [
        {
            "id": 1,
            "name": "Plain Eggs",
            "tags": [],
            "effort": "low",
            "favorite_score": 1,
            "last_made_at": None,
            "ingredients": [
                {"canonical_name": "eggs", "display_name": "Eggs", "role": "required"},
            ],
        },
        {
            "id": 2,
            "name": "Spinach Eggs",
            "tags": [],
            "effort": "low",
            "favorite_score": 1,
            "last_made_at": None,
            "ingredients": [
                {"canonical_name": "eggs", "display_name": "Eggs", "role": "required"},
                {"canonical_name": "spinach", "display_name": "Spinach", "role": "optional"},
            ],
        },
    ]
    inventory = [
        {"canonical_name": "eggs", "display_name": "Eggs", "status": "have"},
        {"canonical_name": "spinach", "display_name": "Spinach", "status": "use_soon"},
    ]
    results = rank_favorite_meals(meals=meals, inventory=inventory, request_filters={})
    assert results[0]["meal_id"] == 2
    assert results[0]["use_soon_ingredients"] == ["Spinach"]


def test_rank_favorite_meals_penalizes_missing_required_items():
    meals = [
        {
            "id": 1,
            "name": "Turkey Tacos",
            "tags": [],
            "effort": "low",
            "favorite_score": 5,
            "last_made_at": None,
            "ingredients": [
                {"canonical_name": "ground turkey", "display_name": "Ground Turkey", "role": "required"},
                {"canonical_name": "tortillas", "display_name": "Tortillas", "role": "required"},
            ],
        }
    ]
    inventory = [{"canonical_name": "tortillas", "display_name": "Tortillas", "status": "have"}]
    results = rank_favorite_meals(meals=meals, inventory=inventory, request_filters={})
    assert results[0]["missing_required_ingredients"] == ["Ground Turkey"]
    assert results[0]["score"] < 0


def test_rank_favorite_meals_treats_staples_as_available():
    meals = [
        {
            "id": 1,
            "name": "Rice Bowl",
            "tags": [],
            "effort": "low",
            "favorite_score": 0,
            "last_made_at": None,
            "ingredients": [
                {"canonical_name": "rice", "display_name": "Rice", "role": "required"},
            ],
        }
    ]
    inventory = [{"canonical_name": "rice", "display_name": "Rice", "status": "staple"}]
    results = rank_favorite_meals(meals=meals, inventory=inventory, request_filters={})
    assert results[0]["available_required_ingredients"] == ["Rice"]
    assert results[0]["missing_required_ingredients"] == []


def test_generate_shopping_items_skips_have_and_staples():
    meals = [
        {
            "id": 7,
            "name": "Turkey Tacos",
            "ingredients": [
                {"canonical_name": "ground turkey", "display_name": "Ground Turkey", "role": "required"},
                {"canonical_name": "tortillas", "display_name": "Tortillas", "role": "required"},
                {"canonical_name": "salt", "display_name": "Salt", "role": "required"},
            ],
        }
    ]
    inventory = [
        {"canonical_name": "tortillas", "display_name": "Tortillas", "status": "have"},
        {"canonical_name": "salt", "display_name": "Salt", "status": "staple"},
    ]
    items = generate_shopping_items_for_meals(meals=meals, inventory=inventory)
    assert items == [
        {
            "canonical_name": "ground turkey",
            "display_name": "Ground Turkey",
            "source": "meal_plan",
            "linked_meal_ids": [7],
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_kitchen_services.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.kitchen'`.

- [ ] **Step 3: Create `app/services/kitchen.py`**

```python
import re
from datetime import datetime, timezone


AVAILABLE_STATUSES = {"have", "use_soon", "staple"}


def canonicalize_ingredient_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _inventory_by_name(inventory: list[dict]) -> dict[str, dict]:
    return {item["canonical_name"]: item for item in inventory}


def _days_since(iso_value: str | None) -> int | None:
    if not iso_value:
        return None
    raw = iso_value.replace("Z", "+00:00")
    try:
        then = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0, (now - then).days)


def rank_favorite_meals(
    *,
    meals: list[dict],
    inventory: list[dict],
    request_filters: dict | None = None,
) -> list[dict]:
    request_filters = request_filters or {}
    inventory_map = _inventory_by_name(inventory)
    results = []

    for meal in meals:
        score = int(meal.get("favorite_score") or 0)
        breakdown = [{"reason": "favorite_score", "points": score}]
        available_required = []
        missing_required = []
        available_optional = []
        use_soon = []
        maybe = []
        out = []

        for ingredient in meal.get("ingredients", []):
            canonical = ingredient["canonical_name"]
            display = ingredient["display_name"]
            role = ingredient["role"]
            inv = inventory_map.get(canonical)
            status = inv["status"] if inv else "missing"

            if status == "use_soon":
                score += 8
                breakdown.append({"reason": f"use_soon:{canonical}", "points": 8})
                use_soon.append(display)

            if status in AVAILABLE_STATUSES:
                if role == "required":
                    score += 5
                    breakdown.append({"reason": f"required_available:{canonical}", "points": 5})
                    available_required.append(display)
                else:
                    score += 2
                    breakdown.append({"reason": f"optional_available:{canonical}", "points": 2})
                    available_optional.append(display)
            elif status == "maybe":
                score -= 2
                breakdown.append({"reason": f"maybe:{canonical}", "points": -2})
                maybe.append(display)
            elif status == "out":
                score -= 7 if role == "required" else 1
                breakdown.append({"reason": f"out:{canonical}", "points": -7 if role == "required" else -1})
                out.append(display)
                if role == "required":
                    missing_required.append(display)
            elif role == "required":
                score -= 7
                breakdown.append({"reason": f"missing_required:{canonical}", "points": -7})
                missing_required.append(display)

        if request_filters.get("effort") and meal.get("effort") != request_filters["effort"]:
            score -= 3
            breakdown.append({"reason": "effort_mismatch", "points": -3})

        required_tag = request_filters.get("tag")
        if required_tag and required_tag not in meal.get("tags", []):
            score -= 4
            breakdown.append({"reason": f"missing_tag:{required_tag}", "points": -4})

        days = _days_since(meal.get("last_made_at"))
        if days is not None and days < 3:
            score -= 4
            breakdown.append({"reason": "recently_made", "points": -4})

        results.append({
            "meal_id": meal["id"],
            "meal_name": meal["name"],
            "score": score,
            "available_required_ingredients": available_required,
            "missing_required_ingredients": missing_required,
            "available_optional_ingredients": available_optional,
            "use_soon_ingredients": use_soon,
            "maybe_ingredients": maybe,
            "out_ingredients": out,
            "score_breakdown": breakdown,
        })

    return sorted(results, key=lambda result: result["score"], reverse=True)


def generate_shopping_items_for_meals(*, meals: list[dict], inventory: list[dict]) -> list[dict]:
    inventory_map = _inventory_by_name(inventory)
    pending: dict[str, dict] = {}

    for meal in meals:
        for ingredient in meal.get("ingredients", []):
            if ingredient["role"] != "required":
                continue
            inv = inventory_map.get(ingredient["canonical_name"])
            if inv and inv["status"] in AVAILABLE_STATUSES:
                continue

            canonical = ingredient["canonical_name"]
            if canonical not in pending:
                pending[canonical] = {
                    "canonical_name": canonical,
                    "display_name": ingredient["display_name"],
                    "source": "meal_plan",
                    "linked_meal_ids": [],
                }
            if meal["id"] not in pending[canonical]["linked_meal_ids"]:
                pending[canonical]["linked_meal_ids"].append(meal["id"])

    return sorted(pending.values(), key=lambda item: item["display_name"].lower())
```

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/test_kitchen_services.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/kitchen.py tests/test_kitchen_services.py
git commit -m "feat: add kitchen memory matching services"
```

---

### Task 3: Pydantic Models

**Files:**
- Create: `app/models/kitchen.py`

- [ ] **Step 1: Create `app/models/kitchen.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


InventoryStatus = Literal["have", "use_soon", "maybe", "out", "staple"]
KitchenLocation = Literal["fridge", "freezer", "pantry", "other"]
IngredientRole = Literal["required", "optional", "substitution"]
EffortLevel = Literal["low", "medium", "high"]
ShoppingSource = Literal["manual", "meal_plan", "inventory", "staple_refresh", "suggestion"]


class InventoryItemCreate(BaseModel):
    name: str
    status: InventoryStatus = "have"
    location: KitchenLocation | None = None
    category: str | None = None
    notes: str | None = None


class InventoryItem(BaseModel):
    id: int
    user_id: int
    canonical_name: str
    display_name: str
    status: InventoryStatus
    location: KitchenLocation | None = None
    category: str | None = None
    notes: str | None = None
    last_confirmed_at: datetime
    created_at: datetime
    updated_at: datetime


class FavoriteMealIngredientInput(BaseModel):
    name: str
    role: IngredientRole = "required"
    category: str | None = None


class FavoriteMealIngredient(BaseModel):
    id: int | None = None
    meal_id: int | None = None
    canonical_name: str
    display_name: str
    role: IngredientRole
    category: str | None = None


class FavoriteMealCreate(BaseModel):
    name: str
    tags: list[str] = Field(default_factory=list)
    prep_time_minutes: int | None = None
    effort: EffortLevel | None = None
    favorite_score: int = 0
    nutrition_template_id: int | None = None
    ingredients: list[FavoriteMealIngredientInput] = Field(default_factory=list)


class FavoriteMeal(BaseModel):
    id: int
    user_id: int
    name: str
    tags: list[str]
    prep_time_minutes: int | None = None
    effort: EffortLevel | None = None
    favorite_score: int
    nutrition_template_id: int | None = None
    last_made_at: datetime | None = None
    times_made: int
    ingredients: list[FavoriteMealIngredient]
    created_at: datetime
    updated_at: datetime


class MealMatch(BaseModel):
    meal_id: int
    meal_name: str
    score: int
    available_required_ingredients: list[str]
    missing_required_ingredients: list[str]
    available_optional_ingredients: list[str]
    use_soon_ingredients: list[str]
    maybe_ingredients: list[str]
    out_ingredients: list[str]
    score_breakdown: list[dict]


class MealMatchRequest(BaseModel):
    effort: EffortLevel | None = None
    tag: str | None = None


class ShoppingListItemCreate(BaseModel):
    name: str
    source: ShoppingSource = "manual"
    linked_meal_ids: list[int] = Field(default_factory=list)
    notes: str | None = None


class ShoppingListItem(BaseModel):
    id: int
    user_id: int
    canonical_name: str
    display_name: str
    checked: bool
    source: ShoppingSource
    linked_meal_ids: list[int]
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: Run import check**

Run:

```bash
python -c "from app.models.kitchen import InventoryItem, FavoriteMeal, MealMatch, ShoppingListItem"
```

Expected: exits with status 0.

- [ ] **Step 3: Commit**

```bash
git add app/models/kitchen.py
git commit -m "feat: add kitchen memory API models"
```

---

### Task 4: Kitchen API Routes

**Files:**
- Create: `app/routes/kitchen.py`
- Modify: `app/main.py`
- Create: `tests/test_routes_kitchen.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/test_routes_kitchen.py`:

```python
def test_create_and_list_inventory_item(client):
    r = client.post("/kitchen/inventory", json={
        "name": "Eggs",
        "status": "have",
        "location": "fridge",
        "category": "protein",
    })
    assert r.status_code == 201
    assert r.json()["canonical_name"] == "eggs"

    listed = client.get("/kitchen/inventory?status=have")
    assert listed.status_code == 200
    assert listed.json()[0]["display_name"] == "Eggs"


def test_create_favorite_meal_and_get_matches(client):
    client.post("/kitchen/inventory", json={"name": "Eggs", "status": "have"})
    client.post("/kitchen/inventory", json={"name": "Spinach", "status": "use_soon"})
    r = client.post("/kitchen/meals", json={
        "name": "Spinach Eggs",
        "tags": ["breakfast", "high_protein"],
        "effort": "low",
        "favorite_score": 3,
        "ingredients": [
            {"name": "Eggs", "role": "required"},
            {"name": "Spinach", "role": "optional"},
        ],
    })
    assert r.status_code == 201

    matches = client.post("/kitchen/matches", json={"effort": "low"})
    assert matches.status_code == 200
    assert matches.json()[0]["meal_name"] == "Spinach Eggs"
    assert matches.json()[0]["use_soon_ingredients"] == ["Spinach"]


def test_generate_shopping_list_from_meals(client):
    client.post("/kitchen/inventory", json={"name": "Tortillas", "status": "have"})
    meal = client.post("/kitchen/meals", json={
        "name": "Turkey Tacos",
        "ingredients": [
            {"name": "Ground Turkey", "role": "required"},
            {"name": "Tortillas", "role": "required"},
        ],
    }).json()
    r = client.post("/kitchen/shopping-list/generate", json={"meal_ids": [meal["id"]]})
    assert r.status_code == 200
    assert [item["display_name"] for item in r.json()] == ["Ground Turkey"]


def test_mark_meal_made(client):
    meal = client.post("/kitchen/meals", json={
        "name": "Chicken Rice Bowl",
        "ingredients": [],
    }).json()
    r = client.post(f"/kitchen/meals/{meal['id']}/made")
    assert r.status_code == 200
    assert r.json()["times_made"] == 1
    assert r.json()["last_made_at"] is not None


def test_check_shopping_item(client):
    item = client.post("/kitchen/shopping-list", json={"name": "Greek Yogurt"}).json()
    r = client.patch(f"/kitchen/shopping-list/{item['id']}", json={"checked": True})
    assert r.status_code == 200
    assert r.json()["checked"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_routes_kitchen.py -v
```

Expected: `404 Not Found` for `/kitchen/*` endpoints.

- [ ] **Step 3: Create `app/routes/kitchen.py`**

```python
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.models.kitchen import (
    FavoriteMeal,
    FavoriteMealCreate,
    InventoryItem,
    InventoryItemCreate,
    MealMatch,
    MealMatchRequest,
    ShoppingListItem,
    ShoppingListItemCreate,
)
from app.repositories.kitchen import KitchenRepository
from app.services.kitchen import (
    canonicalize_ingredient_name,
    generate_shopping_items_for_meals,
    rank_favorite_meals,
)


router = APIRouter(prefix="/kitchen", tags=["kitchen"])


class ShoppingGenerateRequest(BaseModel):
    meal_ids: list[int]


class ShoppingItemPatch(BaseModel):
    checked: bool


def _repo(request: Request) -> KitchenRepository:
    return KitchenRepository(request.app.state.db)


def _ingredient_payload(item) -> dict:
    canonical = canonicalize_ingredient_name(item.name)
    return {
        "display_name": item.name.strip(),
        "canonical_name": canonical,
        "role": item.role,
        "category": item.category,
    }


@router.post("/inventory", status_code=201, response_model=InventoryItem, summary="Create or update kitchen inventory item")
def upsert_inventory_item(request: Request, body: InventoryItemCreate):
    canonical = canonicalize_ingredient_name(body.name)
    return _repo(request).upsert_inventory_item(
        user_id=settings.default_user_id,
        display_name=body.name.strip(),
        canonical_name=canonical,
        status=body.status,
        location=body.location,
        category=body.category,
        notes=body.notes,
    )


@router.get("/inventory", response_model=list[InventoryItem], summary="List kitchen inventory")
def list_inventory(
    request: Request,
    status: str | None = None,
    location: str | None = None,
    category: str | None = None,
    q: str | None = None,
):
    return _repo(request).list_inventory(
        user_id=settings.default_user_id,
        status=status,
        location=location,
        category=category,
        query=q,
    )


@router.delete("/inventory/{item_id}", status_code=204, summary="Delete kitchen inventory item")
def delete_inventory_item(request: Request, item_id: int):
    if not _repo(request).delete_inventory_item(user_id=settings.default_user_id, item_id=item_id):
        raise HTTPException(404, "Inventory item not found")


@router.post("/meals", status_code=201, response_model=FavoriteMeal, summary="Create favorite meal")
def create_favorite_meal(request: Request, body: FavoriteMealCreate):
    ingredients = [_ingredient_payload(item) for item in body.ingredients]
    return _repo(request).create_favorite_meal(
        user_id=settings.default_user_id,
        name=body.name,
        tags=body.tags,
        prep_time_minutes=body.prep_time_minutes,
        effort=body.effort,
        favorite_score=body.favorite_score,
        nutrition_template_id=body.nutrition_template_id,
        ingredients=ingredients,
    )


@router.get("/meals", response_model=list[FavoriteMeal], summary="List favorite meals")
def list_favorite_meals(request: Request):
    return _repo(request).list_favorite_meals(user_id=settings.default_user_id)


@router.post("/meals/{meal_id}/made", response_model=FavoriteMeal, summary="Mark favorite meal made")
def mark_meal_made(request: Request, meal_id: int):
    made_at = datetime.now(timezone.utc).isoformat()
    meal = _repo(request).mark_meal_made(
        user_id=settings.default_user_id,
        meal_id=meal_id,
        made_at=made_at,
    )
    if not meal:
        raise HTTPException(404, "Favorite meal not found")
    return meal


@router.post("/matches", response_model=list[MealMatch], summary="Rank meals from current kitchen memory")
def rank_meals(request: Request, body: MealMatchRequest):
    repo = _repo(request)
    meals = repo.list_favorite_meals(user_id=settings.default_user_id)
    inventory = repo.list_inventory(user_id=settings.default_user_id)
    return rank_favorite_meals(
        meals=meals,
        inventory=inventory,
        request_filters=body.model_dump(exclude_none=True),
    )


@router.post("/shopping-list", status_code=201, response_model=ShoppingListItem, summary="Add shopping list item")
def add_shopping_item(request: Request, body: ShoppingListItemCreate):
    canonical = canonicalize_ingredient_name(body.name)
    return _repo(request).upsert_shopping_list_item(
        user_id=settings.default_user_id,
        display_name=body.name.strip(),
        canonical_name=canonical,
        source=body.source,
        linked_meal_ids=body.linked_meal_ids,
        notes=body.notes,
    )


@router.get("/shopping-list", response_model=list[ShoppingListItem], summary="List shopping list items")
def list_shopping_items(request: Request, checked: bool | None = None):
    return _repo(request).list_shopping_items(
        user_id=settings.default_user_id,
        checked=checked,
    )


@router.post("/shopping-list/generate", response_model=list[ShoppingListItem], summary="Generate shopping list items from selected meals")
def generate_shopping_list(request: Request, body: ShoppingGenerateRequest):
    repo = _repo(request)
    meals = []
    for meal_id in body.meal_ids:
        meal = repo.get_favorite_meal(user_id=settings.default_user_id, meal_id=meal_id)
        if not meal:
            raise HTTPException(404, f"Favorite meal {meal_id} not found")
        meals.append(meal)

    inventory = repo.list_inventory(user_id=settings.default_user_id)
    generated = generate_shopping_items_for_meals(meals=meals, inventory=inventory)
    return [
        repo.upsert_shopping_list_item(
            user_id=settings.default_user_id,
            display_name=item["display_name"],
            canonical_name=item["canonical_name"],
            source=item["source"],
            linked_meal_ids=item["linked_meal_ids"],
        )
        for item in generated
    ]


@router.patch("/shopping-list/{item_id}", response_model=ShoppingListItem, summary="Check or uncheck shopping list item")
def patch_shopping_item(request: Request, item_id: int, body: ShoppingItemPatch):
    item = _repo(request).set_shopping_item_checked(
        user_id=settings.default_user_id,
        item_id=item_id,
        checked=body.checked,
    )
    if not item:
        raise HTTPException(404, "Shopping list item not found")
    return item
```

- [ ] **Step 4: Include kitchen router in `app/main.py`**

Add import near the other route imports:

```python
from app.routes.kitchen import router as kitchen_router
```

Add include after `recipes_router`:

```python
app.include_router(kitchen_router, dependencies=_auth)
```

- [ ] **Step 5: Run route tests**

Run:

```bash
pytest tests/test_routes_kitchen.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run kitchen test suite**

Run:

```bash
pytest tests/test_kitchen_repository.py tests/test_kitchen_services.py tests/test_routes_kitchen.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/routes/kitchen.py app/main.py tests/test_routes_kitchen.py
git commit -m "feat: add kitchen memory API routes"
```

---

### Task 5: API Documentation And Smoke Test

**Files:**
- Modify: `README.md`
- Modify: `docs/live-smoke-test.md`

- [ ] **Step 1: Add Kitchen Memory endpoint summary to `README.md`**

In the top endpoint list, add:

```markdown
- `POST /kitchen/inventory` - remember what you have, use soon, maybe have, are out of, or treat as a staple
- `POST /kitchen/matches` - rank favorite meals from current kitchen inventory
- `POST /kitchen/shopping-list/generate` - generate grocery items from selected favorite meals
```

- [ ] **Step 2: Add a live smoke-test section to `docs/live-smoke-test.md`**

Append:

````markdown
## Kitchen Memory - inventory, matches, shopping list

Create inventory:

```bash
curl -s -X POST https://nutrition.example.com/kitchen/inventory \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Eggs","status":"have","location":"fridge"}'
```

Create a favorite meal:

```bash
curl -s -X POST https://nutrition.example.com/kitchen/meals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Spinach Eggs","tags":["breakfast","high_protein"],"effort":"low","ingredients":[{"name":"Eggs","role":"required"},{"name":"Spinach","role":"optional"}]}'
```

Rank meals:

```bash
curl -s -X POST https://nutrition.example.com/kitchen/matches \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"effort":"low"}'
```

Expected: returns a ranked list with `meal_name`, `score`, ingredient groups, and score breakdown.
````

- [ ] **Step 3: Run full tests**

Run:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/live-smoke-test.md
git commit -m "docs: document kitchen memory endpoints"
```

---

## Release Criteria

- Inventory supports `have`, `use_soon`, `maybe`, `out`, and `staple`
- Favorite meals can be stored with required and optional ingredients
- `POST /kitchen/matches` returns deterministic, explainable rankings
- `POST /kitchen/shopping-list/generate` adds only missing required ingredients
- Shopping list items remain editable and checkable
- No endpoint requires exact ingredient quantities
- All new repository, service, and route tests pass
- Existing test suite still passes

---

## Explicit Deferrals

- Natural-language parsing
- Mobile/web UI
- Receipt import
- Barcode inventory updates
- Grocery delivery integration
- Exact quantity decrementing
- Expiration prediction
- Links to future meal-template tables beyond nullable `nutrition_template_id`
