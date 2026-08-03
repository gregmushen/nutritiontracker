import csv

import pytest

from app.providers.cnf import (
    check_nutrient_units,
    normalize_cnf_food,
    parse_cnf_value,
    read_cnf_directory,
)

NUTRIENT_NAMES = [
    ("208", "KCAL", "kilocalorie"),
    ("203", "PROT", "Gram"),
    ("291", "TDF", "Gram"),
    ("430", "VITK", "Microgram"),
    ("262", "CAFF", "Milligram"),
    ("435", "DFE", "Microgram"),
    ("417", "FOLA", "Microgram"),
]


def _write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_bundle(directory, *, foods, amounts, measures=(), nutrients=NUTRIENT_NAMES):
    directory.mkdir(exist_ok=True)
    _write_csv(
        directory / "Nutrient_Name.csv",
        ["Nutrient_Code", "Nutrient_Symbol", "Nutrient_Unit"],
        [
            {"Nutrient_Code": c, "Nutrient_Symbol": s, "Nutrient_Unit": u}
            for c, s, u in nutrients
        ],
    )
    _write_csv(
        directory / "Food_Name.csv",
        ["Food_Code", "Food_Description_EN", "CNF_Food_Group_Code"],
        [
            {
                "Food_Code": code,
                "Food_Description_EN": name,
                "CNF_Food_Group_Code": group,
            }
            for code, name, group in foods
        ],
    )
    _write_csv(
        directory / "Nutrient_Amount.csv",
        ["Food_Code", "Nutrient_Code", "Nutrient_Amount"],
        [
            {"Food_Code": f, "Nutrient_Code": n, "Nutrient_Amount": v}
            for f, n, v in amounts
        ],
    )
    _write_csv(
        directory / "Measure_Weight_Conversion.csv",
        ["Food_Code", "Measure_Type_Code", "Measure_Code", "Measure_Weight_Conversion"],
        [
            {
                "Food_Code": f,
                "Measure_Type_Code": t,
                "Measure_Code": m,
                "Measure_Weight_Conversion": g,
            }
            for f, t, m, g in measures
        ],
    )
    _write_csv(
        directory / "Measure_Name.csv",
        ["Measure_Code", "Measure_Description_and_Unit_EN"],
        [
            {"Measure_Code": "750", "Measure_Description_and_Unit_EN": "total refuse"},
            {"Measure_Code": "341", "Measure_Description_and_Unit_EN": "100 ml"},
            {"Measure_Code": "383", "Measure_Description_and_Unit_EN": "1 slice"},
        ],
    )
    return directory


def test_parse_values():
    assert parse_cnf_value("9.544150000") == 9.54415
    assert parse_cnf_value("0.000") == 0.0
    assert parse_cnf_value("") is None
    assert parse_cnf_value(None) is None
    assert parse_cnf_value("n/a") is None


def test_normalize_maps_nutrients():
    food = normalize_cnf_food(
        {"208": 23.0, "203": 2.86, "430": 482.9},
        food_code="2213",
        name="Spinach, raw",
        group="11",
    )
    assert food["source"] == "cnf"
    assert food["source_code"] == "2213"
    assert food["calories_kcal"] == 23.0
    assert food["vitamin_k_ug"] == 482.9
    assert food["categories_tags"] == ["cnf:11"]
    assert food["base_quantity"] == 100
    assert food["base_unit"] == "g"


def test_normalize_leaves_unmeasured_nutrients_unknown():
    """A nutrient with no CNF row was never assayed, so it must not read as 0."""
    food = normalize_cnf_food({"208": 23.0}, food_code="2213", name="Spinach, raw")
    assert food["vitamin_k_ug"] is None
    assert food["selenium_ug"] is None
    # CNF measures no iodine at all.
    assert food["iodine_ug"] is None
    assert food["chromium_ug"] is None
    assert food["added_sugar_g"] is None


def test_normalize_keeps_measured_zero():
    food = normalize_cnf_food({"262": 0.0}, food_code="1", name="Water")
    assert food["caffeine_mg"] == 0.0


def test_normalize_folate_prefers_dfe():
    dfe = normalize_cnf_food({"435": 194.0, "417": 116.0}, food_code="1", name="X")
    assert dfe["folate_ug"] == 194.0
    fallback = normalize_cnf_food({"417": 116.0}, food_code="2", name="Y")
    assert fallback["folate_ug"] == 116.0


def test_check_nutrient_units_accepts_published_units():
    check_nutrient_units({c: u for c, _, u in NUTRIENT_NAMES})


