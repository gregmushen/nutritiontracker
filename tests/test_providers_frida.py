import pytest

from app.providers.frida import (
    check_parameter_units,
    normalize_frida_food,
    normalize_unit,
    parse_frida_value,
    read_frida_workbook,
)

openpyxl = pytest.importorskip("openpyxl")

PARAMETERS = [
    ("356", "Energy (kcal)", "kcal/100 g"),
    ("218", "Protein", "g/100g"),
    ("172", "Available carbohydrates", "g/100g"),
    ("170", "Carbohydrate by difference", "g/100g"),
    ("47", "Vitamin C", "mg/100g"),
    ("116", "Choline", "mg/100g"),
    ("163", "Iodine", "µg/100g"),
    ("12", "Vitamin A", "RE (µg/100g)"),
    ("135", "Vitamin E", "alfa-TE"),
    ("442", "Vitamin K", "µg/100g"),
    ("164", "Vitamin K1", "µg/100g"),
]


def _write_workbook(path, *, foods, measurements, parameters=PARAMETERS, groups=None):
    """`foods` is [(food_id, name)]; `measurements` is [(food_id, param_id, value)]."""
    groups = groups or {}
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Parameter")
    ws.append(["ParameterNavn", "ParameterName", "Unit", "ParameterID"])
    for pid, name, unit in parameters:
        ws.append([name, name, unit, pid])

    ws = wb.create_sheet("Food")
    ws.append(["FoodName", "FoodID", "FoodGroupID"])
    for food_id, name in foods:
        ws.append([name, food_id, groups.get(food_id)])

    ws = wb.create_sheet("Data_Normalised")
    ws.append(["FoodID", "FoodName", "ParameterID", "ParameterName", "ResVal"])
    names = dict(foods)
    for food_id, pid, value in measurements:
        ws.append([food_id, names[food_id], pid, "", value])

    wb.save(path)
    return path


def test_parse_values():
    assert parse_frida_value("38.4579487179487") == pytest.approx(38.4579487179487)
    assert parse_frida_value("0") == 0.0
    assert parse_frida_value("NULL") is None
    assert parse_frida_value(None) is None
    assert parse_frida_value("") is None


def test_normalize_unit_handles_published_forms():
    assert normalize_unit("g/100g") == "g"
    assert normalize_unit("mg/100g") == "mg"
    assert normalize_unit("µg/100g") == "ug"
    assert normalize_unit("kcal/100 g") == "kcal"
    # Equivalence units carry no explicit mass unit.
    assert normalize_unit("RE (µg/100g)") == "ug"
    assert normalize_unit("alfa-TE") == "mg"
    assert normalize_unit(None) == ""


def test_check_parameter_units_accepts_published_units():
    check_parameter_units({pid: unit for pid, _, unit in PARAMETERS})


def test_check_parameter_units_rejects_a_changed_unit():
    """An upstream mg/ug switch would scale values by 1000 with no error."""
    with pytest.raises(ValueError, match="reported in"):
        check_parameter_units({"163": "mg/100g"})


def test_normalize_maps_measurements():
    food = normalize_frida_food(
        {"356": 38.46, "218": 0.66, "47": 66.85},
        food_id="1",
        name="Strawberry, raw",
        group="51",
    )
    assert food["source"] == "frida"
    assert food["source_code"] == "1"
    assert food["calories_kcal"] == 38.46
    assert food["vitamin_c_mg"] == 66.85
    assert food["categories_tags"] == ["frida:51"]


def test_normalize_leaves_unmeasured_nutrients_unknown():
    """No row for a parameter means it was never measured, not that it is zero."""
    food = normalize_frida_food({"356": 38.46}, food_id="1", name="Strawberry, raw")
    assert food["choline_mg"] is None
    assert food["vitamin_k_ug"] is None
    # Frida reports no folic acid at all.
    assert food["folic_acid_ug"] is None


def test_normalize_keeps_measured_zero():
    food = normalize_frida_food({"121": 0.0}, food_id="1", name="X")
    assert food["caffeine_mg"] == 0.0


def test_normalize_prefers_available_carbohydrate():
    food = normalize_frida_food({"172": 6.86, "170": 7.7}, food_id="1", name="X")
    assert food["carbs_g"] == 6.86
    fallback = normalize_frida_food({"170": 7.7}, food_id="2", name="Y")
    assert fallback["carbs_g"] == 7.7


