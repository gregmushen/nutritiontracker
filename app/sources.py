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
        code="cofid",
        label="McCance and Widdowson's The Composition of Foods Integrated Dataset (CoFID)",
        publisher="Public Health England / Institute of Food Research",
        tier=2,
        license="Open Government Licence v3.0 (Crown copyright)",
        url="https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid",
        citation=(
            "Public Health England. McCance and Widdowson's The Composition of "
            "Foods Integrated Dataset (2021). Contains public sector information "
            "licensed under the Open Government Licence v3.0."
        ),
        dataset_version="CoFID 2021",
    ),
    FoodSource(
        code="cnf",
        label="Canadian Nutrient File (CNF)",
        publisher="Health Canada",
        tier=2,
        license="Open Government Licence - Canada",
        url="https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/canadian-nutrient-file-about-us.html",
        citation=(
            "Health Canada. Canadian Nutrient File, 2026. Contains information "
            "licensed under the Open Government Licence - Canada."
        ),
        dataset_version="CNF 2026",
    ),
    FoodSource(
        code="frida",
        label="Frida — Danish Food Composition Database",
        publisher="National Food Institute, Technical University of Denmark",
        tier=2,
        license="CC BY 4.0",
        url="https://frida.fooddata.dk/",
        citation=(
            "Frida, The Danish Food Composition Database, version 6.1, "
            "National Food Institute, Technical University of Denmark. "
            "https://doi.org/10.11583/DTU.32312844"
        ),
        dataset_version="Frida 6.1",
    ),
    FoodSource(
        code="afcd",
        label="Australian Food Composition Database (AFCD)",
        publisher="Food Standards Australia New Zealand",
        tier=2,
        license="CC BY 4.0",
        url="https://www.foodstandards.gov.au/science-data/food-nutrient-databases",
        citation=(
            "Food Standards Australia New Zealand. Australian Food Composition "
            "Database — Release 3. Licensed under CC BY 4.0."
        ),
        dataset_version="AFCD Release 3",
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
        code="cronometer_custom",
        label="Cronometer custom food",
        publisher="User (via personal Cronometer export)",
        tier=0,
        license="Private to the owning user",
        url="",
    ),
    FoodSource(
        code="nccdb",
        label="Nutrition Coordinating Center Food and Nutrient Database (NCCDB)",
        publisher="University of Minnesota Nutrition Coordinating Center",
        tier=1,
        license=(
            "Proprietary — licensed to Cronometer. Personal export only: "
            "not redistributable and must not be republished or served publicly."
        ),
        url="https://www.ncc.umn.edu/food-and-nutrient-database/",
        citation=(
            "Nutrition Coordinating Center. NCC Food and Nutrient Database, "
            "University of Minnesota. Retrieved via a personal Cronometer export."
        ),
    ),
    FoodSource(
        code="nuttab",
        label="NUTTAB (Australian Food Composition Tables)",
        publisher="Food Standards Australia New Zealand",
        tier=2,
        license="Creative Commons Attribution 3.0 Australia",
        url="https://www.foodstandards.gov.au/science-data/food-composition-databases",
        citation=(
            "Food Standards Australia New Zealand. NUTTAB. Retrieved via a "
            "personal Cronometer export."
        ),
    ),
    FoodSource(
        code="crdb",
        label="Cronometer Restaurant and Branded Foods Database (CRDB)",
        publisher="Cronometer Software Inc.",
        tier=4,
        license=(
            "Proprietary — Cronometer Software Inc. Personal export only: "
            "not redistributable and must not be republished or served publicly."
        ),
        url="https://cronometer.com/",
        citation=(
            "Cronometer Software Inc. Restaurant and branded foods database. "
            "Retrieved via a personal Cronometer export."
        ),
    ),
    FoodSource(
        code="nutritionix",
        label="Nutritionix",
        publisher="Nutritionix (Syndigo)",
        tier=4,
        license=(
            "Proprietary — Nutritionix. Personal export only: not "
            "redistributable and must not be republished or served publicly."
        ),
        url="https://www.nutritionix.com/",
        citation=(
            "Nutritionix branded food database. Retrieved via a personal "
            "Cronometer export."
        ),
    ),
    FoodSource(
        code="cronometer",
        label="Cronometer export",
        publisher="Cronometer Software Inc.",
        tier=4,
        license=(
            "Mixed upstream licences. Personal export only: not redistributable "
            "and must not be republished or served publicly."
        ),
        url="https://cronometer.com/",
        citation=(
            "Personal Cronometer export. Covers foods Cronometer sourced from a "
            "database this system also imports directly, kept separate so the "
            "authoritative row from the full dataset is never overwritten."
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

PRIVATE_SOURCE_CODES = frozenset(
    {
        "custom",
        "recipe",
        "cronometer",
        "cronometer_custom",
        "nccdb",
        "crdb",
        "nutritionix",
        "nuttab",
    }
)

SourceType = Literal[
    "custom",
    "recipe",
    "cronometer_custom",
    "usda_fndds",
    "nccdb",
    "usda_foundation",
    "cofid",
    "cnf",
    "frida",
    "afcd",
    "nuttab",
    "usda_sr_legacy",
    "food_data_central",
    "usda_branded",
    "open_food_facts",
    "crdb",
    "nutritionix",
    "cronometer",
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
    # Everything that reached us through a personal Cronometer export, whatever
    # database Cronometer itself sourced it from.
    "cronometer": (
        "cronometer",
        "cronometer_custom",
        "nccdb",
        "crdb",
        "nutritionix",
        "nuttab",
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
