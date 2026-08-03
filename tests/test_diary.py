import pytest
from app.repositories.foods import FoodRepository
from app.repositories.diary import DiaryRepository
from app.services.diary import compute_entry_nutrients


@pytest.fixture
def food_repo(db):
    r = FoodRepository(db)
    r.ensure_fts()
    return r


@pytest.fixture
def diary_repo(db):
    return DiaryRepository(db)


@pytest.fixture
def banana_id(food_repo):
    return food_repo.create(source="custom", name="Banana", calories_kcal=89, protein_g=1.1, carbs_g=22.8, fat_g=0.3)


def test_create_and_get_entry(diary_repo, banana_id):
    entry_id = diary_repo.create(
        user_id=1, date="2026-05-19", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        amount=1, unit="serving", grams=118,
        nutrients_total={"calories_kcal": 105},
    )
    entry = diary_repo.get(entry_id)
    assert entry is not None
    assert entry["meal_type"] == "breakfast"


def test_list_by_date(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-19", meal_type="breakfast",
        food_id=banana_id, food_snapshot={}, amount=1, unit="g", grams=100,
        nutrients_total={},
    )
    diary_repo.create(
        user_id=1, date="2026-05-20", meal_type="lunch",
        food_id=banana_id, food_snapshot={}, amount=1, unit="g", grams=100,
        nutrients_total={},
    )
    entries = diary_repo.list_by_date(user_id=1, date="2026-05-19")
    assert len(entries) == 1


def test_update_entry(diary_repo, banana_id):
    entry_id = diary_repo.create(
        user_id=1, date="2026-05-19", meal_type="breakfast",
        food_id=banana_id, food_snapshot={}, amount=1, unit="g", grams=100,
        nutrients_total={},
    )
    diary_repo.update(entry_id, amount=2, grams=200)
    entry = diary_repo.get(entry_id)
    assert entry["amount"] == 2


def test_delete_entry(diary_repo, banana_id):
    entry_id = diary_repo.create(
        user_id=1, date="2026-05-19", meal_type="breakfast",
        food_id=banana_id, food_snapshot={}, amount=1, unit="g", grams=100,
        nutrients_total={},
    )
    diary_repo.delete(entry_id)
    assert diary_repo.get(entry_id) is None


def test_create_entry_stores_food_name(diary_repo, banana_id):
    entry_id = diary_repo.create(
        user_id=1, date="2026-05-19", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana",
        amount=1, unit="g", grams=100,
        nutrients_total={},
    )
    entry = diary_repo.get(entry_id)
    assert entry["food_name"] == "Banana"


def test_search_by_food_name_returns_matching_entries(diary_repo, food_repo):
    apple_id = food_repo.create(source="custom", name="Apple", calories_kcal=52, protein_g=0.3, carbs_g=14, fat_g=0.2)
    banana_id_local = food_repo.create(source="custom", name="Banana", calories_kcal=89, protein_g=1.1, carbs_g=22.8, fat_g=0.3)
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id_local, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    diary_repo.create(
        user_id=1, date="2026-05-05", meal_type="lunch",
        food_id=apple_id, food_snapshot={"name": "Apple"},
        food_name="Apple", amount=1, unit="g", grams=150, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="Banana")
    assert len(results) == 1
    assert results[0]["food_name"] == "Banana"


def test_search_by_food_name_is_case_insensitive(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="banana")
    assert len(results) == 1
    assert results[0]["food_name"] == "Banana"


def test_search_by_food_name_returns_empty_for_no_match(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="xyz_no_match")
    assert results == []


def test_search_by_food_name_partial_match(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="bana")
    assert len(results) == 1


def test_search_by_food_name_ordered_newest_first(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    diary_repo.create(
        user_id=1, date="2026-05-10", meal_type="lunch",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=200, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="Banana")
    assert results[0]["date"] == "2026-05-10"
    assert results[1]["date"] == "2026-05-01"


def test_search_by_food_name_does_not_return_other_users_entries(diary_repo, banana_id):
    diary_repo.create(
        user_id=1, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    diary_repo.create(
        user_id=2, date="2026-05-01", meal_type="breakfast",
        food_id=banana_id, food_snapshot={"name": "Banana"},
        food_name="Banana", amount=1, unit="g", grams=100, nutrients_total={},
    )
    results = diary_repo.search_by_food_name(user_id=1, query="Banana")
    assert len(results) == 1
    assert results[0]["user_id"] == 1


def test_computed_nutrients_preserve_unknown_and_measured_zero():
    nutrients = compute_entry_nutrients(
        {"protein_g": 0, "vitamin_k_ug": None}, grams=100
    )

    assert nutrients["protein_g"] == 0
    assert nutrients["vitamin_k_ug"] is None
