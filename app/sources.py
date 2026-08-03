"""Registry of food composition data sources.

Every food record carries a ``source`` code that resolves to an entry here, so
the API can report where a nutrient value came from, under what licence it was
published, and how much to trust it relative to a duplicate from another
source.

Tiers order duplicate foods during search (lower wins):

    0  the user's own deliberate data (custom foods, recipes)
    1  research-grade and gap-filled — missing values imputed by documented
       procedures, so a nutrient profile is essentially complete
    2  laboratory-analysed reference data, authoritative but sparse
    3  compiled reference data, no longer maintained
    4  nutrition-label data — only what the manufacturer prints on the package

Adding a new source (CoFID, CNF, Frida, ...) means adding a row here plus a
normalizer in ``app/providers/``; ``foods.source`` is a foreign key onto this
registry, so no schema migration is required.
"""

from typing import Literal, NamedTuple


class FoodSource(NamedTuple):
    code: str
    label: str
    publisher: str
    tier: int
    license: str
    url: str
    citation: str | None = None
    dataset_version: str | None = None


FOOD_SOURCES: tuple[FoodSource, ...] = (
    FoodSource(
        code="custom",
        label="Custom food",
        publisher="User",
        tier=0,
        license="Private to the owning user",
        url="",
    ),
    FoodSource(
        code="recipe",
        label="Recipe",
        publisher="User",
        tier=0,
        license="Private to the owning user",
        url="",
    ),
    FoodSource(
        code="usda_fndds",
        label="USDA Food and Nutrient Database for Dietary Studies (FNDDS)",
        publisher="U.S. Department of Agriculture, Agricultural Research Service",
        tier=1,
        license="Public domain (U.S. Government work)",
        url="https://fdc.nal.usda.gov/",
        citation=(
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "Food and Nutrient Database for Dietary Studies. FoodData Central, "
            "fdc.nal.usda.gov."
        ),
    ),
    FoodSource(
        code="usda_foundation",
        label="USDA FoodData Central Foundation Foods",
        publisher="U.S. Department of Agriculture, Agricultural Research Service",
        tier=2,
        license="Public domain (U.S. Government work)",
        url="https://fdc.nal.usda.gov/food-search?type=Foundation",
        citation=(
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central: Foundation Foods, fdc.nal.usda.gov."
        ),
    ),
    FoodSource(
        code="usda_sr_legacy",
        label="USDA National Nutrient Database for Standard Reference (SR Legacy)",
        publisher="U.S. Department of Agriculture, Agricultural Research Service",
        tier=3,
        license="Public domain (U.S. Government work)",
        url="https://fdc.nal.usda.gov/",
        citation=(
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "National Nutrient Database for Standard Reference, Legacy (2018). "
            "FoodData Central, fdc.nal.usda.gov."
        ),
        dataset_version="SR Legacy (final release, 2018)",
    ),
    FoodSource(
        code="food_data_central",
        label="USDA FoodData Central (unspecified dataset)",
        publisher="U.S. Department of Agriculture, Agricultural Research Service",
        tier=3,
        license="Public domain (U.S. Government work)",
        url="https://fdc.nal.usda.gov/",
        citation=(
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central, fdc.nal.usda.gov."
        ),
        dataset_version="Legacy import — re-import to resolve the exact dataset",
    ),
    FoodSource(
        code="usda_branded",
        label="USDA FoodData Central Branded Foods",
        publisher="U.S. Department of Agriculture / food industry data owners",
        tier=4,
        license="Public domain (U.S. Government work)",
        url="https://fdc.nal.usda.gov/",
        citation=(
            "U.S. Department of Agriculture, Agricultural Research Service. "
            "FoodData Central: Branded Foods, fdc.nal.usda.gov."
        ),
    ),
    FoodSource(
        code="open_food_facts",
        label="Open Food Facts",
        publisher="Open Food Facts contributors",
        tier=4,
        license="Open Database License (ODbL) v1.0; contents under DbCL v1.0",
        url="https://world.openfoodfacts.org/",
        citation=(
            "Open Food Facts contributors. Open Food Facts database, "
            "openfoodfacts.org, made available under the Open Database License."
        ),
    ),
)

SOURCES_BY_CODE: dict[str, FoodSource] = {s.code: s for s in FOOD_SOURCES}

SOURCE_CODES: tuple[str, ...] = tuple(s.code for s in FOOD_SOURCES)

SourceType = Literal[
    "custom",
    "recipe",
    "usda_fndds",
    "usda_foundation",
    "usda_sr_legacy",
    "food_data_central",
    "usda_branded",
    "open_food_facts",
]

# Worse than any registered tier, so an unknown source always sorts last.
UNKNOWN_TIER = 99

# `source=` search filters that expand to a set of underlying source codes.
SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "usda": (
        "usda_fndds",
        "usda_foundation",
        "usda_sr_legacy",
        "usda_branded",
        "food_data_central",
    ),
    # Pre-split imports used `food_data_central` for every USDA dataset, so the
    # old filter value has to keep matching all of them.
    "food_data_central": (
        "usda_fndds",
        "usda_foundation",
        "usda_sr_legacy",
        "usda_branded",
        "food_data_central",
    ),
}


def source_tier(code: str | None) -> int:
    source = SOURCES_BY_CODE.get(code or "")
    return source.tier if source else UNKNOWN_TIER


def resolve_source_filter(source: str | None) -> tuple[str, ...] | None:
    """Expand a `source=` filter into the source codes it should match.

    Returns None when every source should be searched.
    """
    if not source or source == "all":
        return None
    return SOURCE_ALIASES.get(source, (source,))
