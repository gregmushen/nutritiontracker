import pytest

from app.providers.afcd import (
    kj_to_kcal,
    normalize_afcd_food,
    normalize_header,
    parse_afcd_value,
    read_afcd_workbook,
)

openpyxl = pytest.importorskip("openpyxl")

# Enough of the real layout to exercise the reader, including the two traps:
# percent-of-total fatty acid columns and a trans fat column in milligrams.
HEADERS = [
    "Public Food Key",
    "Classification",
    "Food Name",
    "Energy with dietary fibre, equated  (kJ)",
    "Protein  \n(g)",
    "Fat, total  (g)",
    "Available carbohydrate, without sugar alcohols  (g)",
    "Available carbohydrate, with sugar alcohols  (g)",
    "Total sugars (g)",
    "Added sugars (g)",
    "Total dietary fibre  (g)",
    "Total saturated fatty acids, equated (%T)",
    "Total saturated fatty acids, equated  (g)",
    "Total monounsaturated fatty acids, equated  (g)",
    "Total polyunsaturated fatty acids, equated  (g)",
    "Total trans fatty acids, imputed  (mg)",
    "Cholesterol  (mg)",
    "Caffeine  (mg)",
    "Sodium (Na)  (mg)",
    "Potassium (K)  (mg)",
    "Calcium (Ca)  (mg)",
    "Magnesium (Mg)  (mg)",
    "Phosphorus (P)  (mg)",
    "Iron (Fe)  (mg)",
    "Copper (Cu)  (mg)",
    "Zinc (Zn)  (mg)",
    "Manganese (Mn)  (mg)",
    "Selenium (Se)  (ug)",
    "Iodine (I)  (ug)",
    "Chromium (Cr)  (ug)",
    "Vitamin A retinol equivalents  (ug)",
    "Vitamin D3 equivalents  (ug)",
    "Vitamin E  (mg)",
    "Thiamin (B1)  (mg)",
    "Riboflavin (B2)  (mg)",
    "Niacin (B3)  (mg)",
    "Pyridoxine (B6)  (mg)",
    "Cobalamin (B12)  (ug)",
    "Dietary folate equivalents  (ug)",
    "Total folates  (ug)",
    "Folic acid  (ug)",
    "Pantothenic acid (B5)  (mg)",
    "Biotin (B7)  (ug)",
    "Vitamin C  (mg)",
]


