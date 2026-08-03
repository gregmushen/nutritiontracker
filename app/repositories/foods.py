import json
import sqlite3
from collections.abc import Sequence

from app.models.food import NUTRIENT_FIELDS

DATASET_SPECIFIC_USDA_SOURCES = frozenset(
    {"usda_fndds", "usda_foundation", "usda_sr_legacy", "usda_branded"}
)


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

    def create(
        self, *, source: str, name: str, owner_user_id: int | None = None, **kwargs
    ) -> int:
        other_fields = [
            "source_code", "brand", "barcode", "image_url", "serving_quantity",
            "serving_unit", "serving_size_text", "ingredients_text",
            "allergens_tags", "dietary_tags", "categories_tags", "labels_tags",
            "countries_tags", "nutriscore_grade", "nova_group", "product_quantity",
            "product_quantity_unit", "base_quantity", "base_unit", "density_g_per_ml",
        ]
        all_fields = other_fields + list(NUTRIENT_FIELDS)
        fields = ["source", "name", "owner_user_id"]
        values = [source, name, owner_user_id]
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
        owner_user_id = kwargs.pop("owner_user_id", None)
        other_fields = [
            "source_code", "brand", "barcode", "image_url", "serving_quantity",
            "serving_unit", "serving_size_text", "ingredients_text",
            "allergens_tags", "dietary_tags", "categories_tags", "labels_tags",
            "countries_tags", "nutriscore_grade", "nova_group", "product_quantity",
            "product_quantity_unit", "base_quantity", "base_unit", "density_g_per_ml",
        ]
        all_fields = other_fields + list(NUTRIENT_FIELDS)
        fields = ["source", "name", "owner_user_id"]
        values = [source, name, owner_user_id]
        for f in all_fields:
            if f in kwargs:
                fields.append(f)
                values.append(json.dumps(kwargs[f]) if f.endswith("_tags") else kwargs[f])
        placeholders = ", ".join(["?"] * len(values))
        cols = ", ".join(fields)
        source_code = kwargs.get("source_code")
        if (
            owner_user_id is None
            and source in DATASET_SPECIFIC_USDA_SOURCES
            and source_code is not None
        ):
            legacy = self.conn.execute(
                """SELECT id FROM foods
                   WHERE source = 'food_data_central' AND source_code = ?
                     AND owner_user_id IS NULL""",
                (source_code,),
            ).fetchone()
            current = self.conn.execute(
                """SELECT id FROM foods
                   WHERE source = ? AND source_code = ? AND owner_user_id IS NULL""",
                (source, source_code),
            ).fetchone()
            if legacy is not None and current is None:
                assignments = ", ".join(f"{field} = ?" for field in fields)
                self.conn.execute(
                    f"UPDATE foods SET {assignments}, updated_at = datetime('now') "
                    "WHERE id = ?",
                    (*values, legacy["id"]),
                )
                return legacy["id"]
        conflict_clause = ""
        if "source_code" in fields:
            updates = ", ".join(
                f"{field} = excluded.{field}"
                for field in fields
                if field not in ("source", "source_code", "owner_user_id")
            )
            if owner_user_id is None:
                conflict_clause = (
                    " ON CONFLICT(source, source_code) "
                    "WHERE source_code IS NOT NULL AND owner_user_id IS NULL"
                    f" DO UPDATE SET {updates}, updated_at = datetime('now')"
                )
            else:
                conflict_clause = (
                    " ON CONFLICT(owner_user_id, source, source_code) "
                    "WHERE source_code IS NOT NULL AND owner_user_id IS NOT NULL"
                    f" DO UPDATE SET {updates}, updated_at = datetime('now')"
                )
        cur = self.conn.execute(
            f"INSERT INTO foods ({cols}) VALUES ({placeholders})"
            f"{conflict_clause} RETURNING id",
            values,
        )
        return cur.fetchone()[0]

    def get(self, food_id: int, *, user_id: int | None = None) -> dict | None:
        query = "SELECT * FROM foods WHERE id = ?"
        values: list[int] = [food_id]
        if user_id is not None:
            query += " AND (owner_user_id IS NULL OR owner_user_id = ?)"
            values.append(user_id)
        row = self.conn.execute(query, values).fetchone()
        return self._deserialize(row)

    def get_by_barcode(self, barcode: str, *, user_id: int | None = None) -> dict | None:
        query = "SELECT * FROM foods WHERE barcode = ?"
        values: list[int | str] = [barcode]
        if user_id is not None:
            query += " AND (owner_user_id IS NULL OR owner_user_id = ?)"
            values.append(user_id)
        row = self.conn.execute(query, values).fetchone()
        return self._deserialize(row)

    @staticmethod
    def build_fts_query(query: str) -> str:
        """Turn user input into an FTS5 prefix query, or "" if it has no terms.

        Each term is wrapped in an FTS5 string literal so that punctuation a
        user can reasonably type is matched literally instead of being parsed
        as query syntax. Unquoted, "Ben & Jerry's" and "AC/DC" and "Milk 2%"
        all raised `fts5: syntax error` and failed the request, "Yoghurt-Greek"
        raised `no such column: greek`, and a bare `AND` was read as an
        operator.

        NUL is stripped rather than quoted: SQLite's FTS5 parser is written
        against NUL-terminated C strings, so an embedded NUL truncates the
        expression mid-literal and the unclosed quote raises
        `fts5: unterminated string`.
        """
        cleaned = query.replace("\x00", "")
        terms = [term.replace('"', '""') for term in cleaned.strip().split()]
        return " ".join(f'"{term}"*' for term in terms)

    def search(
        self, query: str, *, sources: Sequence[str] | None = None,
        user_id: int | None = None, limit: int = 20, offset: int = 0,
        quality_weight: float = 0.0, max_quality_tier: int = 5,
    ) -> list[dict]:
        """Full-text matches ordered by relevance, each carrying its bm25 score.

        Ordering here is text relevance only. Callers that care about source
        quality re-rank the rows using the `relevance` score, which is why it
        is returned rather than discarded.
        """
        fts_query = self.build_fts_query(query)
        if not fts_query:
            # An empty MATCH is itself a syntax error.
            return []
        filters = ""
        filter_values: list[object] = []
        if sources:
            placeholders = ", ".join(["?"] * len(sources))
            filters += f" AND f.source IN ({placeholders})"
            filter_values.extend(sources)
        if user_id is not None:
            filters += " AND (f.owner_user_id IS NULL OR f.owner_user_id = ?)"
            filter_values.append(user_id)
        known_nutrients = " + ".join(
            f"(f.{field} IS NOT NULL)" for field in NUTRIENT_FIELDS
        )
        rows = self.conn.execute(
            """
            WITH matched AS (
                SELECT f.*, bm25(foods_fts) AS relevance,
                       MIN(s.tier, ?) AS ranking_tier,
                       """ + known_nutrients + """ AS known_nutrients,
                       lower(trim(f.name)) AS normalized_name
                FROM foods_fts fts
                JOIN foods f ON f.id = fts.rowid
                JOIN food_sources s ON s.code = f.source
                WHERE foods_fts MATCH ?""" + filters + """
            ),
            barcode_ranked AS (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY CASE
                               WHEN barcode IS NULL OR barcode = ''
                               THEN 'id:' || id
                               ELSE 'barcode:' || barcode
                           END
                           ORDER BY ranking_tier, known_nutrients DESC, id
                       ) AS barcode_rank
                FROM matched
            ),
            name_ranked AS (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY normalized_name
                           ORDER BY ranking_tier, known_nutrients DESC, id
                       ) AS name_rank
                FROM barcode_ranked
                WHERE barcode_rank = 1
            )
            SELECT *
            FROM name_ranked
            WHERE name_rank = 1
            ORDER BY relevance + ? * ranking_tier, known_nutrients DESC, id
            LIMIT ? OFFSET ?
            """,
            (
                max_quality_tier,
                fts_query,
                *filter_values,
                quality_weight,
                limit,
                offset,
            ),
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

    def list_sources(self) -> list[dict]:
        """Registered data sources with how many foods each contributes."""
        rows = self.conn.execute("""
            SELECT s.code, s.label, s.publisher, s.tier, s.license, s.url,
                   s.citation, s.dataset_version,
                   (SELECT COUNT(*) FROM foods f WHERE f.source = s.code) AS food_count
            FROM food_sources s
            ORDER BY s.tier, s.code
        """).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _deserialize(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        food = dict(row)
        for field in (
            "ranking_tier",
            "known_nutrients",
            "normalized_name",
            "barcode_rank",
            "name_rank",
        ):
            food.pop(field, None)
        for field in ("allergens_tags", "dietary_tags", "categories_tags", "labels_tags", "countries_tags"):
            food[field] = json.loads(food[field])
        return food
