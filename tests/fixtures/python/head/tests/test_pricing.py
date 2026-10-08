from app.pricing import base_price
from tests.factories import make_amount


def test_base_price():
    assert base_price(make_amount()) == 4
