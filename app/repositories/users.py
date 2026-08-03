import hashlib
import secrets
import sqlite3


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UserRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, created_at, updated_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def create(self, name: str) -> tuple[dict, str]:
        token = secrets.token_urlsafe(32)
        cur = self.conn.execute(
            "INSERT INTO users (name, token_hash) VALUES (?, ?)",
            (name, _token_hash(token)),
        )
        self.conn.commit()
        user = self.get(cur.lastrowid)
        assert user is not None
        return user, token

    def rotate_token(self, user_id: int) -> tuple[dict, str] | None:
        token = secrets.token_urlsafe(32)
        cur = self.conn.execute(
            "UPDATE users SET token_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (_token_hash(token), user_id),
        )
        self.conn.commit()
        if not cur.rowcount:
            return None
        user = self.get(user_id)
        assert user is not None
        return user, token