def test_normalize_falls_back_to_vitamin_k1():
    total = normalize_frida_food({"442": 20.0, "164": 18.0}, food_id="1", name="X")
    assert total["vitamin_k_ug"] == 20.0
    fallback = normalize_frida_food({"164": 18.0}, food_id="2", name="Y")
    assert fallback["vitamin_k_ug"] == 18.0


def test_read_workbook(tmp_path):
    path = _write_workbook(
        tmp_path / "frida.xlsx",
        foods=[("1", "Strawberry, raw"), ("3", "Banana, raw")],
        measurements=[
            ("1", "356", "38.4579487179487"),
            ("1", "47", "66.85"),
            ("1", "163", "0.0503"),
            ("3", "356", "93.4754660894661"),
            ("3", "47", "11.2"),
        ],
        groups={"1": "51", "3": "52"},
    )
    foods = {f["source_code"]: f for f in read_frida_workbook(path)}
    assert set(foods) == {"1", "3"}
    assert foods["1"]["calories_kcal"] == pytest.approx(38.4579487179487)
    assert foods["1"]["iodine_ug"] == 0.0503
    assert foods["1"]["categories_tags"] == ["frida:51"]
    assert foods["3"]["vitamin_c_mg"] == 11.2
    assert foods["3"]["iodine_ug"] is None


def test_read_workbook_skips_null_results(tmp_path):
    path = _write_workbook(
        tmp_path / "frida.xlsx",
        foods=[("1", "Strawberry, raw")],
        measurements=[("1", "356", "38.46"), ("1", "116", "NULL")],
    )
    food = next(iter(read_frida_workbook(path)))
    assert food["calories_kcal"] == 38.46
    assert food["choline_mg"] is None


def test_read_workbook_rejects_unexpected_units(tmp_path):
    parameters = [
        (pid, name, "mg/100g" if pid == "163" else unit)
        for pid, name, unit in PARAMETERS
    ]
    path = _write_workbook(
        tmp_path / "frida.xlsx",
        foods=[("1", "X")],
        measurements=[("1", "356", "10")],
        parameters=parameters,
    )
    with pytest.raises(ValueError, match="reported in"):
        list(read_frida_workbook(path))


def test_read_workbook_requires_expected_sheets(tmp_path):
    path = _write_workbook(
        tmp_path / "frida.xlsx", foods=[("1", "X")], measurements=[("1", "356", "10")]
    )
    wb = openpyxl.load_workbook(path)
    del wb["Data_Normalised"]
    wb.save(path)
    with pytest.raises(ValueError, match="missing the 'Data_Normalised' sheet"):
        list(read_frida_workbook(path))


def test_import_frida_end_to_end(tmp_path):
    from app.database import get_connection
    from scripts.import_frida import import_frida

    path = _write_workbook(
        tmp_path / "frida.xlsx",
        foods=[("1", "Strawberry, raw"), ("3", "Banana, raw")],
        measurements=[
            ("1", "356", "38.4579487179487"),
            ("1", "47", "66.85"),
            ("1", "116", "5.7"),
            ("3", "356", "93.4754660894661"),
        ],
        groups={"1": "51"},
    )
    db_path = tmp_path / "nutrition.db"
    assert import_frida(str(path), str(db_path)) == 2

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT source, source_code, name, calories_kcal, vitamin_c_mg, "
        "choline_mg, folic_acid_ug FROM foods ORDER BY CAST(source_code AS INTEGER)"
    ).fetchall()
    conn.close()

    assert [r["source"] for r in rows] == ["frida", "frida"]
    assert rows[0]["name"] == "Strawberry, raw"
    assert rows[0]["vitamin_c_mg"] == 66.85
    assert rows[0]["choline_mg"] == 5.7
    assert rows[0]["folic_acid_ug"] is None
    assert rows[1]["vitamin_c_mg"] is None


def test_read_workbook_rejects_a_parameter_with_no_published_unit(tmp_path):
    """A parameter missing from the Parameter sheet must not import unverified.

    Comparing units only protects the values it can see, so a nutrient the
    metadata never describes would be stored on trust.
    """
    path = _write_workbook(
        tmp_path / "frida.xlsx",
        foods=[("1", "Strawberry, raw")],
        measurements=[("1", "356", "38.46"), ("1", "163", "0.05")],
        parameters=[p for p in PARAMETERS if p[0] != "163"],
    )

    with pytest.raises(ValueError, match="163"):
        list(read_frida_workbook(path))
