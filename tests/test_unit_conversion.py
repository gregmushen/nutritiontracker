import pytest
from app.services.unit_conversion import convert_to_grams


def test_grams_identity():
    r = convert_to_grams(100, "g")
    assert r.grams == 100
    assert r.approximate is False


def test_kg_to_grams():
    r = convert_to_grams(1, "kg")
    assert r.grams == 1000


def test_oz_to_grams():
    r = convert_to_grams(1, "oz")
    assert abs(r.grams - 28.3495) < 0.01


def test_lb_to_grams():
    r = convert_to_grams(1, "lb")
    assert abs(r.grams - 453.592) < 0.1


def test_ml_with_density():
    r = convert_to_grams(100, "ml", density_g_per_ml=1.03)
    assert r.grams == 103
    assert r.approximate is False
    assert r.amount_in("ml") == 100


def test_ml_without_density_uses_water():
    r = convert_to_grams(100, "ml")
    assert r.grams == 100
    assert r.approximate is True
    assert r.amount_in("ml") == 100


def test_weight_to_volume_requires_density():
    with pytest.raises(ValueError, match="without density"):
        convert_to_grams(80, "g").amount_in("ml")

    result = convert_to_grams(80, "g", density_g_per_ml=0.8)
    assert result.amount_in("ml") == 100


def test_cup_to_grams():
    r = convert_to_grams(1, "cup", density_g_per_ml=1.0)
    assert abs(r.grams - 236.588) < 0.1


def test_tbsp():
    r = convert_to_grams(1, "tbsp", density_g_per_ml=1.0)
    assert abs(r.grams - 14.787) < 0.01


def test_tsp():
    r = convert_to_grams(1, "tsp", density_g_per_ml=1.0)
    assert abs(r.grams - 4.929) < 0.01


def test_fl_oz():
    r = convert_to_grams(1, "fl_oz", density_g_per_ml=1.0)
    assert abs(r.grams - 29.574) < 0.01


def test_serving_with_quantity():
    r = convert_to_grams(2, "serving", serving_quantity=50, serving_unit="g")
    assert r.grams == 100
    assert r.approximate is False


def test_serving_without_quantity_raises():
    with pytest.raises(ValueError, match="serving"):
        convert_to_grams(1, "serving")


def test_unknown_unit_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        convert_to_grams(1, "bushel")
