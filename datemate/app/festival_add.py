"""결과 화면 축제 카드의 「+ 내 코스에 추가」 (2026-11-24, 리디자인 가이드 §2.5 마지막 항목).

이미 만든 코스(화면에서 지금 고른 코스)에 그 축제 방문을 끼워 넣는 변경 초안을 만든다. 「이 축제 주변 코스 추천받기」
(출발지를 행사장으로 바꿔 처음부터 다시 추천, static/festivals.js planAround)와는 다른 기능이고, 그 단추는 그대로다.

흐름: POST /api/plans/{id}/festival-preview {festival_id} → 이 모듈 → 식사 추가와 같은 초안(experience.make_draft).
확정은 같은 draft-apply(experience.apply_draft) — 새 코스 id 로 저장되고 되돌리기(/undo)도 같다.

정하는 것
- 근거는 서버가 직접 정한다. 화면이 보낸 것은 축제 id 하나뿐이다.
  · 제목·좌표·기간: 그 코스의 방문일·시·도로 받은 축제 목록(festivals.fetch_festivals — 화면의 축제 구역과 같은 캐시 열쇠,
    캐시가 없으면 같은 한 번의 목록 조회).
  · 운영 시간: 축제 상세(festival-detail 캐시, 없으면 목록에 보였던 축제(seen)만 상세를 한 번 불러온다 — 상세 경로와 같은 제한).
  운영 시간을 끝내 모르거나 'HH:MM~HH:MM' 하나로 읽을 수 없으면 거절한다. 시간을 지어내지 않는다.
- 자리는 고르지 않는다: 플래너의 예전 규칙(planner.evaluate — 코스 끝 → 장소 사이를 앞에서부터)을 그대로 쓴다.
  출발지가 행사장이 아니므로 맨 앞 자리는 없다(festival_time.festival_slot). 행사장 좌표는 축제 좌표다(festival_time.venue).
- 다시 계산은 plan_rules.reevaluate 만 쓴다(저장된 지연·종료 허용·장소 수 규칙). 필수 조건이 아닌 코스(best_effort 아님)는
  엄격하게(soft=False) 계산해 종료 시각·구간 이동 제한·도보·예산을 넘기는 자리는 쓰지 않는다. 조건 차이가 있던 코스(best_effort)는
  다른 변경과 같이 soft 로 계산하되, 축제 때문에 종료·구간 이동·도보가 더 나빠지면 거절한다(_worse).
- 축제 요금은 비용에 넣지 않는다(주최 측 자유 글, festivals.py). 행사장으로 오가는 교통비는 다른 구간처럼 들어간다.

거절(ValueError → 409, 문구는 사용자 말투로): 데모 코스, 이미 축제가 있는 코스, 목록에 없는 축제·방문일이 기간 밖,
좌표 없음, 운영 시간 모름·읽을 수 없음, 넣을 자리 없음, 넣으면 조건을 넘김. 남의 코스(404)·바꿀 수 없는 코스는 API 쪽(experience_api)에서 막는다.
"""

import copy
import re

from .models import Conditions, FestivalAnchor

DETAIL_ID = re.compile(r'\d{1,12}')


def _listed(c, festival_id):
    """그 코스의 방문일·시·도 축제 목록에서 축제 한 건. 화면의 축제 구역(static/festivals.js request)과 같은 열쇠로 찾는다."""
    from .festivals import fetch_festivals

    day = c.visit_date
    listing = fetch_festivals(day, day, c.region)
    if listing.get('status') != 'available':
        raise ValueError('축제 정보를 지금 확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.')
    found = next((row for row in listing.get('festivals') or [] if str(row.get('id')) == festival_id), None)
    if not found:
        raise ValueError(f'방문일({day}) {c.region} 축제 목록에서 이 축제를 찾지 못했어요. 축제 목록을 다시 불러온 뒤 골라 주세요.')
    if not (found.get('start') or '') <= day.isoformat() <= (found.get('end') or ''):
        raise ValueError(f"‘{found['title']}’ 축제는 {found.get('start')}~{found.get('end')}에 열려 방문일({day})에는 들를 수 없어요.")
    if found.get('lat') is None or found.get('lon') is None:
        raise ValueError(f"‘{found['title']}’ 축제는 행사장 위치 정보가 없어 코스에 넣을 수 없어요.")
    return found


