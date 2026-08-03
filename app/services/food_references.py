import json
import sqlite3


def replace_food_references(
    conn: sqlite3.Connection, *, old_food_id: int, new_food_id: int
) -> None:
    conn.execute(
        "UPDATE diary_entries SET food_id = ? WHERE food_id = ?",
        (new_food_id, old_food_id),
    )
    for recipe_id, ingredients_json in conn.execute(
        "SELECT id, ingredients FROM recipes ORDER BY id"
    ):
        ingredients = json.loads(ingredients_json)
        changed = False
        for ingredient in ingredients:
            if ingredient.get("food_id") == old_food_id:
                ingredient["food_id"] = new_food_id
                changed = True
        if changed:
            conn.execute(
                "UPDATE recipes SET ingredients = ? WHERE id = ?",
                (json.dumps(ingredients), recipe_id),
            )