def test_check_nutrient_units_rejects_a_changed_unit():
    """A silent unit change upstream would scale values by 1000."""
    with pytest.raises(ValueError, match="reported in"):
        check_nutrient_units({"430": "Milligram"})


def test_read_directory(tmp_path):
    directory = _write_bundle(
        tmp_path / "cnf",
        foods=[("2213", "Spinach, raw", "11"), ("2873", "Coffee, brewed", "14")],
        amounts=[
            ("2213", "208", "23.0"),
            ("2213", "430", "482.9"),
            ("2873", "208", "1.0"),
            ("2873", "262", "40.0"),
        ],
        measures=[("2213", "6", "341", "12.68")],
    )
    foods = {f["source_code"]: f for f in read_cnf_directory(directory)}
    assert set(foods) == {"2213", "2873"}
    assert foods["2213"]["vitamin_k_ug"] == 482.9
    assert foods["2213"]["serving_quantity"] == 12.68
    assert foods["2213"]["serving_size_text"] == "100 ml"
    assert foods["2873"]["caffeine_mg"] == 40.0
    assert foods["2873"]["vitamin_k_ug"] is None
    assert foods["2873"]["serving_quantity"] is None


def test_read_directory_ignores_refuse_measures(tmp_path):
    """Refuse rows are the inedible part of a food, not a serving of it."""
    directory = _write_bundle(
        tmp_path / "cnf",
        foods=[("2213", "Spinach, raw", "11")],
        amounts=[("2213", "208", "23.0")],
        measures=[
            ("2213", "3", "750", "28"),      # refuse: stems
            ("2213", "9", "383", "90"),      # cooking yield
            ("2213", "6", "341", "12.68"),   # the real household measure
        ],
    )
    food = next(iter(read_cnf_directory(directory)))
    assert food["serving_quantity"] == 12.68
    assert food["serving_size_text"] == "100 ml"


def test_read_directory_rejects_unexpected_units(tmp_path):
    directory = _write_bundle(
        tmp_path / "cnf",
        foods=[("1", "X", "1")],
        amounts=[("1", "208", "23.0")],
        nutrients=[("430", "VITK", "Milligram")],
    )
    with pytest.raises(ValueError, match="reported in"):
        list(read_cnf_directory(directory))


def test_read_directory_reports_a_missing_file(tmp_path):
    directory = _write_bundle(
        tmp_path / "cnf", foods=[("1", "X", "1")], amounts=[("1", "208", "23.0")]
    )
    (directory / "Nutrient_Amount.csv").unlink()
    with pytest.raises(ValueError, match="missing Nutrient_Amount.csv"):
        list(read_cnf_directory(directory))


def test_import_cnf_end_to_end(tmp_path):
    from app.database import get_connection
    from scripts.import_cnf import import_cnf

    directory = _write_bundle(
        tmp_path / "cnf",
        foods=[("2213", "Spinach, raw", "11"), ("2873", "Coffee, brewed", "14")],
        amounts=[
            ("2213", "208", "23.0"),
            ("2213", "430", "482.9"),
            ("2873", "208", "1.0"),
            ("2873", "262", "40.0"),
        ],
        measures=[("2213", "6", "341", "12.68")],
    )
    db_path = tmp_path / "nutrition.db"
    assert import_cnf(str(directory), str(db_path)) == 2

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT source, source_code, calories_kcal, vitamin_k_ug, caffeine_mg, "
        "iodine_ug, serving_quantity FROM foods ORDER BY source_code"
    ).fetchall()
    conn.close()

    assert [r["source"] for r in rows] == ["cnf", "cnf"]
    assert rows[0]["vitamin_k_ug"] == 482.9
    assert rows[0]["serving_quantity"] == 12.68
    assert rows[1]["caffeine_mg"] == 40.0
    assert rows[1]["vitamin_k_ug"] is None
    assert rows[0]["iodine_ug"] is None


def test_read_directory_rejects_a_nutrient_with_no_published_unit(tmp_path):
    """A code missing from Nutrient_Name.csv must not import unverified.

    Comparing units only protects the values it can see, so a nutrient the
    metadata never describes would be stored on trust — the silent 1000x
    rescale that verifying units exists to prevent.
    """
    directory = _write_bundle(
        tmp_path / "cnf",
        foods=[("2213", "Spinach, raw", "11")],
        amounts=[("2213", "208", "23.0"), ("2213", "430", "482.9")],
        nutrients=[n for n in NUTRIENT_NAMES if n[0] != "430"],
    )

    with pytest.raises(ValueError, match="430"):
        list(read_cnf_directory(directory))
