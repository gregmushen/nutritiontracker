from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.sources import SourceType


class NutrientsPer100(BaseModel):
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    sugar_g: float | None = None
    added_sugar_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    fiber_g: float | None = None
    cholesterol_mg: float | None = None
    caffeine_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    magnesium_mg: float | None = None
    zinc_mg: float | None = None
    phosphorus_mg: float | None = None
    copper_mg: float | None = None
    manganese_mg: float | None = None
    selenium_ug: float | None = None
    chromium_ug: float | None = None
    iodine_ug: float | None = None
    vitamin_a_ug: float | None = None
    vitamin_c_mg: float | None = None
    vitamin_d_ug: float | None = None
    vitamin_e_mg: float | None = None
    vitamin_k_ug: float | None = None
    thiamin_mg: float | None = None
    riboflavin_mg: float | None = None
    vitamin_b6_mg: float | None = None
    vitamin_b12_ug: float | None = None
    niacin_mg: float | None = None
    pantothenic_acid_mg: float | None = None
    biotin_ug: float | None = None
    folate_ug: float | None = None
    folic_acid_ug: float | None = None
    choline_mg: float | None = None


NUTRIENT_FIELDS = tuple(NutrientsPer100.model_fields)


__all__ = [
    "NUTRIENT_FIELDS",
    "Food",
    "FoodCreate",
    "FoodOut",
    "FoodSourceOut",
    "FoodUpdate",
    "NutrientsPer100",
    "SourceType",
]


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


class FoodSourceOut(BaseModel):
    """A food composition dataset, its licence and its quality tier."""

    code: str
    label: str
    publisher: str
    tier: int
    license: str
    url: str = ""
    citation: str | None = None
    dataset_version: str | None = None
    food_count: int = 0

    model_config = {"from_attributes": True}


class FoodOut(BaseModel):
    id: int
    source: str
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
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    sugar_g: float | None = None
    added_sugar_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    fiber_g: float | None = None
    cholesterol_mg: float | None = None
    caffeine_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    magnesium_mg: float | None = None
    zinc_mg: float | None = None
    phosphorus_mg: float | None = None
    copper_mg: float | None = None
    manganese_mg: float | None = None
    selenium_ug: float | None = None
    chromium_ug: float | None = None
    iodine_ug: float | None = None
    vitamin_a_ug: float | None = None
    vitamin_c_mg: float | None = None
    vitamin_d_ug: float | None = None
    vitamin_e_mg: float | None = None
    vitamin_k_ug: float | None = None
    thiamin_mg: float | None = None
    riboflavin_mg: float | None = None
    vitamin_b6_mg: float | None = None
    vitamin_b12_ug: float | None = None
    niacin_mg: float | None = None
    pantothenic_acid_mg: float | None = None
    biotin_ug: float | None = None
    folate_ug: float | None = None
    folic_acid_ug: float | None = None
    choline_mg: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
