from app.pricing import base_price


def test_base_price():
    assert base_price(2) == 4
