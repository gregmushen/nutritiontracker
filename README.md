# Nutrition Tracker

A personal nutrition tracking API built with FastAPI and SQLite.

**Live:** https://n.paracosmlab.com — OpenAPI schema at `/openapi.json`

![Nutrition Tracker Service landing page](docs/images/nutrition-tracker-service.png)

## What it does

REST API for logging food, weight, activity, and journal entries. Designed to be called by AI agents or mobile clients.

Key endpoints:
- `GET /foods/search?q=` — full-text search across USDA + OpenFoodFacts + custom foods
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

Download **SR Legacy** and/or **Foundation Foods** JSON from https://fdc.nal.usda.gov/download-datasets, copy to garageband, then:

```bash
bin/import-usda /home/gregmushen/nutrition-data/FoodData_Central_sr_legacy_food_json_2021-10-28.json
bin/import-usda /home/gregmushen/nutrition-data/foundationDownload.json
```

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
  --sr-legacy-json=data/imports/usda/sr-legacy/FoodData_Central_sr_legacy_food_json_2018-04.json
```
