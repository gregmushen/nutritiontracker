# Nutrition Tracker — Live Smoke Test Plan

**Base URL:** `$NT_PUBLIC_URL` — set it before running anything below:

```bash
export NT_PUBLIC_URL=https://nutrition.example.com
```

If you use `deploy/deploy.env`, `NT_PUBLIC_URL` is already defined there.  
**Auth:** `Authorization: Bearer <NT_BEARER_TOKEN>`

---

## 1. Health (unauthenticated)

Verifies the app is running and `/health` is publicly accessible.

```bash
curl -s "$NT_PUBLIC_URL/health"
```

**Expected:** `{"status":"ok","version":"0.1.0"}`

---

## 2. Auth enforcement

Verifies protected endpoints reject unauthenticated requests.

```bash
curl -s -o /dev/null -w "%{http_code}" "$NT_PUBLIC_URL/foods/search?q=chicken"
```

**Expected:** `401`

---

## 3. Foods — create a custom food

Diary, recipes, and stats all require `food_id`. Since USDA/OpenFoodFacts data isn't seeded yet, we create a custom food first.

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Apple",
    "base_quantity": 100,
    "base_unit": "g",
    "nutrients": {
      "calories_kcal": 52,
      "protein_g": 0.3,
      "carbs_g": 14,
      "fat_g": 0.2
    }
  }' \
  "$NT_PUBLIC_URL/foods"
```

**Expected:** Returns `FoodOut` with an `id` field. Capture this ID for subsequent tests.

---

## 4. Foods search

Verifies full-text search finds the food we just created.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/foods/search?q=apple&limit=5"
```

**Expected:** JSON array containing the Test Apple entry.

---

## 5. Diary — log entry and retrieve

Uses the `food_id` from step 3. `amount` and `unit` refer to the quantity eaten.

```bash
# POST entry
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"food_id": <ID>, "amount": 150, "unit": "g", "meal_type": "snack"}' \
  "$NT_PUBLIC_URL/diary/2026-05-19/entries"

# GET entries for the day
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/diary/2026-05-19"
```

**Expected:** POST returns `DiaryEntry` with `id`. GET returns array containing it.

---

## 6. Stats — daily totals

Verifies nutrition rollup for the diary entries logged above.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/stats/daily/2026-05-19"
```

**Expected:** `DailyStats` with non-zero `calories`, `protein_g`, `carbs_g`, `fat_g`.

---

## 7. Weight — log and retrieve

```bash
# POST
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-05-19", "weight_kg": 80.5, "notes": "morning"}' \
  "$NT_PUBLIC_URL/weight"

# GET range
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/weight?start=2026-05-19&end=2026-05-19"
```

**Expected:** POST returns `WeightEntry` with `id`. GET returns array containing it.

---

## 8. Journal — create with scores and retrieve

```bash
# POST
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-05-19",
    "body": "Felt good today, ate well.",
    "mood_score": 8,
    "stress_score": 3,
    "sleep_quality": 7,
    "tags": ["test"]
  }' \
  "$NT_PUBLIC_URL/journal"

# GET by date
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/journal/2026-05-19"
```

**Expected:** POST returns `JournalEntry` with `id` and all scores. GET returns same entry.

---

## 9. Steps / Activity — import and retrieve

Verifies step count sync and cumulative-day logic. A second import with a lower count should set `anomaly_flag: true`.

```bash
# First import
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "observed_at": "2026-05-19T12:00:00",
    "period_start": "2026-05-19T00:00:00",
    "period_end": "2026-05-19T12:00:00",
    "steps_total_today": 6500,
    "timezone": "America/Los_Angeles"
  }' \
  "$NT_PUBLIC_URL/imports/activity/steps"

# Second import — lower count should trigger anomaly
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "observed_at": "2026-05-19T13:00:00",
    "period_start": "2026-05-19T00:00:00",
    "period_end": "2026-05-19T13:00:00",
    "steps_total_today": 3000,
    "timezone": "America/Los_Angeles"
  }' \
  "$NT_PUBLIC_URL/imports/activity/steps"

# GET today's summary
curl -s -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/activity/daily/2026-05-19"
```

**Expected:**
- Both POSTs return `{"status": "ok"}`.
- GET returns `steps: 6500` (anomaly preserved original count) and `anomaly_flag: true`.

---

## 10. Recipes — create with ingredients

Uses `food_id` from step 3. Verifies nutrition math.

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Snack",
    "servings": 1,
    "total_weight_g": 200,
    "ingredients": [
      {"food_id": <ID>, "amount": 200, "unit": "g"}
    ]
  }' \
  "$NT_PUBLIC_URL/recipes"
```

**Expected:** Returns `Recipe` with computed `total_calories: 104` (52 kcal/100g × 200g).

---

## 11. OpenAPI schema accessible

Verifies the schema endpoint is live (useful for AI agents).

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "$NT_PUBLIC_URL/openapi.json"
```

**Expected:** `200`

---

## 12. Kitchen Memory — inventory, matches, shopping list

Create inventory:

```bash
curl -s -X POST "$NT_PUBLIC_URL/kitchen/inventory" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Eggs","status":"have","location":"fridge"}'
```

Create a favorite meal:

```bash
curl -s -X POST "$NT_PUBLIC_URL/kitchen/meals" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Spinach Eggs","tags":["breakfast","high_protein"],"effort":"low","ingredients":[{"name":"Eggs","role":"required"},{"name":"Spinach","role":"optional"}]}'
```

Rank meals:

```bash
curl -s -X POST "$NT_PUBLIC_URL/kitchen/matches" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"effort":"low"}'
```

**Expected:** Returns a ranked list with `meal_name`, `score`, ingredient groups, and score breakdown.
