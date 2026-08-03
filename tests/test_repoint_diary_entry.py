import json
import sqlite3

import pytest

from app.database import init_schema
from scripts.repoint_diary_entry import repoint


def _connection(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _insert_food(conn, *, source, source_code, name, **nutrients):
    columns = ["source", "source_code", "name", *nutrients]
    values = [source, source_code, name, *nutrients.values()]
    placeholders = ", ".join("?" for _ in columns)
    return conn.execute(
        f"INSERT INTO foods ({', '.join(columns)}) VALUES ({placeholders})", values
    ).lastrowid


def _insert_entry(conn, food_id, name, *, grams=100.0, unit="g"):
    return conn.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit, grams, nutrients_total)
           VALUES ('2026-08-01', 'snack', ?, ?, ?, ?, ?, ?, ?)""",
        (
            food_id,
            json.dumps({"name": name}),
            name,
            grams,
            unit,
            grams,
            json.dumps({"calories_kcal": 80.0, "vitamin_e_mg": 0.0}),
        ),
    ).lastrowid


def test_recomputes_nutrients_from_the_replacement_food(tmp_path):
    """A label row reports unmeasured micronutrients as zero; a reference row does not."""
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    label = _insert_food(
        conn,
        source="open_food_facts",
        source_code="0001",
        name="Acai Puree Packets",
        calories_kcal=80.0,
        vitamin_e_mg=0.0,
    )
    reference = _insert_food(
        conn,
        source="nccdb",
        source_code="118907",
        name="Acai Berry",
        calories_kcal=61.0,
        vitamin_e_mg=14.8,
    )
    entry_id = _insert_entry(conn, label, "Acai Puree Packets")
    conn.commit()
    conn.close()

    result = repoint(path, entry_id, reference)
    assert result["nutrients"]["vitamin_e_mg"] == 14.8
    assert result["nutrients"]["calories_kcal"] == 61.0

    check = sqlite3.connect(path)
    check.row_factory = sqlite3.Row
    row = check.execute(
        "SELECT food_id, food_name, nutrients_total, food_snapshot FROM diary_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    assert row["food_id"] == reference
    assert row["food_name"] == "Acai Berry"
    assert json.loads(row["nutrients_total"])["vitamin_e_mg"] == 14.8
    assert json.loads(row["food_snapshot"])["source"] == "nccdb"
    check.close()


def test_scales_nutrients_by_the_logged_weight(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    label = _insert_food(
        conn, source="open_food_facts", source_code="0001", name="Label", calories_kcal=80.0
    )
    reference = _insert_food(
        conn,
        source="nccdb",
        source_code="118907",
        name="Acai Berry",
        calories_kcal=61.0,
        vitamin_e_mg=14.8,
    )
    entry_id = _insert_entry(conn, label, "Label", grams=250.0)
    conn.commit()
    conn.close()

    result = repoint(path, entry_id, reference)
    assert result["nutrients"]["calories_kcal"] == pytest.approx(152.5)
    assert result["nutrients"]["vitamin_e_mg"] == pytest.approx(37.0)


def test_refuses_entries_that_would_need_a_unit_conversion(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    label = _insert_food(
        conn, source="open_food_facts", source_code="0001", name="Label", calories_kcal=80.0
    )
    reference = _insert_food(
        conn, source="nccdb", source_code="118907", name="Acai Berry", calories_kcal=61.0
    )
    entry_id = _insert_entry(conn, label, "Label", unit="packet")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="unit conversion"):
        repoint(path, entry_id, reference)


def test_rejects_unknown_ids(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    food = _insert_food(
        conn, source="nccdb", source_code="1", name="Acai Berry", calories_kcal=61.0
    )
    entry_id = _insert_entry(conn, food, "Acai Berry")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="No diary entry"):
        repoint(path, 9999, food)
    with pytest.raises(ValueError, match="No food"):
        repoint(path, entry_id, 9999)


def test_rejects_food_owned_by_another_user(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'Second')")
    original = _insert_food(
        conn, source="custom", source_code=None, name="Original"
    )
    private = _insert_food(
        conn,
        source="custom",
        source_code=None,
        name="Other user's food",
        owner_user_id=2,
    )
    entry_id = _insert_entry(conn, original, "Original")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="private to a different user"):
        repoint(path, entry_id, private)


def test_repoint_keeps_tag_arrays_as_arrays(tmp_path):
    path = tmp_path / "db.sqlite"
    conn = _connection(path)
    original = _insert_food(
        conn, source="open_food_facts", source_code="1", name="Original"
    )
    replacement = _insert_food(
        conn,
        source="custom",
        source_code=None,
        name="Tagged",
        allergens_tags=json.dumps(["en:milk"]),
    )
    entry_id = _insert_entry(conn, original, "Original")
    conn.commit()
    conn.close()

    repoint(path, entry_id, replacement)

    check = sqlite3.connect(path)
    snapshot = json.loads(
        check.execute(
            "SELECT food_snapshot FROM diary_entries WHERE id = ?", (entry_id,)
        ).fetchone()[0]
    )
    check.close()
    assert snapshot["allergens_tags"] == ["en:milk"]
