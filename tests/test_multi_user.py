import hashlib
import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.repositories.foods import FoodRepository


def _admin_headers():
    return {"Authorization": "Bearer admin-token"}


def _create_user(client, name: str) -> dict:
    response = client.post("/users", headers=_admin_headers(), json={"name": name})
    assert response.status_code == 201
    return response.json()


def _token_headers(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def test_user_tokens_isolate_personal_data_and_custom_foods(client, db, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    user = _create_user(client, "Second user")
    user_headers = {"Authorization": f"Bearer {user['token']}"}

    shared_food_id = FoodRepository(db).create(
        source="food_data_central", name="Shared banana", calories_kcal=89
    )
    custom_response = client.post(
        "/foods",
        headers=user_headers,
        json={"source": "custom", "name": "Private blend"},
    )
    assert custom_response.status_code == 201
    custom_food_id = custom_response.json()["id"]

    assert client.get(f"/foods/{custom_food_id}", headers=_admin_headers()).status_code == 404
    assert client.get(f"/foods/{custom_food_id}", headers=user_headers).status_code == 200

    diary_response = client.post(
        "/diary/2026-08-01/entries",
        headers=user_headers,
        json={
            "food_id": shared_food_id,
            "amount": 100,
            "unit": "g",
            "meal_type": "breakfast",
        },
    )
    assert diary_response.status_code == 201

    assert client.get("/diary/2026-08-01", headers=_admin_headers()).json() == []
    assert len(client.get("/diary/2026-08-01", headers=user_headers).json()) == 1


def test_private_source_codes_are_scoped_per_user(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    user = _create_user(client, "Second user")
    user_headers = _token_headers(user["token"])
    payload = {"source": "custom", "source_code": "shared-name", "name": "Blend"}

    first = client.post("/foods", headers=_admin_headers(), json=payload)
    second = client.post("/foods", headers=user_headers, json=payload)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_custom_food_endpoint_rejects_catalog_sources(client):
    response = client.post(
        "/foods",
        headers=_admin_headers(),
        json={"source": "open_food_facts", "source_code": "123", "name": "Squat"},
    )

    assert response.status_code == 422


def test_only_admin_can_create_users(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    user = _create_user(client, "Second user")

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {user['token']}"},
        json={"name": "Third user"},
    )

    assert response.status_code == 403


def test_multi_user_routes_are_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", False)

    response = client.get("/users/me", headers=_admin_headers())

    assert response.status_code == 404


def test_single_user_mode_rejects_alternate_user_token(client, db, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", False)
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO users (name, token_hash) VALUES (?, ?)",
        ("Second user", hashlib.sha256(token.encode()).hexdigest()),
    )
    db.commit()

    response = client.get(
        "/diary/2026-08-01", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_multi_user_without_a_token_is_refused_at_startup():
    """The combination would make every anonymous caller an admin."""
    with pytest.raises(ValidationError, match="NT_MULTI_USER_ENABLED requires NT_BEARER_TOKEN"):
        Settings(multi_user_enabled=True, bearer_token=None)


def test_unauthenticated_deployment_grants_no_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", None)
    monkeypatch.setattr(settings, "multi_user_enabled", True)

    assert client.get("/users").status_code == 403
    assert client.post("/users", json={"name": "Intruder"}).status_code == 403


def test_default_user_token_cannot_be_rotated(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", True)

    response = client.post(
        f"/users/{settings.default_user_id}/token", headers=_admin_headers()
    )

    assert response.status_code == 409
    assert "NT_BEARER_TOKEN" in response.json()["detail"]


def test_other_user_tokens_can_still_be_rotated(client, monkeypatch):
    monkeypatch.setattr(settings, "bearer_token", "admin-token")
    monkeypatch.setattr(settings, "multi_user_enabled", True)
    user = _create_user(client, "Rotatable")

    response = client.post(f"/users/{user['id']}/token", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["token"] != user["token"]


def test_schema_seeds_the_configured_default_user(monkeypatch):
    """A deployment that sets NT_DEFAULT_USER_ID must still be able to write.

    Owned rows reference users(id), so seeding a hardcoded 1 while the app
    attributes rows to a different id leaves every insert failing the foreign
    key on a completely fresh database.
    """
    import sqlite3

    from app.database import init_schema

    monkeypatch.setattr(settings, "default_user_id", 2)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)

    seeded = [row["id"] for row in conn.execute("SELECT id FROM users")]
    assert settings.default_user_id in seeded

    conn.execute(
        "INSERT INTO foods (name, source, owner_user_id) VALUES ('probe', 'custom', ?)",
        (settings.default_user_id,),
    )
    conn.close()


def test_migration_0005_seeds_the_configured_default_user(monkeypatch):
    """The upgrade path has the same constraint as a fresh install.

    Legacy custom foods are handed to the default user, so the id the
    migration seeds has to be the one the application is configured to use.
    """
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0005_add_users_and_food_ownership.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setenv("NT_DEFAULT_USER_ID", "2")
    assert module._default_user_id() == 2

    monkeypatch.delenv("NT_DEFAULT_USER_ID")
    assert module._default_user_id() == 1

    monkeypatch.setenv("NT_DEFAULT_USER_ID", "nope")
    with pytest.raises(ValueError, match="must be an integer"):
        module._default_user_id()

    monkeypatch.setenv("NT_DEFAULT_USER_ID", "0")
    with pytest.raises(ValueError, match="positive rowid"):
        module._default_user_id()


def test_migration_0005_owns_legacy_custom_and_recipe_foods(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    database_path = tmp_path / "legacy.db"
    monkeypatch.setenv("NT_DB_PATH", str(database_path))
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "0004")

    conn = sqlite3.connect(database_path)
    conn.executemany(
        "INSERT INTO foods (source, name) VALUES (?, ?)",
        [("custom", "Private custom"), ("recipe", "Private recipe")],
    )
    conn.commit()
    conn.close()

    command.upgrade(config, "head")

    conn = sqlite3.connect(database_path)
    owners = conn.execute(
        "SELECT source, owner_user_id FROM foods ORDER BY source"
    ).fetchall()
    conn.close()
    assert owners == [("custom", 1), ("recipe", 1)]
