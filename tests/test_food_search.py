import pytest

from app.repositories.foods import FoodRepository
from app.services.food_search import FoodSearchService


def test_dedup_by_barcode(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Banana", barcode="123", calories_kcal=89, protein_g=1.1)
    repo.create(source="food_data_central", name="Banana, raw", barcode="123", calories_kcal=89, protein_g=1.1, fiber_g=2.6)
    svc = FoodSearchService(repo)
    results = svc.search("banana")
    # Should deduplicate — prefer FDC because it has more nutrient data (fiber_g)
    assert len(results) == 1
    assert results[0]["fiber_g"] == 2.6


def test_dedup_by_name(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Chicken Breast", calories_kcal=165)
    repo.create(source="food_data_central", name="Chicken Breast", calories_kcal=165, protein_g=31)
    svc = FoodSearchService(repo)
    results = svc.search("chicken breast")
    assert len(results) == 1


def test_no_dedup_different_foods(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Banana")
    repo.create(source="food_data_central", name="Banana Chips")
    svc = FoodSearchService(repo)
    results = svc.search("banana")
    assert len(results) == 2


def test_tier_wins_when_relevance_ties(db):
    """The açaí case: identical names, so bm25 ties and tier must decide.

    Both foods report the same number of nutrients, so nothing but source tier
    can separate them.
    """
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(
        source="open_food_facts", name="Berry Acai", calories_kcal=17, vitamin_e_mg=0.0
    )
    repo.create(
        source="nccdb", name="Acai Berry", calories_kcal=61, vitamin_e_mg=14.8
    )
    results = FoodSearchService(repo).search("acai berry")
    assert results[0]["source"] == "nccdb"
    assert results[0]["vitamin_e_mg"] == 14.8


def test_tier_overcomes_a_terser_label_name(db):
    """bm25 rewards short documents, which label data supplies far more of."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Butterfinger", calories_kcal=464)
    repo.create(source="usda_fndds", name="Butter, stick, salted", calories_kcal=717)
    results = FoodSearchService(repo).search("butter")
    assert results[0]["name"] == "Butter, stick, salted"


def test_exact_brand_match_still_wins(db):
    """Tier must not be so strong that a branded search stops working."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Doritos Nacho Cheese")
    repo.create(source="usda_fndds", name="Corn chips, nacho cheese flavored")
    results = FoodSearchService(repo).search("doritos")
    assert results[0]["name"] == "Doritos Nacho Cheese"


def test_reference_foods_are_retrieved_past_a_wall_of_label_data(db):
    """Reference sources get their own retrieval pass.

    Label data outnumbers reference data ~50:1 in the real catalogue, so a
    single relevance-ordered window fills with branded rows and the reference
    food is never a candidate at all.
    """
    repo = FoodRepository(db)
    repo.ensure_fts()
    for i in range(300):
        repo.create(source="open_food_facts", name=f"Salmon Snack {i}")
    repo.create(source="usda_fndds", name="Fish, salmon, sockeye, cooked", protein_g=25)
    results = FoodSearchService(repo).search("salmon", limit=5)
    assert results[0]["source"] == "usda_fndds"


def test_relevance_score_does_not_leak_into_results(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="open_food_facts", name="Banana")
    results = FoodSearchService(repo).search("banana")
    assert "relevance" not in results[0]


def test_paging_is_applied_after_dedup(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    for i in range(10):
        repo.create(source="open_food_facts", name=f"Oat Bar {i}")
    svc = FoodSearchService(repo)
    first = svc.search("oat bar", limit=4, offset=0)
    second = svc.search("oat bar", limit=4, offset=4)
    assert len(first) == len(second) == 4
    assert {f["id"] for f in first}.isdisjoint({f["id"] for f in second})


def test_source_filter_still_restricts_results(db):
    """The extra reference pass must not smuggle in filtered-out sources."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    repo.create(source="usda_fndds", name="Yogurt, greek, plain")
    repo.create(source="open_food_facts", name="Greek Yogurt")
    results = FoodSearchService(repo).search("yogurt", source="open_food_facts")
    assert [f["source"] for f in results] == ["open_food_facts"]


def test_paging_reaches_past_the_candidate_ceiling(db, monkeypatch):
    """A deep page must not come back empty while matches remain.

    The candidate window used to be capped at a fixed ceiling, so `offset`
    beyond it sliced past the end of the retrieved list and reported no
    results even though thousands of foods still matched.
    """
    repo = FoodRepository(db)
    repo.ensure_fts()
    for i in range(1200):
        repo.create(source="open_food_facts", name=f"Apple item {i}",
                    source_code=f"b{i}", calories_kcal=46)
    svc = FoodSearchService(repo)
    batch_sizes = []
    search = repo.search

    def recording_search(*args, **kwargs):
        batch_sizes.append(kwargs["limit"])
        return search(*args, **kwargs)

    monkeypatch.setattr(repo, "search", recording_search)

    assert len(svc.search("apple", limit=20, offset=1100)) == 20
    assert svc.search("apple", limit=20, offset=1200) == []
    assert max(batch_sizes) == 20


def test_paging_does_not_repeat_or_skip_foods(db):
    """Walking the pages must yield every distinct food exactly once."""
    repo = FoodRepository(db)
    repo.ensure_fts()
    for i in range(150):
        repo.create(source="open_food_facts", name="Apple Juice",
                    source_code=f"d{i}", calories_kcal=46)
    for i in range(45):
        repo.create(source="usda_fndds", name=f"Apple variety {i}",
                    source_code=f"v{i}", calories_kcal=52)
    svc = FoodSearchService(repo)

    seen: list[int] = []
    for offset in range(0, 60, 20):
        seen += [food["id"] for food in svc.search("apple", limit=20, offset=offset)]

    # 45 distinct varieties plus the one surviving "Apple Juice" duplicate.
    assert len(seen) == len(set(seen))
    assert len(seen) == 46


def test_tier_adjustment_happens_before_candidate_truncation(db):
    repo = FoodRepository(db)
    repo.ensure_fts()
    for i in range(600):
        repo.create(
            source="open_food_facts",
            source_code=f"label-{i}",
            name="Spinach",
            calories_kcal=23,
        )
    repo.create(
        source="usda_fndds",
        source_code="reference",
        name="Spinach",
        calories_kcal=23,
        vitamin_k_ug=482.9,
    )

    results = FoodSearchService(repo).search("spinach", limit=5)

    assert len(results) == 1
    assert results[0]["source"] == "usda_fndds"


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (20, -1), (20, 10_001)],
)
def test_search_rejects_unbounded_pagination(db, limit, offset):
    repo = FoodRepository(db)
    repo.ensure_fts()

    with pytest.raises(ValueError, match="must be between"):
        FoodSearchService(repo).search("apple", limit=limit, offset=offset)
