from app.repositories.foods import FoodRepository
from app.sources import FOOD_SOURCES, resolve_source_filter

SOURCE_TIER_WEIGHT = 2.0
MAX_SEARCH_LIMIT = 100
MAX_SEARCH_OFFSET = 10_000

# Cap the ranking penalty so an unregistered source remains reachable.
MAX_RANKING_TIER = max(source.tier for source in FOOD_SOURCES) + 1


class FoodSearchService:
    def __init__(self, repo: FoodRepository):
        self.repo = repo

    def search(
        self,
        query: str,
        *,
        source: str | None = None,
        user_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
        if not 0 <= offset <= MAX_SEARCH_OFFSET:
            raise ValueError(f"offset must be between 0 and {MAX_SEARCH_OFFSET}")

        page = self.repo.search(
            query,
            sources=resolve_source_filter(source),
            user_id=user_id,
            limit=limit,
            offset=offset,
            quality_weight=SOURCE_TIER_WEIGHT,
            max_quality_tier=MAX_RANKING_TIER,
        )
        for food in page:
            food.pop("relevance", None)
        return page
