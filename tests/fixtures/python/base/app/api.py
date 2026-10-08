from app.pricing import describe


def audit(event):
    return {"seen": event}


def handler(event):
    audit(event)
    return describe(event["amount"])
