from app.repositories.foods import FoodRepository
from app.models.food import NutrientsPer100

NUTRIENT_FIELDS = list(NutrientsPer100.model_fields.keys())


def _nutrient_completeness(food: dict) -> int:
    return sum(1 for f in NUTRIENT_FIELDS if (food.get(f) or 0) > 0)


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().strip().split())


class FoodSearchService:
    def __init__(self, repo: FoodRepository):
        self.repo = repo

    def search(
        self, query: str, *, source: str | None = None, user_id: int | None = None,
        limit: int = 20, offset: int = 0,
    ) -> list[dict]:
        # Fetch extra results to allow for dedup shrinkage
        raw = self.repo.search(
            query, source=source, user_id=user_id, limit=limit * 2, offset=offset
        )
        deduped = self._deduplicate(raw)
        return deduped[:limit]

    def _deduplicate(self, foods: list[dict]) -> list[dict]:
        seen_barcodes: dict[str, int] = {}
        seen_names: dict[str, int] = {}
        result: list[dict] = []

        for food in foods:
            barcode = food.get("barcode")
            norm_name = _normalize_name(food.get("name", ""))
            dup_idx = None

            if barcode and barcode in seen_barcodes:
                dup_idx = seen_barcodes[barcode]
            elif norm_name in seen_names:
                dup_idx = seen_names[norm_name]

            if dup_idx is not None:
                existing = result[dup_idx]
                if _nutrient_completeness(food) > _nutrient_completeness(existing):
                    result[dup_idx] = food
                continue

            idx = len(result)
            if barcode:
                seen_barcodes[barcode] = idx
            seen_names[norm_name] = idx
            result.append(food)

        return result
