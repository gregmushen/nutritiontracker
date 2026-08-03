import json
import sqlite3

from app.models.food import NUTRIENT_FIELDS


class FoodRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure_fts(self):
        self.conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
                name, brand, content='foods', content_rowid='id',
                tokenize='porter unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS foods_ai AFTER INSERT ON foods BEGIN
                INSERT INTO foods_fts(rowid, name, brand)
                VALUES (new.id, new.name, new.brand);
            END;

            CREATE TRIGGER IF NOT EXISTS foods_ad AFTER DELETE ON foods BEGIN
                INSERT INTO foods_fts(foods_fts, rowid, name, brand)
                VALUES ('delete', old.id, old.name, old.brand);
            END;

            CREATE TRIGGER IF NOT EXISTS foods_au AFTER UPDATE ON foods BEGIN
                INSERT INTO foods_fts(foods_fts, rowid, name, brand)
                VALUES ('delete', old.id, old.name, old.brand);
                INSERT INTO foods_fts(rowid, name, brand)
                VALUES (new.id, new.name, new.brand);
            END;
        """)

    def create(self, *, source: str, name: str, **kwargs) -> int:
        other_fields = [
            "source_code", "brand", "barcode", "image_url", "serving_quantity",
            "serving_unit", "serving_size_text", "ingredients_text",
            "allergens_tags", "dietary_tags", "categories_tags", "labels_tags",
            "countries_tags", "nutriscore_grade", "nova_group", "product_quantity",
            "product_quantity_unit", "base_quantity", "base_unit", "density_g_per_ml",
        ]
        all_fields = other_fields + list(NUTRIENT_FIELDS)
        fields = ["source", "name"]
        values = [source, name]
        for f in all_fields:
            if f in kwargs:
                fields.append(f)
                values.append(json.dumps(kwargs[f]) if f.endswith("_tags") else kwargs[f])
        placeholders = ", ".join(["?"] * len(values))
        cols = ", ".join(fields)
        cur = self.conn.execute(
            f"INSERT INTO foods ({cols}) VALUES ({placeholders})", values
        )
        self.conn.commit()
        return cur.lastrowid

    def create_no_commit(self, **kwargs) -> int:
        """Same as create() but without committing — caller manages transactions for bulk imports."""
        source = kwargs.pop("source")
        name = kwargs.pop("name")
        other_fields = [
            "source_code", "brand", "barcode", "image_url", "serving_quantity",
            "serving_unit", "serving_size_text", "ingredients_text",
            "allergens_tags", "dietary_tags", "categories_tags", "labels_tags",
            "countries_tags", "nutriscore_grade", "nova_group", "product_quantity",
            "product_quantity_unit", "base_quantity", "base_unit", "density_g_per_ml",
        ]
        all_fields = other_fields + list(NUTRIENT_FIELDS)
        fields = ["source", "name"]
        values = [source, name]
        for f in all_fields:
            if f in kwargs:
                fields.append(f)
                values.append(json.dumps(kwargs[f]) if f.endswith("_tags") else kwargs[f])
        placeholders = ", ".join(["?"] * len(values))
        cols = ", ".join(fields)
        conflict_clause = ""
        if "source_code" in fields:
            updates = ", ".join(
                f"{field} = excluded.{field}"
                for field in fields
                if field not in ("source", "source_code")
            )
            conflict_clause = (
                " ON CONFLICT(source, source_code) WHERE source_code IS NOT NULL"
                f" DO UPDATE SET {updates}, updated_at = datetime('now')"
            )
        cur = self.conn.execute(
            f"INSERT INTO foods ({cols}) VALUES ({placeholders})"
            f"{conflict_clause} RETURNING id",
            values,
        )
        return cur.fetchone()[0]

    def get(self, food_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
        return self._deserialize(row)

    def get_by_barcode(self, barcode: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM foods WHERE barcode = ?", (barcode,)
        ).fetchone()
        return self._deserialize(row)

    def search(
        self, query: str, *, source: str | None = None, limit: int = 20, offset: int = 0
    ) -> list[dict]:
        fts_query = " ".join(f"{term}*" for term in query.strip().split())
        if source and source != "all":
            rows = self.conn.execute(
                """SELECT f.* FROM foods_fts fts
                   JOIN foods f ON f.id = fts.rowid
                   WHERE foods_fts MATCH ? AND f.source = ?
                   ORDER BY rank
                   LIMIT ? OFFSET ?""",
                (fts_query, source, limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT f.* FROM foods_fts fts
                   JOIN foods f ON f.id = fts.rowid
                   WHERE foods_fts MATCH ?
                   ORDER BY rank
                   LIMIT ? OFFSET ?""",
                (fts_query, limit, offset),
            ).fetchall()
        return [self._deserialize(r) for r in rows]

    def update(self, food_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        for field in (
            "allergens_tags", "dietary_tags", "categories_tags", "labels_tags",
            "countries_tags",
        ):
            if field in kwargs and isinstance(kwargs[field], list):
                kwargs[field] = json.dumps(kwargs[field])
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [food_id]
        self.conn.execute(
            f"UPDATE foods SET {sets}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        self.conn.commit()
        return True

    def delete(self, food_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
        self.conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _deserialize(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        food = dict(row)
        for field in ("allergens_tags", "dietary_tags", "categories_tags", "labels_tags", "countries_tags"):
            food[field] = json.loads(food[field])
        return food
