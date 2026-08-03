# Nutrition Tracker

A personal nutrition tracking API built with FastAPI and SQLite.

**Live:** https://n.paracosmlab.com — OpenAPI schema at `/openapi.json`

![Nutrition Tracker Service landing page](docs/images/nutrition-tracker-service.png)

## What it does

REST API for logging food, weight, activity, and journal entries. Designed to be called by AI agents or mobile clients.

Key endpoints:
- `GET /foods/search?q=` — full-text search across USDA + OpenFoodFacts + custom foods
- `GET /foods/sources` — data sources behind the catalog, with licence, citation and quality tier
- `GET /foods/barcode/{barcode}` — barcode lookup; caches a matching live Open Food Facts product on a local miss
- `POST /diary/{date}/entries` — log what you ate
- `GET /stats/daily/{date}` — daily nutrition totals with meal breakdown
- `POST /weight` — log body weight
- `POST /recipes` — build recipes with auto-computed nutrition math
- `POST /imports/activity/steps` — import step count data
- `POST /kitchen/inventory` — remember what you have, use soon, maybe have, are out of, or treat as a staple
- `POST /kitchen/matches` — rank favorite meals from current kitchen inventory
- `POST /kitchen/shopping-list/generate` — generate grocery items from selected favorite meals

All endpoints (except `/health`) require `Authorization: Bearer <token>`.

## Users

Single-user mode is the default. Under the hood it uses one **Default user**
for all personal records, so existing deployments need no user configuration.

Enable multi-user mode only when separate personal data is needed:

```bash
NT_MULTI_USER_ENABLED=true
```

With multi-user mode enabled, the configured `NT_BEARER_TOKEN` is the admin
and default-user token. Use it to create a separate bearer token for each
additional user:

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "Authorization: Bearer $NT_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Second user"}'
```

The response includes the new token once. Each user token scopes diary, recipes,
weight, journal, activity, kitchen, shopping lists, and custom foods to that
user. USDA and Open Food Facts catalog foods remain shared.

## Stack

- Python 3.12, FastAPI, SQLite (WAL mode)
- Deployed via Kamal 2 to a local server, exposed through a Cloudflare tunnel
- CI: Woodpecker (lint → secret-scan → test → deploy)

## Docs

- [Docs index](docs/index.html)
- [Printing Press API-to-Agent Workflow](docs/superpowers/specs/2026-05-25-printing-press-api-to-agent-workflow-design.md)
- [Companion Hermes skill draft](docs/hermes/skills/printing-press-api-to-agent-workflow/SKILL.md)

## Local development

```bash
pip install -e ".[dev]"
pytest tests/
```

## Data import

The app ships with no food data. Seed it from USDA and OpenFoodFacts.

### USDA FoodData Central

Download **Survey (FNDDS)**, **SR Legacy** and/or **Foundation Foods** JSON from
https://fdc.nal.usda.gov/download-datasets, copy to garageband, then:

```bash
bin/import-usda /home/gregmushen/nutrition-data/FoodData_Central_survey_food_json_2021-2023.json
bin/import-usda /home/gregmushen/nutrition-data/FoodData_Central_sr_legacy_food_json_2021-10-28.json
bin/import-usda /home/gregmushen/nutrition-data/foundationDownload.json
```

The importer detects the dataset from the export and tags each food with its
specific source (`usda_fndds`, `usda_foundation`, `usda_sr_legacy`,
`usda_branded`); pass `--source=<code>` to override.

**Prefer FNDDS** for generic foods: USDA fills its gaps with documented
imputation, so entries carry a complete nutrient profile instead of the zeros
SR Legacy leaves behind for unassayed nutrients. It also ships household
portions ("1 cup"), which are imported as serving sizes.

For Foundation Foods, also extract the matching CSV archive and pass its
directory as a fallback. Records omitted or invalid in the JSON export are
reconstructed from `food.csv`, `foundation_food.csv`, and `food_nutrient.csv`:

```bash
bin/import-usda /home/gregmushen/nutrition-data/foundationDownload.json \
  --csv-dir=/home/gregmushen/nutrition-data/foundation-food-csv
```

### OpenFoodFacts (US products)

Download the full compressed JSONL (~12 GB) once:

```bash
ssh gregmushen@192.168.60.55 \
  "wget -q -O /home/gregmushen/nutrition-data/openfoodfacts-products.jsonl.gz \
   'https://openfoodfacts-ds.s3.eu-west-3.amazonaws.com/openfoodfacts-products.jsonl.gz'"
```

Then import US products only (streams through the gzip — no decompression to disk needed):

```bash
bin/import-off /home/gregmushen/nutrition-data/openfoodfacts-products.jsonl.gz \
  --country=en:united-states
