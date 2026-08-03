import json
import sqlite3

import pytest

from app.providers.cronometer import (
    FIELD_NUTRIENTS,
    PUBLISHED_UNITS,
    check_nutrient_units,
    normalize_cronometer_food,
    parse_source,
    pick_serving,
    read_cronometer_export,
    unresolved_food_names,
)
from app.sources import SOURCES_BY_CODE

ACAI = {
    "id": 4894931,
    "name": "Acai Berry",
    "source": "NCCDB:118907",
    "defaultMeasureId": 12467452,
    "measures": [
        {"id": 12467449, "amount": 1, "name": "cup", "value": 230.0},
        {"id": 12467452, "amount": 1, "name": "g", "value": 1},
    ],
    "nutrients": [
        {"id": 208, "amount": 61, "type": "PRIMARY"},
        {"id": 203, "amount": 0.82, "type": "PRIMARY"},
        {"id": 323, "amount": 14.8, "type": "PRIMARY"},
        {"id": 324, "amount": 80, "type": "PRIMARY"},
        {"id": 401, "amount": 0, "type": "PRIMARY"},
    ],
}


def _write_export(tmp_path, documents, *, units=None, referenced=None):
    details = tmp_path / "raw" / "mobile" / "food_details" / "objects" / "ab"
    details.mkdir(parents=True)
    for index, document in enumerate(documents):
        (details / f"{index}.json").write_text(json.dumps(document), encoding="utf-8")

    conn = sqlite3.connect(tmp_path / "cronometer.sqlite3")
    conn.execute(
        "CREATE TABLE referenced_items (name TEXT, enriched INTEGER, enriched_json TEXT)"
    )
    rows = referenced
    if rows is None:
        rows = [
            (
                d["name"],
                {
                    "food_id": d["id"],
                    "nutrients": [
                        {
                            "nutrient_id": n["id"],
                            "unit": (units or PUBLISHED_UNITS).get(n["id"], ""),
                            "value": n["amount"],
                        }
                        for n in d["nutrients"]
                    ],
                },
            )
            for d in documents
        ]
    conn.executemany(
        "INSERT INTO referenced_items VALUES (?, 1, ?)",
        [(name, json.dumps(payload)) for name, payload in rows],
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_every_mapped_nutrient_declares_a_unit():
    assert set(FIELD_NUTRIENTS.values()) <= set(PUBLISHED_UNITS)


def test_source_codes_are_registered():
    from app.providers.cronometer import CRONOMETER_SOURCE, SOURCE_PREFIXES

    for code in (*SOURCE_PREFIXES.values(), CRONOMETER_SOURCE):
        assert code in SOURCES_BY_CODE


def test_values_are_taken_per_100g_unchanged():
    food = normalize_cronometer_food(ACAI)
    assert food["calories_kcal"] == 61
    assert food["protein_g"] == 0.82
    assert food["vitamin_e_mg"] == 14.8
    assert food["base_quantity"] == 100
    assert food["base_unit"] == "g"


def test_vitamin_d_converts_from_iu_to_micrograms():
    food = normalize_cronometer_food(ACAI)
    assert food["vitamin_d_ug"] == pytest.approx(2.0)


def test_unmeasured_nutrients_are_none_not_zero():
    food = normalize_cronometer_food(ACAI)
    assert food["choline_mg"] is None
    assert food["iodine_ug"] is None
    # Folic acid is never reported separately from total folate.
    assert food["folic_acid_ug"] is None


def test_measured_zero_is_preserved():
    food = normalize_cronometer_food(ACAI)
    assert food["vitamin_c_mg"] == 0


@pytest.mark.parametrize(
    ("raw_source", "expected"),
    [
        ("NCCDB:118907", ("nccdb", "118907")),
        ("CRDB:12345", ("crdb", "12345")),
        ("Nutritionix:abc", ("nutritionix", "abc")),
        ("NUTTAB:31103002", ("nuttab", "31103002")),
        ("Custom", ("cronometer_custom", "777")),
        ("NCCDB", ("nccdb", "777")),
        # Databases we import in full stay under the generic code so the
        # authoritative row is never overwritten.
        ("FDC:Branded:1902975", ("cronometer", "777")),
        ("CoFID:19-599", ("cronometer", "777")),
        ("CNF2015:4400", ("cronometer", "777")),
        ("USDAsr:06180", ("cronometer", "777")),
        (None, ("cronometer", "777")),
    ],
)
def test_parse_source(raw_source, expected):
    assert parse_source(raw_source, 777) == expected


def test_named_portion_is_preferred_over_a_bare_gram_default():
    grams, text = pick_serving(ACAI["measures"], ACAI["defaultMeasureId"])
    assert (grams, text) == (230.0, "1 cup")


def test_default_measure_wins_when_it_is_a_real_portion():
    measures = [
        {"id": 1, "amount": 1, "name": "cup", "value": 230.0},
        {"id": 2, "amount": 1, "name": "tbsp", "value": 14.0},
    ]
    assert pick_serving(measures, 2) == (14.0, "1 tbsp")


def test_hidden_and_valueless_measures_are_ignored():
    measures = [
        {"id": 1, "amount": 1, "name": "cup", "value": 230.0, "hidden": True},
        {"id": 2, "amount": 1, "name": "slice", "value": 0},
        {"id": 3, "amount": 2, "name": "wedge", "value": 40.0},
    ]
    assert pick_serving(measures, 1) == (40.0, "2 wedge")


def test_serving_is_none_when_only_bare_units_exist():
    assert pick_serving([{"id": 1, "amount": 1, "name": "g", "value": 1}], 1) == (
        None,
        None,
    )


def test_provenance_is_recorded_in_tags():
    food = normalize_cronometer_food(ACAI)
    assert food["source"] == "nccdb"
    assert food["source_code"] == "118907"
    assert "cronometer:4894931" in food["categories_tags"]
    assert "cronometer-source:NCCDB:118907" in food["categories_tags"]


def test_trailing_comma_is_stripped_from_names():
    document = dict(ACAI, name="Celcius, Sparkling Beverage, Raspberry/Acai,")
    assert normalize_cronometer_food(document)["name"] == (
        "Celcius, Sparkling Beverage, Raspberry/Acai"
    )


def test_micro_sign_units_are_accepted():
    check_nutrient_units({317: "\u00b5g", 430: "\u00b5g"})


def test_unexpected_unit_fails_loudly(tmp_path):
    # A future export that switched vitamin D to micrograms must not be
    # silently divided by 40.
    with pytest.raises(ValueError, match="nutrient 324"):
        check_nutrient_units({324: "\u00b5g"})


def test_read_export_verifies_units(tmp_path):
    _write_export(tmp_path, [ACAI], units={**PUBLISHED_UNITS, 323: "g"})
    with pytest.raises(ValueError, match="nutrient 323"):
        list(read_cronometer_export(tmp_path))


def test_read_export_requires_crawl_database(tmp_path):
    details = tmp_path / "raw" / "mobile" / "food_details" / "objects"
    details.mkdir(parents=True)
    (details / "food.json").write_text(json.dumps(ACAI))

    with pytest.raises(FileNotFoundError, match="cronometer.sqlite3"):
        list(read_cronometer_export(tmp_path))


def test_read_export_requires_units_for_every_imported_nutrient(tmp_path):
    units = dict(PUBLISHED_UNITS)
    units.pop(324)
    _write_export(tmp_path, [ACAI], units=units)

    with pytest.raises(ValueError, match="nutrient\\(s\\): 324"):
        list(read_cronometer_export(tmp_path))


def test_read_export_yields_foods(tmp_path):
    _write_export(tmp_path, [ACAI])
    foods = list(read_cronometer_export(tmp_path))
    assert [f["name"] for f in foods] == ["Acai Berry"]
    assert foods[0]["vitamin_e_mg"] == 14.8


def test_missing_food_details_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        list(read_cronometer_export(tmp_path))


def test_unresolved_foods_are_reported(tmp_path):
    _write_export(
        tmp_path,
        [ACAI],
        referenced=[
            ("Acai Berry", {"food_id": 4894931, "nutrients": []}),
            ("Eggs, Cooked", {"food_id": 69011855, "nutrients": []}),
        ],
    )
    assert unresolved_food_names(tmp_path) == ["Eggs, Cooked"]


def test_import_writes_foods_to_the_database(tmp_path):
    from app.database import get_connection, init_schema
    from scripts.import_cronometer import import_cronometer

    _write_export(tmp_path, [ACAI])
    db_path = tmp_path / "test.db"
    assert import_cronometer(str(tmp_path), str(db_path)) == 1

    conn = get_connection(db_path)
    init_schema(conn)
    row = conn.execute(
        "SELECT source, source_code, owner_user_id, name, vitamin_e_mg, vitamin_d_ug, choline_mg,"
        " serving_quantity, serving_size_text FROM foods"
    ).fetchone()
    assert row["source"] == "nccdb"
    assert row["source_code"] == "118907"
    assert row["owner_user_id"] == 1
    assert row["vitamin_e_mg"] == 14.8
    assert row["vitamin_d_ug"] == pytest.approx(2.0)
    assert row["choline_mg"] is None
    assert (row["serving_quantity"], row["serving_size_text"]) == (230.0, "1 cup")
    conn.close()


def test_reimport_updates_rather_than_duplicates(tmp_path):
    from app.database import get_connection, init_schema
    from scripts.import_cronometer import import_cronometer

    _write_export(tmp_path, [ACAI])
    db_path = tmp_path / "test.db"
    import_cronometer(str(tmp_path), str(db_path))
    import_cronometer(str(tmp_path), str(db_path))

    conn = get_connection(db_path)
    init_schema(conn)
    assert conn.execute("SELECT COUNT(*) c FROM foods").fetchone()["c"] == 1
    conn.close()


def test_two_users_can_import_the_same_private_food_independently(tmp_path):
    from app.database import get_connection, init_schema
    from scripts.import_cronometer import import_cronometer

    _write_export(tmp_path, [ACAI])
    db_path = tmp_path / "test.db"
    import_cronometer(str(tmp_path), str(db_path), owner_user_id=1)

    conn = get_connection(db_path)
    init_schema(conn)
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'Second')")
    conn.commit()
    conn.close()

    import_cronometer(str(tmp_path), str(db_path), owner_user_id=2)

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT owner_user_id FROM foods WHERE source_code = '118907' ORDER BY owner_user_id"
    ).fetchall()
    conn.close()
    assert [row["owner_user_id"] for row in rows] == [1, 2]
