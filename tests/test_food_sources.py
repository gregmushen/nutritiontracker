import sqlite3

import pytest

from app.repositories.foods import FoodRepository
from app.services.food_search import FoodSearchService
from app.sources import (
    FOOD_SOURCES,
    SOURCES_BY_CODE,
    UNKNOWN_TIER,
    resolve_source_filter,
    source_tier,
)


def test_every_source_declares_a_licence():
    for source in FOOD_SOURCES:
        assert source.label and source.publisher and source.license


def test_registry_is_seeded_into_the_database(db):
    rows = db.execute("SELECT code FROM food_sources").fetchall()
    assert {r["code"] for r in rows} == set(SOURCES_BY_CODE)


def test_source_is_a_foreign_key(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        repo.create(source="not_a_real_source", name="Bogus")


def test_tier_ordering_prefers_gap_filled_data():
    assert source_tier("custom") < source_tier("usda_fndds")
    assert source_tier("usda_fndds") < source_tier("usda_foundation")
    assert source_tier("usda_foundation") < source_tier("usda_sr_legacy")
    assert source_tier("usda_sr_legacy") < source_tier("open_food_facts")
    assert source_tier("nonsense") == UNKNOWN_TIER


def test_resolve_source_filter():
    assert resolve_source_filter(None) is None
    assert resolve_source_filter("all") is None
    assert resolve_source_filter("custom") == ("custom",)
    assert "usda_fndds" in resolve_source_filter("usda")
    # The pre-split filter value still matches every USDA dataset.
    assert "usda_sr_legacy" in resolve_source_filter("food_data_central")


def test_search_source_alias_matches_split_usda_datasets(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="usda_fndds", name="Rice FNDDS")
    repo.create(source="usda_sr_legacy", name="Rice SR")
    repo.create(source="open_food_facts", name="Rice OFF")
    svc = FoodSearchService(repo)
    results = svc.search("rice", source="usda")
    assert {r["name"] for r in results} == {"Rice FNDDS", "Rice SR"}


def test_dedup_prefers_higher_tier_over_raw_nutrient_count(db):
    """A label listing more numbers must not beat a research-grade profile."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(
        source="open_food_facts", name="Spinach", barcode="55",
        calories_kcal=23, protein_g=2.9, carbs_g=3.6, fat_g=0.4, sugar_g=0.4,
        fiber_g=2.2, sodium_mg=79,
    )
    repo.create(
        source="usda_fndds", name="Spinach", barcode="55",
        calories_kcal=23, protein_g=2.9, vitamin_k_ug=482.9,
    )
    svc = FoodSearchService(repo)
    results = svc.search("spinach")
    assert len(results) == 1
    assert results[0]["source"] == "usda_fndds"
    assert results[0]["vitamin_k_ug"] == 482.9


def test_dedup_falls_back_to_completeness_within_a_tier(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Yoghurt", barcode="77", calories_kcal=59)
    repo.create(
        source="open_food_facts", name="Yoghurt Plain", barcode="77",
        calories_kcal=59, protein_g=10, calcium_mg=110,
    )
    svc = FoodSearchService(repo)
    results = svc.search("yoghurt")
    assert len(results) == 1
    assert results[0]["protein_g"] == 10


def test_unknown_nutrient_stays_null_through_the_repository(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    food_id = repo.create(source="custom", name="Mystery", calories_kcal=100)
    food = repo.get(food_id)
    assert food["calories_kcal"] == 100
    assert food["vitamin_k_ug"] is None


def test_sources_endpoint_reports_licences_and_counts(client):
    resp = client.post(
        "/foods",
        json={"source": "custom", "name": "Test food", "nutrients": {"protein_g": 5}},
    )
    assert resp.status_code == 201

    resp = client.get("/foods/sources")
    assert resp.status_code == 200
    sources = {s["code"]: s for s in resp.json()}

    assert sources["custom"]["food_count"] == 1
    assert sources["usda_fndds"]["tier"] == 1
    assert "Public domain" in sources["usda_fndds"]["license"]
    assert "Open Database License" in sources["open_food_facts"]["license"]
    assert sources["open_food_facts"]["citation"]
    # Sorted best-quality first.
    tiers = [s["tier"] for s in resp.json()]
    assert tiers == sorted(tiers)


def test_custom_food_reports_unknown_nutrients_as_null(client):
    resp = client.post(
        "/foods",
        json={
            "source": "custom",
            "name": "Olive oil",
            "nutrients": {"fat_g": 100, "protein_g": 0},
        },
    )
    body = resp.json()
    assert body["fat_g"] == 100
    assert body["protein_g"] == 0
    assert body["vitamin_k_ug"] is None


def test_registered_legacy_source_can_be_returned(client, db):
    db.execute(
        """INSERT INTO food_sources
           (code, label, publisher, tier, license)
           VALUES ('legacy_private', 'Legacy', 'Unknown', 99, 'Unknown')"""
    )
    food_id = db.execute(
        "INSERT INTO foods (source, name) VALUES ('legacy_private', 'Old food')"
    ).lastrowid
    db.commit()

    response = client.get(f"/foods/{food_id}")

    assert response.status_code == 200
    assert response.json()["source"] == "legacy_private"
