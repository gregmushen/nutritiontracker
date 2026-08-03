import pytest

from app.providers.cofid import (
    normalize_cofid_food,
    parse_cofid_value,
    read_cofid_workbook,
)

openpyxl = pytest.importorskip("openpyxl")


PROXIMATE_CODES = ["KCALS", "PROT", "FAT", "CHO", "TOTSUG", "AOACFIB", "ENGFIB", "CHOL"]
INORGANIC_CODES = ["NA", "K", "CA", "FE", "SE", "I"]
VITAMIN_CODES = ["RETEQU", "VITD", "VITK1", "VITC", "VITB12"]

SHEET_CODES = {
    "1.3 Proximates": PROXIMATE_CODES,
    "1.4 Inorganics": INORGANIC_CODES,
    "1.5 Vitamins": VITAMIN_CODES,
}


def _write_workbook(path, foods, *, codes=None, misalign_sheet=None):
    """Build a miniature CoFID workbook.

    `foods` is a list of (food_code, name, group, {short_code: value}).
    """
    codes = codes or SHEET_CODES
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, sheet_codes in codes.items():
        ws = wb.create_sheet(sheet_name)
        meta = ["Food Code", "Food Name", "Description", "Group", "Previous",
                "Main data references", "Footnote"]
        ws.append(meta + [f"{c} (unit)" for c in sheet_codes])   # row 1: long names
        ws.append([""] * len(meta) + sheet_codes)                 # row 2: short codes
        ws.append([""] * len(meta) + sheet_codes)                 # row 3: descriptions
        for i, (food_code, name, group, values) in enumerate(foods):
            if misalign_sheet == sheet_name and i == 0:
                food_code = "SHUFFLED"
            ws.append(
                [food_code, name, "", group, "", "", ""]
                + [values.get(c) for c in sheet_codes]
            )
    wb.save(path)
    return path


def test_parse_unknown_marker_is_none():
    assert parse_cofid_value("N") is None


def test_parse_blank_is_none():
    assert parse_cofid_value(None) is None
    assert parse_cofid_value("") is None
    assert parse_cofid_value("   ") is None


def test_parse_trace_is_zero():
    """Trace is a measurement of effectively nothing, unlike an unknown."""
    assert parse_cofid_value("Tr") == 0.0


def test_parse_estimate_in_parentheses():
    assert parse_cofid_value("(0.07)") == 0.07


def test_parse_numbers():
    assert parse_cofid_value(12) == 12.0
    assert parse_cofid_value("3.5") == 3.5
    assert parse_cofid_value("0.0") == 0.0


def test_parse_unrecognised_text_is_none():
    assert parse_cofid_value("see note") is None


def test_normalize_maps_nutrients():
    food = normalize_cofid_food(
        {"KCALS": "151", "PROT": "2.9", "SE": "N", "I": "Tr", "VITK1": "315"},
        food_code="13-145",
        name="Ackee, canned, drained",
        group="DG",
    )
    assert food["source"] == "cofid"
    assert food["source_code"] == "13-145"
    assert food["calories_kcal"] == 151
    assert food["protein_g"] == 2.9
    assert food["selenium_ug"] is None
    assert food["iodine_ug"] == 0.0
    assert food["vitamin_k_ug"] == 315
    assert food["categories_tags"] == ["cofid:DG"]


def test_normalize_marks_unreported_nutrients_unknown():
    """CoFID never measures caffeine or choline — they must not read as zero."""
    food = normalize_cofid_food({"KCALS": "10"}, food_code="1", name="X", group="DG")
    assert food["caffeine_mg"] is None
    assert food["choline_mg"] is None
    assert food["added_sugar_g"] is None


def test_normalize_fibre_falls_back_to_nsp():
    aoac = normalize_cofid_food(
        {"AOACFIB": "3.1", "ENGFIB": "2.0"}, food_code="1", name="X", group="DG"
    )
    assert aoac["fiber_g"] == 3.1
    fallback = normalize_cofid_food(
        {"AOACFIB": "N", "ENGFIB": "2.0"}, food_code="2", name="Y", group="DG"
    )
    assert fallback["fiber_g"] == 2.0


def test_normalize_alcoholic_beverages_are_per_100ml():
    beer = normalize_cofid_food(
        {"KCALS": "30"}, food_code="17-506", name="Beer, bitter", group="QA"
    )
    assert beer["base_unit"] == "ml"
    assert beer["base_quantity"] == 100

    food = normalize_cofid_food({"KCALS": "30"}, food_code="1", name="X", group="DG")
    assert food["base_unit"] == "g"


