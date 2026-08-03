from app.repositories.foods import FoodRepository
from app.repositories.diary import DiaryRepository
from app.services.diary import compute_entry_nutrients, build_food_snapshot


def _seed_entries(db):
    food_repo = FoodRepository(db)
    food_repo.ensure_fts()
    fid = food_repo.create(
        source="custom", name="Banana", calories_kcal=89,
        protein_g=1.1, carbs_g=22.8, fat_g=0.3,
    )
    food = food_repo.get(fid)

    diary = DiaryRepository(db)
    for meal in ["breakfast", "lunch"]:
        nutrients = compute_entry_nutrients(food, 100)
        diary.create(
            user_id=1, date="2026-05-19", meal_type=meal,
            food_id=fid, food_snapshot=build_food_snapshot(food),
            amount=100, unit="g", grams=100,
            nutrients_total=nutrients,
        )
    return fid


def test_daily_stats(client, db):
    _seed_entries(db)
    r = client.get("/stats/daily/2026-05-19")
    assert r.status_code == 200
    data = r.json()
    assert data["date"] == "2026-05-19"
    assert data["entry_count"] == 2
    assert data["total"]["calories_kcal"] == 178
    assert data["meals"]["breakfast"]["calories_kcal"] == 89
    assert data["meals"]["lunch"]["calories_kcal"] == 89
    assert data["meals"]["dinner"]["calories_kcal"] == 0
    assert data["total"]["vitamin_k_ug"] is None
    assert data["meals"]["dinner"]["vitamin_k_ug"] == 0


def test_daily_stats_empty(client, db):
    r = client.get("/stats/daily/2026-05-19")
    assert r.status_code == 200
    assert r.json()["entry_count"] == 0
    assert r.json()["total"]["calories_kcal"] == 0


def test_range_stats(client, db):
    _seed_entries(db)
    r = client.get("/stats/range?start=2026-05-18&end=2026-05-20")
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 1
    assert days[0]["date"] == "2026-05-19"