def _write_workbook(path, foods, *, headers=HEADERS, sheet="All solids & liquids per 100 g"):
    """`foods` is a list of (key, classification, name, {heading: value})."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(sheet)
    ws.append(["Release 3 - Nutrient profiles "])
    ws.append([])
    ws.append(headers)
    for key, classification, name, values in foods:
        row = []
        for heading in headers:
            clean = normalize_header(heading)
            if clean == "Public Food Key":
                row.append(key)
            elif clean == "Classification":
                row.append(classification)
            elif clean == "Food Name":
                row.append(name)
            else:
                row.append(values.get(clean))
        ws.append(row)
    wb.save(path)
    return path


def test_normalize_header_collapses_spacing():
    assert normalize_header("Protein  \n(g)") == "Protein (g)"
    assert normalize_header(None) == ""


def test_parse_values():
    assert parse_afcd_value("10.8") == 10.8
    assert parse_afcd_value(0) == 0.0
    assert parse_afcd_value(None) is None
    assert parse_afcd_value("") is None
    assert parse_afcd_value("n/a") is None


def test_kj_to_kcal():
    assert kj_to_kcal(1236) == 295.4
    assert kj_to_kcal(None) is None


def test_normalize_converts_energy_to_kcal():
    food = normalize_afcd_food(
        {"Energy with dietary fibre, equated (kJ)": "1236"},
        food_key="F002258",
        name="Cardamom seed, dried, ground",
    )
    assert food["calories_kcal"] == 295.4
    assert food["source"] == "afcd"
    assert food["source_code"] == "F002258"


def test_normalize_converts_trans_fat_from_milligrams():
    """The trans fat column is in mg while every other fat column is in g."""
    food = normalize_afcd_food(
        {"Total trans fatty acids, imputed (mg)": "1989.88"},
        food_key="F001973",
        name="Butter, plain, salted",
    )
    assert food["trans_fat_g"] == pytest.approx(1.98988)


def test_normalize_ignores_percent_of_total_fat_columns():
    """%T columns are shares of total fat, not grams per 100 g."""
    food = normalize_afcd_food(
        {
            "Total saturated fatty acids, equated (%T)": "69.2",
            "Total saturated fatty acids, equated (g)": "56.91",
        },
        food_key="F001973",
        name="Butter, plain, salted",
    )
    assert food["saturated_fat_g"] == 56.91


def test_normalize_leaves_blank_cells_unknown():
    food = normalize_afcd_food({}, food_key="F1", name="X")
    assert food["protein_g"] is None
    assert food["calories_kcal"] is None
    assert food["trans_fat_g"] is None
    # AFCD measures neither of these at all.
    assert food["vitamin_k_ug"] is None
    assert food["choline_mg"] is None


def test_normalize_keeps_measured_zero():
    food = normalize_afcd_food(
        {"Caffeine (mg)": "0", "Total trans fatty acids, imputed (mg)": "0"},
        food_key="F1",
        name="X",
    )
    assert food["caffeine_mg"] == 0.0
    assert food["trans_fat_g"] == 0.0


def test_normalize_folate_prefers_dietary_equivalents():
    food = normalize_afcd_food(
        {"Dietary folate equivalents (ug)": "60", "Total folates (ug)": "35"},
        food_key="F1",
        name="X",
    )
    assert food["folate_ug"] == 60
    fallback = normalize_afcd_food(
        {"Total folates (ug)": "35"}, food_key="F2", name="Y"
    )
    assert fallback["folate_ug"] == 35


def test_normalize_tags_classification():
    food = normalize_afcd_food(
        {}, food_key="F1", name="X", classification="31302"
    )
    assert food["categories_tags"] == ["afcd:31302"]


def test_read_workbook(tmp_path):
    path = _write_workbook(
        tmp_path / "afcd.xlsx",
        [
            ("F002258", "31302", "Cardamom seed, dried, ground", {
                "Energy with dietary fibre, equated (kJ)": 1236,
                "Protein (g)": 10.8,
                "Iodine (I) (ug)": 0,
            }),
            ("F003729", "13101", "Egg, chicken, whole, raw", {
                "Energy with dietary fibre, equated (kJ)": 533,
                "Protein (g)": 12.6,
                "Iodine (I) (ug)": 57.6,
            }),
        ],
    )
    foods = {f["source_code"]: f for f in read_afcd_workbook(path)}
    assert set(foods) == {"F002258", "F003729"}
    assert foods["F002258"]["protein_g"] == 10.8
    assert foods["F002258"]["iodine_ug"] == 0.0
    assert foods["F003729"]["iodine_ug"] == 57.6
    assert foods["F003729"]["calories_kcal"] == kj_to_kcal(533)
    assert foods["F003729"]["categories_tags"] == ["afcd:13101"]


def test_read_workbook_rejects_a_changed_layout(tmp_path):
    headers = [h for h in HEADERS if normalize_header(h) != "Iodine (I) (ug)"]
    path = _write_workbook(
        tmp_path / "afcd.xlsx",
        [("F1", "1", "X", {"Protein (g)": 1})],
        headers=headers,
    )
    with pytest.raises(ValueError, match="missing expected columns"):
        list(read_afcd_workbook(path))


def test_read_workbook_requires_the_per_100g_sheet(tmp_path):
    path = _write_workbook(
        tmp_path / "afcd.xlsx",
        [("F1", "1", "X", {})],
        sheet="Liquids only per 100 mL",
    )
    with pytest.raises(ValueError, match="missing the 'All solids"):
        list(read_afcd_workbook(path))


def test_import_afcd_end_to_end(tmp_path):
    from app.database import get_connection
    from scripts.import_afcd import import_afcd

    path = _write_workbook(
        tmp_path / "afcd.xlsx",
        [
            ("F001973", "19", "Butter, plain, salted", {
                "Energy with dietary fibre, equated (kJ)": 3069,
                "Fat, total (g)": 82.2,
                "Total saturated fatty acids, equated (g)": 56.91,
                "Total saturated fatty acids, equated (%T)": 69.2,
                "Total trans fatty acids, imputed (mg)": 1989.88,
                "Iodine (I) (ug)": 8.8,
            }),
            ("F003729", "13", "Egg, chicken, whole, raw", {
                "Energy with dietary fibre, equated (kJ)": 533,
                "Protein (g)": 12.6,
            }),
        ],
    )
    db_path = tmp_path / "nutrition.db"
    assert import_afcd(str(path), str(db_path)) == 2

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT source, source_code, calories_kcal, saturated_fat_g, trans_fat_g, "
        "iodine_ug, vitamin_k_ug, protein_g FROM foods ORDER BY source_code"
    ).fetchall()
    conn.close()

    assert [r["source"] for r in rows] == ["afcd", "afcd"]
    assert rows[0]["saturated_fat_g"] == 56.91
    assert rows[0]["trans_fat_g"] == pytest.approx(1.98988)
    assert rows[0]["iodine_ug"] == 8.8
    assert rows[0]["protein_g"] is None
    assert rows[0]["vitamin_k_ug"] is None
    assert rows[1]["calories_kcal"] == kj_to_kcal(533)
