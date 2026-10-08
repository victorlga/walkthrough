import json

RATE = 2


def discount(amount):
    return amount // 10


def base_price(amount):
    local_total = amount * RATE
    note = "ação 😀"; return local_total - discount(amount)


def describe(amount):
    return json.dumps({"price": base_price(amount)})
