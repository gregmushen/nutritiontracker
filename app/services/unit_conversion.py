from dataclasses import dataclass

WEIGHT_TO_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}

VOLUME_TO_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "cup": 236.588,
    "tbsp": 14.787,
    "tsp": 4.929,
    "fl_oz": 29.574,
}

PORTION_UNITS = {"serving", "piece", "slice"}


@dataclass
class ConversionResult:
    grams: float
    approximate: bool
    milliliters: float | None = None

    def amount_in(self, base_unit: str) -> float:
        normalized = base_unit.lower().strip()
        if normalized == "g":
            return self.grams
        if normalized == "ml":
            if self.milliliters is None:
                raise ValueError(
                    "Cannot convert a weight amount to a volume-based food "
                    "without density_g_per_ml"
                )
            return self.milliliters
        raise ValueError(f"Unsupported food base unit: '{base_unit}'")


def convert_to_grams(
    amount: float,
    unit: str,
    density_g_per_ml: float | None = None,
    serving_quantity: float | None = None,
    serving_unit: str | None = None,
) -> ConversionResult:
    unit = unit.lower().strip()
    if density_g_per_ml is not None and density_g_per_ml <= 0:
        raise ValueError("density_g_per_ml must be greater than zero")

    if unit in WEIGHT_TO_GRAMS:
        grams = amount * WEIGHT_TO_GRAMS[unit]
        milliliters = (
            grams / density_g_per_ml if density_g_per_ml is not None else None
        )
        return ConversionResult(
            grams=grams, approximate=False, milliliters=milliliters
        )

    if unit in VOLUME_TO_ML:
        ml = amount * VOLUME_TO_ML[unit]
        if density_g_per_ml is not None:
            return ConversionResult(
                grams=ml * density_g_per_ml,
                approximate=False,
                milliliters=ml,
            )
        return ConversionResult(grams=ml, approximate=True, milliliters=ml)

    if unit in PORTION_UNITS:
        if serving_quantity is None or serving_unit is None:
            raise ValueError(
                f"Cannot convert '{unit}' without serving_quantity and serving_unit on the food"
            )
        per_serving = convert_to_grams(serving_quantity, serving_unit, density_g_per_ml)
        return ConversionResult(
            grams=amount * per_serving.grams,
            approximate=per_serving.approximate,
            milliliters=(
                None
                if per_serving.milliliters is None
                else amount * per_serving.milliliters
            ),
        )

    raise ValueError(f"Unsupported unit: '{unit}'")
