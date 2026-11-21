"""축제 참석 시간 고정: 고른 축제(conditions.festival)의 방문을 운영 시간에 맞춰 코스 맨 앞에 둔다.

- 근거: 관광공사 축제 상세(detailIntro2)의 playtime(app/festivals.fetch_festival_detail 의 hours). 추천을 시작할 때
  이미 받아 둔 상세 캐시에서만 읽어 conditions.festival.hours 에 담는다(recommendation_service.generate, 새 외부 호출 없음).
  저장된 코스는 그 값을 그대로 가지고 있어 다시 열거나 장소를 바꿔도 같은 시각이 나온다.
- 읽는 시간: 'HH:MM~HH:MM' 범위가 정확히 하나일 때만 쓴다. 범위가 없거나('상시 개방', '18시~22시') 여러 개면
  (요일·날짜별) 고정하지 않고 안내만 한다. '입장 마감 17:00' 같은 단독 시각은 쓰지 않는다.
- 고정 방식: 행사장이 곧 출발지라 축제를 첫 일정으로 둔다. 방문 시작 = max(코스 시작, 개막), 머무는 시간 = 장소당 체류
  시간(conditions.stay_minutes). 개막까지 기다림이 MAX_WAIT 분 이하이고 방문이 운영 종료·코스 종료 안에 끝날 때만 고정한다.
  고정하면 첫 장소는 축제가 끝난 시각에 행사장에서 출발한다(planner.evaluate). 못 하면 코스는 예전처럼 짜고 까닭을 알린다.
- 하지 않는 것: 축제를 코스 끝이나 중간에 두기(행사장으로 돌아오는 구간이 따로 필요해 구간·지도·귀가 계산이 모두 바뀐다),
  요금을 비용에 넣기(주최 측 자유 글이라 계산하지 않는다, festivals.py).
"""

import re
from functools import lru_cache

RANGE = re.compile(r'(\d{1,2})\s*:\s*(\d{2})\s*[~\-–]\s*(\d{1,2})\s*:\s*(\d{2})')
# 코스 시작 뒤 개막까지 이만큼(분)은 행사장에서 기다린다. 더 길면 고정하지 않고 시작 시간을 바꾸라고 안내한다.
MAX_WAIT = 60


def _minutes(value):
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def _clock(value):
    return f'{value // 60 % 24:02}:{value % 60:02}'


def hours_range(text):
    """('one', (개막, 종료)) · ('many', None) · ('none', None). 종료가 개막보다 이르면 다음 날 새벽으로 본다."""
    ranges = set()
    for a, b, c, d in RANGE.findall(text or ''):
        a, b, c, d = int(a), int(b), int(c), int(d)
        if a > 23 or b > 59 or c > 24 or d > 59 or (c == 24 and d):
            continue
        opening, closing = a * 60 + b, c * 60 + d
        if closing <= opening:
            closing += 1440
        ranges.add((opening, closing))
    if len(ranges) == 1:
        return 'one', next(iter(ranges))
    return ('many' if ranges else 'none'), None


@lru_cache(maxsize=256)
def _slot(hours, start, end, stay):
    """(고정 여부, 까닭, 값들). 추천 탐색에서 장소 조합마다 불리므로 같은 입력은 한 번만 계산한다."""
    if not hours:
        return False, 'no_hours', ()
    kind, found = hours_range(hours)
    if kind != 'one':
        return False, 'varies' if kind == 'many' else 'unparsed', ()
    opening, closing = found
    begin, finish = _minutes(start), _minutes(end)
    arrival = max(begin, opening)
    departure = arrival + stay
    if arrival - begin <= MAX_WAIT and departure <= min(closing, finish):
        return True, 'fixed', (arrival, departure, arrival - begin, opening, closing)
    if opening >= finish:
        return False, 'after_course', (opening, closing)
    if closing <= begin:
        return False, 'before_course', (opening, closing)
    if arrival - begin > MAX_WAIT and opening + stay <= closing:
        return False, 'late_opening', (opening, closing)
    return False, 'too_short', (opening, closing)


