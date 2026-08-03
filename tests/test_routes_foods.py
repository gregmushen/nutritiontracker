from app.repositories.foods import FoodRepository


def _seed_food(db, name="Banana", **kwargs):
    repo = FoodRepository(db)
    repo.ensure_fts()
    return repo.create(source="custom", name=name, owner_user_id=1, **kwargs)


def test_search_foods(client, db):
    _seed_food(db, "Chicken Breast", protein_g=31)
    _seed_food(db, "Chicken Thigh", protein_g=26)
    r = client.get("/foods/search?q=chicken")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_search_rejects_extreme_pagination(client):
    assert client.get("/foods/search?q=x&limit=101").status_code == 422
    assert client.get("/foods/search?q=x&offset=10001").status_code == 422


def test_get_food(client, db):
    fid = _seed_food(db, "Banana", calories_kcal=89)
    r = client.get(f"/foods/{fid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Banana"


def test_get_food_404(client):
    r = client.get("/foods/9999")
    assert r.status_code == 404


def test_barcode_lookup(client, db):
    _seed_food(db, "Granola", barcode="12345")
    r = client.get("/foods/barcode/12345")
    assert r.status_code == 200
    assert r.json()["name"] == "Granola"


def test_barcode_404(client):
    r = client.get("/foods/barcode/nope")
    assert r.status_code == 404


def test_barcode_lookup_caches_global_open_food_facts_result(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.foods.fetch_off_by_barcode",
        lambda barcode: {
            "source": "open_food_facts",
            "source_code": barcode,
            "name": "Imported product",
            "barcode": barcode,
            "caffeine_mg": 56.3,
        },
    )

    r = client.get("/foods/barcode/0889392000863")

    assert r.status_code == 200
    assert r.json()["caffeine_mg"] == 56.3
    assert client.get("/foods/barcode/0889392000863").json()["id"] == r.json()["id"]


def test_barcode_refresh_persists_product_metadata(client, db, monkeypatch):
    barcode = "555"
    food_id = _seed_food(db, "Old", barcode=barcode, source_code=barcode)
    db.execute(
        "UPDATE foods SET source = 'open_food_facts' WHERE id = ?", (food_id,)
    )
    db.commit()
    monkeypatch.setattr(
        "app.routes.foods.fetch_off_by_barcode",
        lambda value: {
            "source": "open_food_facts",
            "source_code": value,
            "name": "Refreshed",
            "barcode": value,
            "protein_g": 0,
            "ingredients_text": "Water",
            "allergens_tags": ["en:milk"],
            "dietary_tags": [],
            "categories_tags": ["en:drinks"],
            "labels_tags": [],
            "countries_tags": ["en:united-states"],
            "nutriscore_grade": "a",
            "nova_group": 1,
            "product_quantity": 355,
            "product_quantity_unit": "ml",
        },
    )

    response = client.get(f"/foods/barcode/{barcode}")

    assert response.status_code == 200
    assert response.json()["protein_g"] == 0
    assert response.json()["ingredients_text"] == "Water"
    assert response.json()["allergens_tags"] == ["en:milk"]
    assert response.json()["product_quantity"] == 355


def test_barcode_refresh_stores_a_measured_zero(client, db, monkeypatch):
    """A refreshed label declaring 0 must overwrite NULL, not be filtered out.

    NULL means "not reported" and 0 means "measured as zero", so a truthiness
    filter on the refresh would leave the column unknown forever.
    """
    _seed_food(db, "Diet soda", barcode="555", source_code="555")
    db.execute("UPDATE foods SET source = 'open_food_facts' WHERE barcode = '555'")
    db.commit()

    monkeypatch.setattr(
        "app.routes.foods.fetch_off_by_barcode",
        lambda barcode: {
            "source": "open_food_facts",
            "source_code": barcode,
            "name": "Diet soda",
            "barcode": barcode,
            "calories_kcal": 0,
            "sugar_g": 0,
        },
    )

    body = client.get("/foods/barcode/555").json()

    assert body["calories_kcal"] == 0
    assert body["sugar_g"] == 0


def test_create_custom_food(client, db):
    FoodRepository(db).ensure_fts()
    r = client.post("/foods", json={"name": "My Food", "source": "custom",
                                     "nutrients": {"calories_kcal": 100}})
    assert r.status_code == 201
    assert r.json()["name"] == "My Food"


def test_create_food_rejects_non_finite_base_measurements(client):
    response = client.post(
        "/foods",
        content='{"name":"Invalid","base_quantity":1e309}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_update_custom_food(client, db):
    fid = _seed_food(db, "Old")
    r = client.patch(f"/foods/{fid}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


def test_update_rejects_null_tag_lists(client, db):
    fid = _seed_food(db, "Old")
    response = client.patch(f"/foods/{fid}", json={"allergens_tags": None})

    assert response.status_code == 422


def test_delete_custom_food(client, db):
    fid = _seed_food(db, "Gone")
    r = client.delete(f"/foods/{fid}")
    assert r.status_code == 204
