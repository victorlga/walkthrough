import json

RATE = 2


def base_price(amount):
    return amount * RATE


def describe(amount):
    return json.dumps({"price": base_price(amount)})
