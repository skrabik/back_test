from datetime import datetime, timedelta


def seconds_until_tomorrow() -> int:
    return int((datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time()) - datetime.now()).total_seconds())


def seconds_until_day_after_tomorrow() -> int:
    return int((datetime.combine(datetime.now().date() + timedelta(days=2), datetime.min.time()) - datetime.now()).total_seconds())
