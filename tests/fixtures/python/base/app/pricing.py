import json

RATE = 2
MAX = 10
LIMITS = {"max": MAX}


def base_price(amount):
    return amount * RATE


def describe(amount):
    return json.dumps({"price": base_price(amount)})
