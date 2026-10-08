from app.pricing import describe


def handler(event):
    return describe(event["amount"])