def test_read_workbook(tmp_path):
    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [
            ("13-145", "Ackee, canned", "DG",
             {"KCALS": 151, "PROT": 2.9, "SE": "N", "I": "Tr"}),
            ("17-506", "Beer, bitter", "QA", {"KCALS": 30, "VITK1": "Tr"}),
        ],
    )
    foods = list(read_cofid_workbook(path))
    assert [f["name"] for f in foods] == ["Ackee, canned", "Beer, bitter"]
    assert foods[0]["calories_kcal"] == 151
    assert foods[0]["selenium_ug"] is None
    assert foods[0]["iodine_ug"] == 0.0
    assert foods[1]["base_unit"] == "ml"
    assert foods[1]["vitamin_k_ug"] == 0.0


def test_read_workbook_disambiguates_duplicate_food_codes(tmp_path):
    """CoFID 2021 reuses 13-669 for two foods; both must survive the import."""
    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [
            ("13-669", "Aubergine, roasted", "DG", {"KCALS": 62}),
            ("13-669", "Watercress, raw", "DG", {"KCALS": 10}),
        ],
    )
    foods = list(read_cofid_workbook(path))
    assert [f["source_code"] for f in foods] == ["13-669", "13-669#2"]
    assert [f["calories_kcal"] for f in foods] == [62, 10]


def test_read_workbook_rejects_misaligned_sheets(tmp_path):
    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [("13-145", "Ackee", "DG", {"KCALS": 151}), ("13-146", "Agar", "DG", {"KCALS": 16})],
        misalign_sheet="1.5 Vitamins",
    )
    with pytest.raises(ValueError, match="not aligned"):
        list(read_cofid_workbook(path))


def test_read_workbook_requires_expected_sheets(tmp_path):
    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [("13-145", "Ackee", "DG", {"KCALS": 151})],
        codes={"1.3 Proximates": PROXIMATE_CODES},
    )
    with pytest.raises(ValueError, match="missing the '1.4 Inorganics' sheet"):
        list(read_cofid_workbook(path))


def test_read_workbook_skips_rows_without_a_food(tmp_path):
    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [
            ("13-145", "Ackee", "DG", {"KCALS": 151}),
            ("", "", None, {}),
        ],
    )
    assert len(list(read_cofid_workbook(path))) == 1


def test_import_cofid_end_to_end(tmp_path):
    from app.database import get_connection
    from scripts.import_cofid import import_cofid

    path = _write_workbook(
        tmp_path / "cofid.xlsx",
        [
            ("13-669", "Aubergine, roasted", "DG",
             {"KCALS": 62, "PROT": 2.1, "SE": "N", "I": 3.0}),
            ("13-669", "Watercress, raw", "DG",
             {"KCALS": 10, "VITK1": 315, "SE": "Tr"}),
            ("17-506", "Beer, bitter", "QA", {"KCALS": 30}),
        ],
    )
    db_path = tmp_path / "nutrition.db"
    assert import_cofid(str(path), str(db_path)) == 3

    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT source, source_code, name, calories_kcal, vitamin_k_ug, "
        "selenium_ug, caffeine_mg, base_unit FROM foods ORDER BY source_code"
    ).fetchall()
    counts = conn.execute(
        "SELECT food_count FROM ("
        " SELECT s.code, (SELECT COUNT(*) FROM foods f WHERE f.source = s.code)"
        " AS food_count FROM food_sources s) WHERE code = 'cofid'"
    ).fetchone()
    conn.close()

    assert [r["source_code"] for r in rows] == ["13-669", "13-669#2", "17-506"]
    assert all(r["source"] == "cofid" for r in rows)
    assert rows[1]["vitamin_k_ug"] == 315
    assert rows[1]["selenium_ug"] == 0.0     # Tr -> measured zero
    assert rows[0]["selenium_ug"] is None    # N  -> unknown
    assert rows[0]["caffeine_mg"] is None    # never reported by CoFID
    assert rows[2]["base_unit"] == "ml"
    assert counts["food_count"] == 3


def test_cofid_outranks_label_data_in_search(db):
    from app.repositories.foods import FoodRepository
    from app.services.food_search import FoodSearchService

    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(
        source="open_food_facts", name="Watercress", calories_kcal=10, sugar_g=0.4
    )
    repo.create(source="cofid", name="Watercress", calories_kcal=10, vitamin_k_ug=315)
    results = FoodSearchService(repo).search("watercress")
    assert len(results) == 1
    assert results[0]["source"] == "cofid"
