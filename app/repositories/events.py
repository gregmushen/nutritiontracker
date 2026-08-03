from __future__ import annotations

import sqlite3


class EventTypeRepository:
    """User-defined categories of event. Nothing here is seeded."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, user_id: int, name: str, unit: str | None,
               notes: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO event_types (user_id, name, unit, notes) VALUES (?, ?, ?, ?)",
            (user_id, name, unit, notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def get(self, type_id: int, *, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM event_types WHERE id = ? AND user_id = ?",
            (type_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def get_by_name(self, name: str, *, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM event_types WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        return dict(row) if row else None

    def list(self, *, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM event_types WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update(self, type_id: int, *, user_id: int, **updates) -> None:
        allowed = {"name", "unit", "notes"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE event_types SET {assignments}, updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (*fields.values(), type_id, user_id),
        )
        self.conn.commit()

    def count_events(self, type_id: int, *, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE event_type_id = ? AND user_id = ?",
            (type_id, user_id),
        ).fetchone()
        return row["n"]

    def delete(self, type_id: int, *, user_id: int, cascade: bool = False) -> None:
        if cascade:
            self.conn.execute(
                "DELETE FROM events WHERE event_type_id = ? AND user_id = ?",
                (type_id, user_id),
            )
        self.conn.execute(
            "DELETE FROM event_types WHERE id = ? AND user_id = ?",
            (type_id, user_id),
        )
        self.conn.commit()


class EventRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    _SELECT = """
        SELECT e.*, t.name AS event_type_name
        FROM events e
        JOIN event_types t ON t.id = e.event_type_id
    """

    def create(self, *, user_id: int, event_type_id: int, date: str,
               at: str | None, value: float | None, unit: str | None,
               notes: str | None) -> int:
        cur = self.conn.execute(
            """INSERT INTO events (user_id, event_type_id, date, at, value, unit, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, event_type_id, date, at, value, unit, notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def get(self, event_id: int, *, user_id: int) -> dict | None:
        row = self.conn.execute(
            f"{self._SELECT} WHERE e.id = ? AND e.user_id = ?",
            (event_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def list(self, *, user_id: int, start: str | None = None,
             end: str | None = None, event_type_id: int | None = None,
             limit: int = 100, offset: int = 0) -> list[dict]:
        clauses = ["e.user_id = ?"]
        params: list = [user_id]
        if start is not None:
            clauses.append("e.date >= ?")
            params.append(start)
        if end is not None:
            clauses.append("e.date <= ?")
            params.append(end)
        if event_type_id is not None:
            clauses.append("e.event_type_id = ?")
            params.append(event_type_id)
        rows = self.conn.execute(
            f"{self._SELECT} WHERE {' AND '.join(clauses)} "
            # id breaks ties so a page boundary cannot shuffle rows that share
            # a date and creation timestamp.
            "ORDER BY e.date DESC, e.at DESC, e.id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def update(self, event_id: int, *, user_id: int, **updates) -> None:
        allowed = {"date", "at", "value", "unit", "notes"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE events SET {assignments}, updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (*fields.values(), event_id, user_id),
        )
        self.conn.commit()

    def delete(self, event_id: int, *, user_id: int) -> None:
        self.conn.execute(
            "DELETE FROM events WHERE id = ? AND user_id = ?", (event_id, user_id)
        )
        self.conn.commit()

    def summary(self, *, user_id: int, start: str | None = None,
                end: str | None = None) -> list[dict]:
        """Per type and unit: how many events, and the total where measured.

        Grouped by unit as well as type because a type whose unit changed
        part-way through has genuinely incommensurable rows, and adding
        minutes to sessions would invent a number nobody recorded. Events with
        no value are counted separately rather than treated as zero.
        """
        clauses = ["e.user_id = ?"]
        params: list = [user_id]
        if start is not None:
            clauses.append("e.date >= ?")
            params.append(start)
        if end is not None:
            clauses.append("e.date <= ?")
            params.append(end)
        rows = self.conn.execute(
            f"""
            SELECT
                e.event_type_id                                   AS event_type_id,
                t.name                                            AS event_type_name,
                e.unit                                            AS unit,
                COUNT(*)                                          AS count,
                SUM(CASE WHEN e.value IS NULL THEN 1 ELSE 0 END)  AS unmeasured_count,
                SUM(e.value)                                      AS total_value
            FROM events e
            JOIN event_types t ON t.id = e.event_type_id
            WHERE {' AND '.join(clauses)}
            GROUP BY e.event_type_id, e.unit
            ORDER BY t.name, e.unit
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
