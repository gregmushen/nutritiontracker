from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NutrientsPer100(BaseModel):
    calories_kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    sugar_g: float = 0
    added_sugar_g: float = 0
    saturated_fat_g: float = 0
    trans_fat_g: float = 0
    monounsaturated_fat_g: float = 0
    polyunsaturated_fat_g: float = 0
    fiber_g: float = 0
    cholesterol_mg: float = 0
    caffeine_mg: float = 0
    sodium_mg: float = 0
    potassium_mg: float = 0
    calcium_mg: float = 0
    iron_mg: float = 0
    magnesium_mg: float = 0
    zinc_mg: float = 0
    phosphorus_mg: float = 0
    copper_mg: float = 0
    manganese_mg: float = 0
    selenium_ug: float = 0
    chromium_ug: float = 0
    iodine_ug: float = 0
    vitamin_a_ug: float = 0
    vitamin_c_mg: float = 0
    vitamin_d_ug: float = 0
    vitamin_e_mg: float = 0
    vitamin_k_ug: float = 0
    thiamin_mg: float = 0
    riboflavin_mg: float = 0
    vitamin_b6_mg: float = 0
    vitamin_b12_ug: float = 0
    niacin_mg: float = 0
    pantothenic_acid_mg: float = 0
    biotin_ug: float = 0
    folate_ug: float = 0
    folic_acid_ug: float = 0
    choline_mg: float = 0


NUTRIENT_FIELDS = tuple(NutrientsPer100.model_fields)


SourceType = Literal["custom", "open_food_facts", "food_data_central", "recipe"]


class FoodCreate(BaseModel):
    source: Literal["custom"] = "custom"
    source_code: str | None = None
    name: str
    brand: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    serving_quantity: float | None = None
    serving_unit: str | None = None
    serving_size_text: str | None = None
    ingredients_text: str | None = None
    allergens_tags: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    categories_tags: list[str] = Field(default_factory=list)
    labels_tags: list[str] = Field(default_factory=list)
    countries_tags: list[str] = Field(default_factory=list)
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    product_quantity: float | None = None
    product_quantity_unit: str | None = None
    base_quantity: float = 100
    base_unit: str = "g"
    density_g_per_ml: float | None = None
    nutrients: NutrientsPer100 = Field(default_factory=NutrientsPer100)


class Food(FoodCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class FoodUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    serving_quantity: float | None = None
    serving_unit: str | None = None
    serving_size_text: str | None = None
    ingredients_text: str | None = None
    allergens_tags: list[str] | None = None
    dietary_tags: list[str] | None = None
    categories_tags: list[str] | None = None
    labels_tags: list[str] | None = None
    countries_tags: list[str] | None = None
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    product_quantity: float | None = None
    product_quantity_unit: str | None = None
    density_g_per_ml: float | None = None
    nutrients: NutrientsPer100 | None = None

    @field_validator(
        "allergens_tags",
        "dietary_tags",
        "categories_tags",
        "labels_tags",
        "countries_tags",
    )
    @classmethod
    def _tags_cannot_be_null(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("tag lists cannot be null; use [] to clear them")
        return value


class FoodOut(BaseModel):
    id: int
    source: SourceType
    source_code: str | None = None
    name: str
    brand: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    serving_quantity: float | None = None
    serving_unit: str | None = None
    serving_size_text: str | None = None
    ingredients_text: str | None = None
    allergens_tags: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    categories_tags: list[str] = Field(default_factory=list)
    labels_tags: list[str] = Field(default_factory=list)
    countries_tags: list[str] = Field(default_factory=list)
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    product_quantity: float | None = None
    product_quantity_unit: str | None = None
    base_quantity: float = 100
    base_unit: str = "g"
    density_g_per_ml: float | None = None
    # Nutrients (flat, as stored in DB)
    calories_kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    sugar_g: float = 0
    added_sugar_g: float = 0
    saturated_fat_g: float = 0
    trans_fat_g: float = 0
    monounsaturated_fat_g: float = 0
    polyunsaturated_fat_g: float = 0
    fiber_g: float = 0
    cholesterol_mg: float = 0
    caffeine_mg: float = 0
    sodium_mg: float = 0
    potassium_mg: float = 0
    calcium_mg: float = 0
    iron_mg: float = 0
    magnesium_mg: float = 0
    zinc_mg: float = 0
    phosphorus_mg: float = 0
    copper_mg: float = 0
    manganese_mg: float = 0
    selenium_ug: float = 0
    chromium_ug: float = 0
    iodine_ug: float = 0
    vitamin_a_ug: float = 0
    vitamin_c_mg: float = 0
    vitamin_d_ug: float = 0
    vitamin_e_mg: float = 0
    vitamin_k_ug: float = 0
    thiamin_mg: float = 0
    riboflavin_mg: float = 0
    vitamin_b6_mg: float = 0
    vitamin_b12_ug: float = 0
    niacin_mg: float = 0
    pantothenic_acid_mg: float = 0
    biotin_ug: float = 0
    folate_ug: float = 0
    folic_acid_ug: float = 0
    choline_mg: float = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
