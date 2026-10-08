import json

RATE = 2
MAX = 10
LIMITS = {"max": MAX}


def discount(amount):
    return min(amount // 10, LIMITS["max"])


def base_price(amount):
    local_total = amount * RATE
    note = "ação 😀"; return local_total - discount(amount)


def describe(amount):
    return json.dumps({"price": base_price(amount)})