def festival_slot(c):
    """조건으로 정해지는 축제 방문 칸. 고정하면 dict(arrival·departure 는 '하루의 분'), 아니면 None."""
    festival = c.festival
    if not festival:
        return None
    fixed, _, values = _slot(festival.hours, c.start, c.end, c.stay_minutes)
    if not fixed:
        return None
    arrival, departure, wait, _, _ = values
    return dict(arrival=arrival, departure=departure, wait=wait)


def visit_record(c, slot):
    """코스에 저장하는 축제 방문(plan['festival_visit']). 화면·현장 일정·조건 확인이 읽는다."""
    return dict(id=c.festival.id, title=c.festival.title, hours=c.festival.hours, position='first',
                arrival=_clock(slot['arrival']), departure=_clock(slot['departure']),
                stay=slot['departure'] - slot['arrival'], wait=slot['wait'])


def places_start(c):
    """첫 장소로 출발하는 시각(하루의 분). 축제를 고정했으면 축제 방문이 끝난 때, 아니면 코스 시작."""
    slot = festival_slot(c)
    return slot['departure'] if slot else _minutes(c.start)


def explain(title, hours, start, end, stay, finish=None):
    """(고정 여부, 안내 문장). 조건 확인(condition_audit)과 축제 안내(recommendation_summary.festival_context)가 같이 쓴다.
    finish 는 코스가 끝나는 시각('HH:MM'). 알면 '코스가 끝난 뒤 들르기'를 그 시각으로 적는다."""
    fixed, reason, values = _slot(hours, start, end, stay)
    if fixed:
        arrival, departure, wait, _, _ = values
        text = (f'‘{title}’ 방문을 안내된 운영 시간({hours})에 맞춰 {_clock(arrival)}~{_clock(departure)}({departure - arrival}분)으로 '
                '코스 맨 앞에 고정하고, 나머지 장소는 축제가 끝난 뒤 행사장에서 출발하도록 배치했어요.')
        if wait:
            text += f' 코스 시작 {start}부터 축제 시작까지 {wait}분 기다려요.'
        return True, text
    if reason == 'no_hours':
        return False, '축제 운영 시간은 확인하지 못했어요. 그래서 축제 방문 시간은 코스에 넣지 않고 행사장을 출발점으로만 삼았어요. 주최 측 안내를 확인해 주세요.'
    if reason == 'unparsed':
        return False, f'축제 운영 시간 안내: {hours} — 시작·끝 시각을 읽지 못해 축제 방문 시간은 코스에 넣지 않았어요.'
    if reason == 'varies':
        return False, f'축제 운영 시간 안내({hours})에 시간대가 여러 개라 방문일의 시간을 정하지 못해, 축제 방문 시간은 코스에 넣지 않았어요. 주최 측 안내를 확인해 주세요.'
    opening, closing = values
    if reason == 'after_course':
        after = f'코스가 끝난 {finish} 뒤에' if finish else '코스가 끝난 뒤에'
        return False, f'축제는 안내된 운영 시간({hours})상 {_clock(opening)}부터라 {after} 들를 수 있어요. 축제 방문 시간은 코스에 넣지 않았어요.'
    if reason == 'before_course':
        return False, f'축제는 안내된 운영 시간({hours})상 {_clock(closing)}에 끝나 코스 시간에는 들를 수 없어요. 시작 시간을 앞당기면 축제부터 일정에 넣을 수 있어요.'
    if reason == 'late_opening':
        after = f' 코스가 끝난 {finish} 뒤에 들르거나,' if finish and _minutes(finish) <= opening else ''
        return False, (f'축제는 안내된 운영 시간({hours})상 {_clock(opening)}부터라, 코스 시작 {start}에 맞춰 축제 방문 시간을 고정하지 않았어요.'
                       f'{after} 시작 시간을 {_clock(opening)} 무렵으로 늦추면(종료 시간도 함께) 축제부터 일정에 넣을 수 있어요.')
    return False, f'안내된 운영 시간({hours})과 코스 시간({start}~{end})이 {stay}분 넘게 겹치지 않아 축제 방문 시간을 고정하지 않았어요. 시작·종료 시간을 조정해 보세요.'
