"""Business dates follow Seoul even when the container uses UTC."""
import os
from datetime import datetime, timedelta, timezone

SEOUL = timezone(timedelta(hours=9))


def today():
    return datetime.now(SEOUL).date()


def planning_now():
    """새 추천 요청이 지난 날짜·시각인지 가릴 때 쓰는 한국 시각.

    DATEMATE_PLANNING_NOW(예: 2026-01-01T09:00, 한국 시각으로 읽음)가 있으면 그 시각으로 고정한다.
    테스트가 과거의 고정 방문일을 쓰기 때문에 tests/conftest.py 가 넣는다. 운영에서는 비워 두고 실제 시계를 쓴다.
    이 값은 지난 날짜 검사에만 쓰고 today()(가격·축제·후기 날짜)에는 영향을 주지 않는다.
    """
    fixed = os.getenv('DATEMATE_PLANNING_NOW', '').strip()
    if fixed:
        moment = datetime.fromisoformat(fixed)
        return moment.replace(tzinfo=SEOUL) if moment.tzinfo is None else moment.astimezone(SEOUL)
    return datetime.now(SEOUL)


def past_visit_message(conditions):
    """방문일이 지났거나, 오늘인데 종료 시각이 이미 지났으면 안내 문구. 아니면 None.

    시작 시각만 지난 경우는 막지 않는다(화면이 다음 시간대로 맞추고, 서버는 남은 시간 안에서 찾는다).
    """
    now = planning_now()
    day = now.date()
    if conditions.visit_date < day:
        return (f'방문 날짜({conditions.visit_date.isoformat()})가 이미 지났어요. '
                f'오늘({day.isoformat()}) 이후 날짜를 골라 주세요.')
    if conditions.visit_date == day and conditions.end <= now.strftime('%H:%M'):
        return (f'오늘은 종료 시각 {conditions.end}이 이미 지났어요. '
                '종료 시각을 늦추거나 다른 날짜를 골라 주세요.')
    return None
