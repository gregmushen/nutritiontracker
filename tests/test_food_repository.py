import pytest

from app.repositories.foods import FoodRepository


@pytest.fixture
def repo(db):
    r = FoodRepository(db)
    r.ensure_fts()
    return r


def test_create_and_get(repo):
    food_id = repo.create(
        source="custom", name="Banana", calories_kcal=89, protein_g=1.1,
        carbs_g=22.8, fat_g=0.3,
    )
    food = repo.get(food_id)
    assert food["name"] == "Banana"
    assert food["calories_kcal"] == 89


def test_get_nonexistent_returns_none(repo):
    assert repo.get(9999) is None


def test_search_by_name(repo):
    repo.create(source="custom", name="Chicken Breast Grilled")
    repo.create(source="custom", name="Chicken Thigh")
    repo.create(source="custom", name="Banana")
    results = repo.search("chicken")
    assert len(results) == 2


def test_search_prefix(repo):
    repo.create(source="custom", name="Broccoli")
    results = repo.search("broc")
    assert len(results) == 1
    assert results[0]["name"] == "Broccoli"


def test_search_with_source_filter(repo):
    repo.create(source="open_food_facts", name="Oats OFF")
    repo.create(source="usda_sr_legacy", name="Oats USDA")
    results = repo.search("oats", sources=("usda_sr_legacy",))
    assert len(results) == 1
    assert results[0]["name"] == "Oats USDA"


def test_search_with_multiple_source_filter(repo):
    repo.create(source="open_food_facts", name="Oats OFF")
    repo.create(source="usda_sr_legacy", name="Oats SR")
    repo.create(source="usda_fndds", name="Oats FNDDS")
    results = repo.search("oats", sources=("usda_sr_legacy", "usda_fndds"))
    assert {r["name"] for r in results} == {"Oats SR", "Oats FNDDS"}


def test_search_limit_offset(repo):
    for i in range(10):
        repo.create(source="custom", name=f"Apple Variety {i}")
    results = repo.search("apple", limit=3, offset=0)
    assert len(results) == 3
    results2 = repo.search("apple", limit=3, offset=3)
    assert len(results2) == 3
    assert results[0]["id"] != results2[0]["id"]


def test_barcode_lookup(repo):
    repo.create(source="open_food_facts", name="Granola Bar", barcode="1234567890")
    food = repo.get_by_barcode("1234567890")
    assert food["name"] == "Granola Bar"


def test_update_food(repo):
    food_id = repo.create(source="custom", name="Old Name")
    repo.update(food_id, name="New Name", protein_g=25)
    food = repo.get(food_id)
    assert food["name"] == "New Name"
    assert food["protein_g"] == 25


def test_delete_food(repo):
    food_id = repo.create(source="custom", name="To Delete")
    repo.delete(food_id)
    assert repo.get(food_id) is None


def test_bulk_upsert_preserves_referenced_food_id(repo, db):
    food_id = repo.create(
        source="food_data_central",
        source_code="123",
        name="Original Name",
    )
    db.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "2026-07-26",
            "snack",
            food_id,
            "{}",
            "Original Name",
            1,
            "serving",
            100,
            "{}",
        ),
    )
    db.commit()

    upserted_id = repo.create_no_commit(
        source="food_data_central",
        source_code="123",
        name="Updated Name",
    )
    db.commit()

    assert upserted_id == food_id
    assert repo.get(food_id)["name"] == "Updated Name"


@pytest.mark.parametrize(
    "query",
    [
        "ben & jerry",       # fts5: syntax error near "&"
        "ac/dc energy",      # fts5: syntax error near "/"
        "milk 2%",           # fts5: syntax error near "%"
        "salt (fine)",       # fts5: syntax error near "("
        "yoghurt-greek",     # no such column: greek
        "cola AND milk",     # AND parsed as an operator
        "cheese: aged",      # no such column: cheese
        "*",                 # unknown special query
        'say "hi"',
        "^caret",
        "a NEAR b",
        "&&&",
        "",
        "   ",
        "test\x00test",      # fts5: unterminated string — NUL truncates the literal
        "\x00",
    ],
)
def test_search_never_raises_on_punctuation(db, query):
    """Users type punctuation; it must not become FTS5 syntax."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    assert isinstance(repo.search(query), list)


def test_punctuated_names_are_findable(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Ben & Jerry's Chocolate Fudge")
    repo.create(source="open_food_facts", name="Milk 2% Fat")
    assert repo.search("ben & jerry")[0]["name"].startswith("Ben & Jerry")
    assert repo.search("milk 2%")[0]["name"] == "Milk 2% Fat"


def test_prefix_matching_still_works(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Chicken Breast")
    assert repo.search("chick brea")[0]["name"] == "Chicken Breast"


def test_blank_query_returns_nothing(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Chicken Breast")
    assert repo.search("   ") == []