```

Both scripts auto-detect the current running container image. Re-running an import is safe — records are upserted by `(source, source_code)`.

## Data sources

Every food records which dataset it came from. `GET /foods/sources` returns the
registry — publisher, licence, required citation, dataset version, food count,
and a quality `tier` used to rank duplicates during search (lower is better):

| Tier | Sources | What it means |
| --- | --- | --- |
| 0 | `custom`, `recipe` | Your own deliberate entries — always win |
| 1 | `usda_fndds` | Gap-filled: USDA imputes missing values by documented procedures, so profiles are essentially complete |
| 2 | `usda_foundation`, `cofid`, `cnf`, `frida`, `afcd` | Lab-analysed, authoritative but sparse |
| 3 | `usda_sr_legacy`, `food_data_central` | Compiled reference data, no longer maintained |
| 4 | `usda_branded`, `open_food_facts` | Nutrition-label data — only what the manufacturer prints |

`/foods/search?source=` accepts any code above, `all`, or `usda` for every USDA
dataset. `food_data_central` is kept as an alias matching all USDA datasets so
pre-split clients keep working.

Registering a new source (CNF, Frida, ...) means adding an entry to
`app/sources.py` and a normalizer in `app/providers/` — `foods.source` is a
foreign key onto the registry, so no schema migration is needed.

Attribution note: Open Food Facts data is licensed under the
[ODbL](https://opendatacommons.org/licenses/odbl/1-0/) and requires attribution;
the citation text is in `GET /foods/sources`.

### CoFID (UK)

McCance and Widdowson's Composition of Foods Integrated Dataset — 2,887 UK foods
from Public Health England, under the Open Government Licence v3.0. Download
[the 2021 workbook](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid)
and import it:

```bash
pip install -e ".[data-import]"    # needs openpyxl
python -m scripts.import_cofid ~/Downloads/cofid_2021.xlsx
```

CoFID distinguishes "not measured" (`N`) from "trace" (`Tr`), which map to `null`
and `0` respectively. Alcoholic drinks are published per 100 ml, so those foods
are stored with `base_unit = "ml"`.

### CNF (Canada)

The Canadian Nutrient File — 5,993 foods from Health Canada, under the Open
Government Licence - Canada. Download and unpack
[the CSV bundle](https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109),
then import the directory:

```bash
python -m scripts.import_cnf ~/Downloads/cnf-fcen-csv
```

CNF stores one row per measurement, so a nutrient a food was never assayed for
has no row and is imported as `null`. It does not measure iodine, chromium, or
added sugar at all. Imports verify each nutrient's published unit and fail
rather than silently rescaling if a future release changes one.

### Frida (Denmark)

The Danish Food Composition Database — 1,390 foods from DTU's National Food
Institute, under CC BY 4.0. Download `FCDB_<version>_Dataset.xlsx` from
[the DTU dataset record](https://doi.org/10.11583/DTU.32312844):

```bash
python -m scripts.import_frida ~/Downloads/FCDB_6.1_Dataset.xlsx
```

Frida has the widest nutrient coverage of the non-USDA sources here, including
choline, chromium, iodine, and vitamin K. It reports no folic acid.

### AFCD (Australia)

The Australian Food Composition Database — 1,588 foods from Food Standards
Australia New Zealand, under CC BY 4.0. Download "AFCD Release 3 - Nutrient
profiles.xlsx" from
[the FSANZ database page](https://www.foodstandards.gov.au/science-data/food-nutrient-databases):

```bash
python -m scripts.import_afcd ~/Downloads/afcd-release-3-nutrient-profiles.xlsx
```

AFCD publishes energy in kilojoules (converted on import) and fatty acid totals
both as a share of total fat and as grams — only the gram columns are read.
Its trans fat column is in milligrams while the rest are grams, so that one is
scaled. It reports no vitamin K or choline. Only the per-100 g sheet is
imported; the per-100 mL sheet re-states 213 foods that are already on it.

### `null` vs `0`

A nutrient is `null` when the source does not report it and `0` when it was
measured as zero. These used to be indistinguishable — every unreported value
was stored as `0`, so USDA spinach with no vitamin K assay looked identical to a
food that genuinely contains none. Treat `null` as "unknown", not "none".

Databases seeded before this change still hold placeholder zeros; re-import the
affected dataset to replace them with `null`.

## Nutrients

Foods track macronutrients plus added sugar, fat subtypes, cholesterol, caffeine,
minerals, trace minerals, and vitamins A, C, D, E, K, and B-complex nutrients.
USDA and Open Food Facts imports normalize each source's units to the API's
per-100 g fields.

To rebuild a new database from the local USDA export and Open Food Facts dump:

```bash
python -m scripts.rebuild_food_database data/nutrition-enriched.db \
  data/imports/openfoodfacts/food.parquet \
  --foundation-json=data/imports/usda/foundation/FoodData_Central_foundation_food_json_2026-04-30.json \
  --foundation-csv-dir=data/imports/usda/foundation-csv/FoodData_Central_foundation_food_csv_2026-04-30 \
  --sr-legacy-json=data/imports/usda/sr-legacy/FoodData_Central_sr_legacy_food_json_2018-04.json \
  --fndds-json=data/imports/usda/survey/FoodData_Central_survey_food_json_2021-2023.json
```