def _hours(festival):
    """축제 상세의 운영 시간(playtime) 원문. 'HH:MM~HH:MM' 범위가 하나로 읽히지 않으면 거절한다."""
    from . import store
    from .festival_time import hours_range
    from .festivals import fetch_festival_detail, seen

    title, festival_id = festival['title'], str(festival['id'])
    if not DETAIL_ID.fullmatch(festival_id):
        raise ValueError(f'‘{title}’ 축제는 운영 시간 정보를 받을 수 없어 몇 시에 들를지 정할 수 없어요. 코스에 넣지 않았어요.')
    detail = store.cached('festival-detail:v1:' + festival_id)
    if not isinstance(detail, dict):
        # 목록에 보였던 축제만 상세를 불러온다(상세 경로 /api/festivals/{id}/detail 과 같은 제한). _listed 가 목록을 읽으며 표시해 둔다.
        detail = fetch_festival_detail(festival_id) if seen(festival_id) else None
    if not isinstance(detail, dict) or detail.get('status') not in (None, 'available'):
        raise ValueError(f'‘{title}’ 축제의 운영 시간을 지금 확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.')
    hours = detail.get('hours')
    hours = hours[:300] if isinstance(hours, str) and hours.strip() else None
    if not hours:
        raise ValueError(f'‘{title}’ 축제는 주최 측이 운영 시간을 알리지 않아 몇 시에 들를지 정할 수 없어요. 코스에 넣지 않았어요.')
    kind, _ = hours_range(hours)
    if kind == 'many':
        raise ValueError(f'‘{title}’ 축제는 운영 시간 안내({hours})에 시간대가 여러 개라 방문일에 몇 시에 여는지 정할 수 없어요. 코스에 넣지 않았어요.')
    if kind != 'one':
        raise ValueError(f'‘{title}’ 축제는 운영 시간 안내({hours})에서 시작·끝 시각을 읽지 못해 몇 시에 들를지 정할 수 없어요. 코스에 넣지 않았어요.')
    return hours


def _no_slot(anchor, c):
    """넣을 자리가 없을 때의 까닭. 운영 시간과 코스 시간이 아예 겹치지 않으면 그렇게, 아니면 오가는 시간·조건 탓이라고 말한다."""
    from .festival_time import _clock, hours_range
    from .planner import minutes

    _, (opening, closing) = hours_range(anchor.hours)
    start, end = minutes(c.start), minutes(c.end)
    lead = f'‘{anchor.title}’ 축제(운영 {anchor.hours})를 이 코스에 넣을 자리가 없어요.'
    if opening >= end:
        return lead + f' 축제가 {_clock(opening)}부터라 코스가 끝나는 {c.end} 뒤예요. 종료 시간을 늦춘 코스에서 다시 시도해 주세요.'
    if closing <= start:
        return lead + f' 축제가 {_clock(closing)}에 끝나 코스 시작({c.start}) 전이에요.'
    if closing - opening < c.stay_minutes:
        return lead + f' 운영 시간이 장소당 머무는 시간({c.stay_minutes}분)보다 짧아요.'
    return (lead + ' 장소 사이나 코스 끝에 행사장을 들르면, 오가는 시간 때문에 운영 시간에 맞춰 닿지 못하거나 '
            f'종료 시각({c.end})·구간 이동 제한({c.max_leg}분) 같은 조건을 넘겨요.')


def _venue_legs(plan, visit):
    """행사장을 오가는 구간: 들어가는 구간(festival_visit.leg)과 행사장에서 나오는 구간(중간이면 다음 장소, 끝이면 귀가)."""
    from .leg_modes import middle_after

    legs = [visit.get('leg') or {}]
    after = middle_after(plan)
    if after is not None:
        legs.append(plan['legs'][after + 1])
    elif len(plan['legs']) > len(plan['places']):
        legs.append(plan['legs'][-1])
    return legs


def _worse(plan, visit, original, c):
    """조건 차이가 있던 코스(soft 계산)에서 축제 때문에 종료·구간 이동·총 도보가 더 나빠지면 그 까닭. 아니면 None.
    엄격하게 계산한 코스는 evaluate 가 이미 막았으므로 여기서 걸리지 않는다."""
    from .planner import minutes

    allowed_end = max(minutes(c.end), minutes(original.get('finish') or c.end))
    if minutes(plan['finish']) > allowed_end:
        return f"축제를 넣으면 코스가 {plan['finish']}에 끝나 종료 시각({c.end})을 넘겨요."
    for leg in _venue_legs(plan, visit):
        if (leg.get('minutes') or 0) > c.max_leg:
            return f"행사장을 오가는 이동이 {leg['minutes']}분으로 구간 이동 제한({c.max_leg}분)을 넘겨요."
    if c.max_walk is not None and (plan.get('walking') or 0) > max(c.max_walk, original.get('walking') or 0):
        return f"축제를 넣으면 총 도보가 {plan['walking']}분으로 도보 제한({c.max_walk}분)을 넘겨요."
    return None


