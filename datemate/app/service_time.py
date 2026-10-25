"""Business dates follow Seoul even when the container uses UTC."""
from datetime import datetime, timedelta, timezone

SEOUL = timezone(timedelta(hours=9))


def today():
    return datetime.now(SEOUL).date()