def festival_draft(original, owner, festival_id):
    """원래 코스(original, 감사까지 마친 저장 코스)에 축제를 넣은 초안. 거절은 ValueError(사용자에게 보일 문장)."""
    from .condition_audit import audit_plan
    from .delay_check import kept_note, kept_record
    from .experience import make_draft
    from .leg_modes import uses_car
    from .plan_rules import reevaluate
    from .preferences import hard_blocks
    from .pricing import price_plans

    c = Conditions.model_validate(original['conditions'])
    if c.mode != 'real':
        raise ValueError('가상 장소로 만든 시연 코스에는 실제 축제를 넣을 수 없어요. 실제 장소로 만든 코스에서 시도해 주세요.')
    if c.festival:
        if c.festival.id == festival_id:
            raise ValueError(f'‘{c.festival.title}’ 축제는 이미 이 코스에 들어 있어요.')
        raise ValueError(f'이 코스에는 이미 ‘{c.festival.title}’ 축제가 있어요. 한 코스에는 축제를 하나만 넣을 수 있어요.')
    if not original.get('places'):
        raise ValueError('장소가 없는 코스라 축제를 넣을 수 없어요.')
    found = _listed(c, festival_id)
    anchor = FestivalAnchor(id=str(found['id'])[:240], title=str(found['title'])[:200], lat=found['lat'], lon=found['lon'],
                            hours=_hours(found))
    added = Conditions.model_validate(dict(c.model_dump(mode='json'), festival=anchor.model_dump(mode='json')))
    # 행사장 좌표가 출발지와 똑같은 드문 경우는 축제 기준 코스와 같아 맨 앞 자리도 쓸 수 있다(festival_time.venue_apart).
    soft = bool(original.get('best_effort'))
    verify = uses_car(added)
    # 지각을 반영한 코스는 같은 지연을 넣고(reevaluate 기본), 이미 넘긴 종료는 지금 끝나는 시각까지 허용한다(late_end — 장소 바꾸기와 같다).
    plan, error = reevaluate(original, original['places'], added, late_end=True, soft=soft, verify_routes=verify)
    route_note = None
    if error and verify and added.allow_estimates:
        plan, error = reevaluate(original, original['places'], added, late_end=True, soft=soft)
        route_note = '자동차 경로 조회에 실패해 추정 동선으로 계산했어요.'
    if error:
        raise ValueError(f'지금 코스를 다시 계산하지 못해 축제를 넣지 않았어요({error}).')
    visit = plan.get('festival_visit')
    if not visit:
        raise ValueError(_no_slot(anchor, added))
    reason = _worse(plan, visit, original, added) if soft else None
    if reason:
        raise ValueError(f'‘{anchor.title}’ 축제를 넣지 않았어요. {reason}')
    # 원래 코스의 다른 표시(검색 근거·추천 이유·개인화 등)는 그대로 두고 시간표·구간·비용·축제 방문만 새 계산으로 바꾼다
    # (수단 바꾸기 leg_modes.apply_change 와 같은 방식). 앞선 변경의 안내·지연 기록은 지우고 아래에서 새로 정한다.
    updated = copy.deepcopy(original)
    for key in ('festival_visit', 'festival_change', 'delay_recovery', 'route_verification', 'transport_change',
                'delta', 'change_reason', 'undo_locks', 'condition_checks', 'deviations'):
        updated.pop(key, None)
    reasons = updated.get('reasons')
    updated.update(plan)
    if reasons:
        updated['reasons'] = reasons  # 장소가 그대로라 장소별 추천 이유도 그대로다.
    record = kept_record(original, 'festival')
    if record:
        updated['delay_recovery'] = record
    updated = audit_plan(price_plans([updated])[0], added)
    if hard_blocks(updated):
        raise ValueError(f"‘{anchor.title}’ 축제를 넣으면 필수로 정한 조건({', '.join(b['label'] for b in hard_blocks(updated))})을 지키지 못해요. 코스에 넣지 않았어요.")
    if any(d['state'] == 'unmet' for d in updated.get('deviations') or []):
        updated.update(best_effort=True, status='조건 차이가 있는 변경안')
    updated['undo_locks'] = dict(original['conditions'].get('locked', {}))
    if route_note:
        updated['route_verification'] = route_note
    elif verify:
        updated['route_verification'] = '네이버 자동차 길찾기 재조회 반영'
    # 어디에·몇 시에 들르는지는 이 글에 적지 않는다: make_draft 의 자동차 경로 재조회가 자리를 다시 정할 수 있어,
    # 최종 초안과 견준 축제 변화 안내(festival_change — festival_time.change_note)가 그 한 줄을 맡는다(식사·합의 초안과 같은 모양).
    summary = (f"‘{anchor.title}’ 축제를 넣고 이동·시간·비용을 다시 계산했어요. "
               '축제 요금은 비용에 넣지 않았어요(주최 측 안내 확인).' + kept_note(original))
    draft = make_draft(updated, original, owner, 'festival', summary)
    # 재조회로 축제가 빠진 초안은 내지 않는다(만든 초안은 쓰이지 않고 10분 뒤 사라진다).
    if not draft['plan'].get('festival_visit'):
        raise ValueError(_no_slot(anchor, added))
    return draft
