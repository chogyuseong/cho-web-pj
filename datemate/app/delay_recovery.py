"""지각 복구: 늦어서 맞출 수 없게 된 장소를 같은 종류의 다른 곳으로 바꾸거나 빼고, 남은 시간표를 지연을 반영해 다시 짜 저장한다.

- 무엇을 고치나: 지각 확인(app/delay_check.py)의 첫 문제가 장소의 마지막 입장·영업 종료일 때 그 장소 하나.
  축제 운영 시간·일정 종료를 넘기는 문제는 장소를 바꿔 풀 일이 아니라 대상이 아니다.
- 후보: 이 코스를 만들 때 쓰던 동네 후보(replacements 와 같은 출처 — catalog·이 사용자가 찾아 둔 공공 자료·식당 자료) 안에서만.
  새 장소 검색·길찾기 같은 외부 호출은 하지 않는다. 바뀌는 구간은 거리 기반 추정, 바뀌지 않는 구간은 저장된 값을 그대로 쓴다
  (routes.saved_routes). 같은 종류 = 3안 선택과 같은 묶음(option_diversity.place_group — 식사·카페·보기·걷기·하기·쉬기,
  '기타'면 같은 분류). 코스에 이미 있는 곳, 예약이 필요한 곳(reservation true), 방문일 휴무인 곳은 뺀다.
- 열림: 지연을 반영한 도착 시각부터 머무는 시간 동안 영업 중(planner.visit_window). 영업시간·휴무 자료가 없는 후보는 추정을 허용한
  코스에서만 '연다'고 가정해 맨 뒤에 두고 '영업시간 미확인'으로 알린다.
- 거리: 앞뒤 구간이 코스 조건 max_leg 이하. 원래보다 이동이 덜 늘어나는 순으로 최대 3곳.
- 남은 일정 전체: 후보마다 planner.evaluate(delays=…)로 지연을 반영한 시간표를 다시 짠다. 뒤 장소가 또 늦거나, 축제(맨 앞 고정·코스 끝)
  시각이 달라지거나, 예산·총 도보가 새로 넘치면 그 후보는 내지 않는다(저장하려 하면 409). 일정 종료를 넘기는 것은 막지 않고 알린다
  (지각 자체로 늦어진 것이라 장소를 바꿔 풀 수 없다 — 종료가 필수 조건이면 저장 단계 hard_blocks 가 막는다).
  코스 중간 축제(position 'middle', after=i)는 같은 자리(빼기는 번호를 당긴 자리)에만 다시 두고(evaluate festival_after),
  그 자리에 못 두거나 자리가 장소 사이가 아니게 되면 그 후보·빼기는 내지 않는다('중간 축제 시간에 맞출 수 없어요'). 축제 시각이 늦어지는 것은 허용.
  축제 바로 앞 장소를 바꾸면 다음 지점, 바로 뒤 장소를 바꾸면 앞 지점이 행사장(축제 좌표 — festival_time.venue)이다.
- 빼고 진행: 같은 검사로 그 장소를 뺀 코스. 장소가 0곳이 되면 허용하지 않는다. 방문 장소 수 조건(count)은 사용자가 정한 값을 그대로 둔다
  (요청 수보다 적은 코스가 된다 — 그 코스의 장소 바꾸기·레저 후보는 장소 수를 검사하지 않고 계산한다, app/plan_rules.py).
- 앞서 반영한 다른 장소의 지연(2026-11-24): 지각 확인을 다른 번호에서 다시 해도 남긴다(안내 문장에 '다른 장소에 앞서 반영한 N분 지연은
  그대로 뒀어요'). 장소를 빼면 그 뒤 번호의 지연은 번호를 당기고, 뺀 장소에 앞서 적어 둔 지연은 버리고 안내 문장에 적는다
  ('… 그 장소를 빼서 넣지 않았어요' — 82차 합의 코스와 같은 판단). 지금 다루는 지연은 그 장소를 빼도 다음 장소가 이어받는다
  (delay_check.delays_after_removal).
- 예약한 장소·고정한 장소는 바꾸지도 빼지도 않는다(예약처에 연락·고정 해제 안내).
- 저장: plan_changes.save_change(recovery=…) — 장소 바꾸기처럼 새 코스 id(parent 연결)로 저장되어 되돌리기·이력이 그대로 동작한다.
  반영한 지연은 plan['delay_recovery'].delays({장소 번호: 분})에 남겨, 지각 확인을 다시 열면 지금 시간표 기준으로 이어서 본다.
"""

import copy

from .delay_check import carried_delay, delay_check, festival_minutes
from .festival_time import places_start
from .models import Conditions
from .planner import ASSUMED_HOURS, clock, minutes, visit_window

MAX_OPTIONS = 3
# 거리·영업으로 거른 뒤 남은 일정 전체를 다시 짜 볼 후보 수(앞에서부터). 많아도 이만큼만 계산한다.
MAX_TRIES = 12
PLACE_PROBLEMS = ("last_entry", "closing")
# 묶음 후보(2026-11-23): 문제 장소를 바꿔도 뒤 장소 한 곳이 또 늦을 때, 그 뒤 장소를 대신할 같은 종류 후보를 몇 곳까지 계산해 볼지.
# 가까운 순으로 이만큼만 다시 짜 보고, 모두 안 맞으면 그 뒤 장소를 빼는 안으로 넘어간다. 늘리면 지각 확인 응답이 느려진다
# (후보 하나마다 planner.evaluate 한 번 — 외부 호출은 없다).
MAX_BUNDLE_TRIES = 4
# 뒤 장소가 '또 늦는다'고 보는 evaluate 실패 까닭(planner._evaluate 의 fail reason). 이 둘일 때만 묶음을 시도한다.
LATER_REASONS = ("영업시간 밖 방문", "마지막 입장 시간 초과")


class Refused(ValueError):
    pass


def candidate_pool(plan, c):
    """장소 바꾸기(planner.replacements)와 같은 동네 후보. 외부 호출 없음."""
    from .planner import candidates
    from .quality import pool

    return pool(c) if plan.get("best_effort") else candidates(c)


def _group(place):
    from .option_diversity import place_group

    group = place_group(place)
    return group if group != "기타" else ("기타", place.get("category"))


def kind_label(place):
    from .option_diversity import GROUP_LABELS, place_group

    return GROUP_LABELS.get(place_group(place)) or place.get("category") or "장소"


def _josa(word, a, b):
    from .leg_modes import josa

    return josa(word, a, b)


def _ro(word):
    """'(으)로': 받침이 없거나 ㄹ 받침이면 '로', 그 밖의 받침이면 '으로'(산책길로·카페로·박물관으로).
    leg_modes.josa 는 받침 유무만 봐서 ㄹ 받침 뒤에 '으로'를 붙인다 — 장소 이름에는 '길·마을·홀'처럼 ㄹ 로 끝나는 말이 많아 따로 둔다.
    한글로 끝나지 않는 이름(영문·숫자)은 '(으)로'."""
    last = str(word or "").strip()[-1:]
    code = ord(last) - 0xAC00 if last else -1
    if not 0 <= code < 11172:
        return "(으)로"
    return "로" if code % 28 in (0, 8) else "으로"


def _evening(plan):
    visit = plan.get("festival_visit")
    return isinstance(visit, dict) and visit.get("position") == "last"


def _middle(plan):
    """코스 중간 축제의 앞 장소 번호(app/leg_modes.middle_after). 없으면 None."""
    from .leg_modes import middle_after

    return middle_after(plan)


def _located(point):
    return point.get("lat") is not None and point.get("lon") is not None


def _saved_legs(plan, c):
    """바뀌지 않는 구간을 다시 조회·추정하지 않도록 저장된 구간을 (출발, 도착, 수단) 열쇠로 모은다.
    코스 중간 축제 뒤 구간은 행사장에서 출발한다. 행사장으로 가는 구간(festival_visit.leg)은 저장 모양이 줄어 있어
    코스 끝 축제와 같이 다시 추정한다. 행사장 좌표는 축제에서 읽는다(festival_time.venue — 출발지 = 행사장인 코스는 출발지 그대로,
    「+ 내 코스에 추가」로 넣은 축제는 출발지와 다른 곳)."""
    from .festival_time import venue
    from .routes import leg_key

    places, legs = plan["places"], plan["legs"]
    points = [c.origin.model_dump(), *places]
    after = _middle(plan)
    rows = {}
    for i, leg in enumerate(legs[: len(places)]):
        a, b = (
            (venue(c) if after is not None and i == after + 1 else points[i]),
            points[i + 1],
        )
        if _located(a) and _located(b) and leg.get("minutes") is not None:
            rows[leg_key(a, b, leg.get("mode") or c.transport)] = leg
    if len(legs) > len(places) and c.home and legs[-1].get("minutes") is not None:
        start = venue(c) if _evening(plan) else places[-1]
        if _located(start):
            rows[leg_key(start, c.home.model_dump(), legs[-1].get("mode") or c.transport)] = legs[
                -1
            ]
    return rows


def _delays(plan, index, delay):
    """새 코스에 반영할 지연 {장소 번호: 분}(지금 코스의 번호 기준). 앞서 반영한 다른 장소의 지연은 그대로 두고, index 에 더한다.
    index 보다 뒤 번호의 지연도 남긴다(2026-11-24 — 예전에는 버려서 다른 번호에서 다시 복구하면 그 지연이 말없이 사라졌다).
    장소를 빼서 번호가 달라지는 것은 _rebuild 가 옮긴다(delay_check.delays_after_removal)."""
    from .delay_check import carried_delays

    new = {k: v for k, v in carried_delays(plan).items() if k != index}
    total = carried_delay(plan, index) + delay
    if total:
        new[index] = total
    return dict(sorted(new.items()))


def _estimate(a, b, c):
    """새로 생기는 구간 하나. 거리 기반 추정만 쓴다(길찾기를 부르지 않는다)."""
    from .planner import route_leg

    conditions = c.model_copy(update={"allow_estimates": True}) if c.mode == "real" else c
    return route_leg(a, b, conditions, c.transport)


def _next_point(plan, c, j, places):
    from .festival_time import venue

    if _middle(plan) == j:
        return venue(c)
    if j + 1 < len(places):
        return places[j + 1]
    if _evening(plan):
        return venue(c)
    if c.return_home and c.home:
        return c.home.model_dump()
    return None


def _previous_point(plan, c, j, places):
    """j 번 장소로 오는 구간의 출발 지점. 첫 장소면 출발지, 코스 중간 축제 바로 뒤 장소면 행사장(festival_time.venue —
    출발지 = 행사장인 코스는 출발지 좌표 그대로)."""
    from .festival_time import venue

    if j == 0:
        return c.origin.model_dump()
    if _middle(plan) == j - 1:
        return venue(c)
    return places[j - 1]


def _leaving_minutes(plan, j):
    """원래 코스에서 j 번 장소를 떠나는 구간의 이동(분). 다음이 없으면 0."""
    places, legs = plan["places"], plan["legs"]
    if _middle(plan) == j:
        return (plan["festival_visit"].get("leg") or {}).get("minutes") or 0
    if j + 1 < len(places):
        return legs[j + 1].get("minutes") or 0
    if _evening(plan):
        return (plan["festival_visit"].get("leg") or {}).get("minutes") or 0
    if len(legs) > len(places):
        return legs[-1].get("minutes") or 0
    return 0


def _place_rows(check):
    """지각 확인 줄 가운데 장소 줄만(코스 중간·끝 축제 줄 festival=True 는 뺀다)."""
    return [row for row in check["rows"] if not row.get("festival")]


def _arrival_base(plan, check, c, j):
    """j 번 장소로 떠나는 시각(분)과 그 도착에 더할 지연. 지연 반영 시간표(check rows)를 따른다.
    코스 중간 축제 바로 뒤 장소면 축제 줄이 끝난 시각(행사장에서 출발)."""
    index = check["index"]
    after = _middle(plan)
    if j == index:
        if index and index - 1 == after:
            # 저장된 축제 시각은 옛 코스에서 '00:30'처럼 접혀 있을 수 있어 지각 확인과 같은 함수로 읽는다(A5).
            departure = festival_minutes(plan["festival_visit"]["departure"], c)
        else:
            departure = (
                minutes(plan["timeline"][index - 1]["departure"]) if index else places_start(c)
            )
        return departure, carried_delay(plan, index) + check["delay"]
    # 남은 첫 장소보다 뒤 장소: 앞 줄을 떠난 시각에, 그 장소에 앞서 반영한 지연을 더한다(지각 확인·evaluate 와 같은 규칙).
    if after is not None and j - 1 == after:
        festival = next(row for row in check["rows"] if row.get("festival"))
        return minutes(festival["departure"]), carried_delay(plan, j)
    return minutes(_place_rows(check)[j - 1 - index]["departure"]), carried_delay(plan, j)


def _changed_legs(updated, j, removed):
    """다시 짠 코스에서 바꾼 자리 앞뒤 구간(새로 생긴 구간)."""
    places, legs = updated["places"], updated["legs"]
    visit = updated.get("festival_visit")
    after = _middle(updated)
    if after is not None:
        # 코스 중간 축제: j 번 장소를 떠나는 구간이 축제 바로 앞이면 행사장으로 가는 구간(festival_visit.leg).
        leaving = (
            lambda k: visit.get("leg")
            if k == after
            else legs[k + 1]
            if k + 1 < len(places)
            else (legs[-1] if len(legs) > len(places) else None)
        )
        if removed:
            # 뺀 자리를 잇는 구간: 뺀 장소가 축제 바로 앞이었으면(이제 축제 앞은 j-1) 행사장으로 가는 구간, 아니면 j 번에 닿는 구간.
            rows = (
                [visit.get("leg")]
                if j - 1 == after
                else [legs[j]]
                if j < len(places)
                else [leaving(j - 1)]
            )
        else:
            rows = [legs[j], leaving(j)]
        return [r for r in rows if r]
    festival_leg = (
        visit.get("leg") if isinstance(visit, dict) and visit.get("position") == "last" else None
    )
    home = legs[-1] if len(legs) > len(places) else None

    def arriving(k):
        # k 번 장소에 닿는 구간. 장소가 끝났으면 코스 끝 축제로 돌아오는 구간, 없으면 귀가 구간.
        return legs[k] if k < len(places) else festival_leg or home

    rows = [arriving(j)] if removed else [legs[j], arriving(j + 1)]
    return [r for r in rows if r]


MIDDLE_REJECTED = "중간 축제 시간에 맞출 수 없어요"


def _middle_target(plan, j, removed, count, extra=None):
    """코스 중간 축제를 다시 짠 코스에서 둘 자리(앞 장소 번호). 중간 축제가 없으면 None, 둘 자리가 없으면 -1.
    바꾸기는 같은 자리, 빼기는 뺀 장소가 축제 앞이면 한 칸 당긴다. 장소 사이가 아니게 되면(맨 앞·끝) 자리가 바뀌므로 둘 수 없다.
    extra=(k, 뺐는지): 묶음 후보가 함께 바꾸거나 뺀 뒤 장소(원래 코스의 번호 k > j). 뺀 장소마다 같은 규칙으로 당긴다."""
    after = _middle(plan)
    if after is None:
        return None
    changes = [(j, removed), *([extra] if extra else [])]
    after -= sum(1 for index, gone in changes if gone and index <= after)
    return after if 0 <= after < count - 1 else -1


def _rejection(plan, c, updated, j, removed, extra=None):
    """다시 짠 코스를 저장하면 안 되는 까닭. 없으면 None.
    extra=(k, 뺐는지): 묶음 후보가 함께 처리한 뒤 장소. 그 장소 앞뒤 구간도 '새로 생긴 구간'으로 본다(구간 길이 검사).
    k 는 j 보다 뒤이고 j 는 빼지 않은 경우에만 쓰므로, 원래 번호 j·k 가 다시 짠 코스에서도 같은 자리를 가리킨다."""
    before, after = plan.get("festival_visit"), updated.get("festival_visit")
    expected = _middle_target(plan, j, removed, len(updated["places"]), extra)
    if expected is not None and (
        not isinstance(after, dict)
        or after.get("position") != "middle"
        or after.get("after") != expected
    ):
        return MIDDLE_REJECTED
    if isinstance(before, dict) or isinstance(after, dict):
        if (
            not isinstance(before, dict)
            or not isinstance(after, dict)
            or before.get("position") != after.get("position")
        ):
            if isinstance(before, dict) and before.get("position") == "last":
                return "코스 끝 축제 시간에 맞출 수 없어요"
            return "축제 방문 시간이 달라져요"
        if before.get("position") not in ("last", "middle") and (
            before["arrival"],
            before["departure"],
        ) != (
            after["arrival"],
            after["departure"],
        ):
            return "맨 앞 축제 시간이 달라져요"
    changed = _changed_legs(updated, j, removed)
    if extra:
        more = _changed_legs(updated, *extra)
        changed = changed + [leg for leg in more if all(leg is not seen for seen in changed)]
    for leg in changed:
        if leg.get("minutes") is None:
            return "이동 시간을 계산하지 못해요"
        if leg["minutes"] > c.max_leg:
            return f"이동이 {leg['minutes']}분으로 정한 {c.max_leg}분보다 길어요"
    if not c.budget_unlimited and updated["total"][1] > c.budget >= plan["total"][1]:
        return f"비용 상한이 예산 {c.budget:,}원을 넘어요"
    if c.max_walk is not None and (updated.get("walking") or 0) > c.max_walk >= (
        plan.get("walking") or 0
    ):
        return f"총 도보가 정한 {c.max_walk}분보다 길어져요"
    return None


def _failure_text(failure, error):
    from .planner import MIDDLE_MISS

    place = failure.get("place")
    reason = failure.get("reason") or error
    if reason == MIDDLE_MISS:
        return MIDDLE_REJECTED
    if place and reason == "영업시간 밖 방문":
        return f"뒤 {place}에서 영업 종료({failure.get('limit')}) 전에 마치지 못해요"
    if place and reason == "마지막 입장 시간 초과":
        return f"뒤 {place}의 마지막 입장({failure.get('limit')})에 늦어요"
    if place and reason == "방문일 휴무":
        return f"{place}{_josa(place, '은', '는')} 방문일에 쉬어요"
    return f"일정을 다시 짤 수 없어요({reason or '확인 필요'})"


def _rebuild(plan, c, places, delays, j, removed, extra=None, failure=None, current=None):
    """(다시 짠 코스, 거절 까닭). evaluate 는 soft — 종료·구간·예산 초과로 실패하지 않고, 위 _rejection 이 바뀐 것만 본다.
    extra=(k, 뺐는지): 묶음 후보가 함께 처리한 뒤 장소(_rejection 참고). failure(dict)를 주면 evaluate 가 실패한 장소·까닭을 거기에 남긴다
    (묶음 후보가 '어느 뒤 장소가 또 늦는지' 알아내는 데 쓴다).
    delays 는 지금 코스(plan)의 번호 기준이다. 장소를 빼면(j 또는 extra) 여기서 새 번호로 옮겨 계산하고, 계산에 쓴 지연과 버린 지연을
    다시 짠 코스의 'delay_recovery'(임시: delays·lost)에 실어 준다 — apply 가 그것으로 기록을 만든다(후보마다 번호가 다를 수 있다).
    current: 지금 다루는 '남은 첫 장소' 번호. 그 장소 자체를 빼는 경우(_skip)에만 준다 — 그 지연은 버리지 않고 다음 장소가 이어받는다."""
    from .delay_check import delays_after_removal
    from .plan_rules import reevaluate
    from .pricing import price_plans
    from .routes import saved_routes

    failure = {} if failure is None else failure
    # 코스 중간 축제는 같은 자리에만 다시 둔다(_middle_target). 둘 자리가 없으면 계산하지 않고 거절한다.
    target = _middle_target(plan, j, removed, len(places), extra)
    if target == -1:
        return None, MIDDLE_REJECTED
    gone = [index for index, was_removed in ((j, removed), extra or (None, False)) if was_removed]
    moved, lost = delays_after_removal(delays, gone, current)
    with saved_routes(_saved_legs(plan, c)):
        updated, error = reevaluate(
            plan, places, c, delays=moved, soft=True, failure=failure, festival_after=target
        )
    if error:
        return None, _failure_text(failure, error)
    if plan.get("course_search"):
        updated["course_search"] = plan["course_search"]
    if plan.get("best_effort"):
        from .best_effort import annotate

        updated = annotate(updated, c)
    from .condition_audit import audit_plan
    from .preferences import hard_blocks

    # 데모 코스는 price_plans 가 조건 확인을 다시 하지 않아 여기서 한 번 더 한다. 저장 단계(save_change)와 같은 기준이다.
    updated = audit_plan(price_plans([updated])[0])
    reason = _rejection(plan, c, updated, j, removed, extra)
    if not reason:
        already = {b["condition"] for b in hard_blocks(plan)}
        new = [b for b in hard_blocks(updated) if b["condition"] not in already]
        if new:
            labels = ", ".join(dict.fromkeys(b["label"] for b in new))
            reason = f"꼭 지킬 조건으로 고른 {labels}{_josa(labels, '을', '를')} 지키지 못해요"
    if reason:
        return None, reason
    updated["delay_recovery"] = dict(
        delays={str(k): v for k, v in moved.items()},
        lost=[[k, v] for k, v in sorted(lost.items())],
    )
    return updated, None


def _over_end(updated, c):
    return max(0, minutes(updated["finish"]) - minutes(c.end))


def _target(check):
    problem = check.get("first_problem")
    if not problem or problem.get("kind") not in PLACE_PROBLEMS:
        return None
    # 문제 장소 = 남은 첫 장소부터 센 장소 줄의 마지막(코스 중간 축제 줄은 세지 않는다).
    return check["index"] + len(_place_rows(check)) - 1


def _same_kind(plan, c, places, target):
    """places 에 없는, target 과 같은 종류의 동네 후보(예약 필요·피할 활동·방문일 휴무·좌표 없음 제외). _options 의 고르는 규칙과 같다.
    (영업시간을 모르는지, 후보) 를 낸다. 영업시간·이동 시간은 여기서 보지 않는다 — 다시 짜 보는 쪽(_rebuild)이 본다."""
    from .quality import same_place

    group, ids, weekday = _group(target), {p["id"] for p in places}, c.visit_date.weekday()
    for p in candidate_pool(plan, c):
        if _group(p) != group or p["id"] in ids or any(same_place(p, q) for q in places):
            continue
        if not _located(p) or p.get("reservation") is True:
            continue
        words = (
            p["name"] + " " + str(p.get("category", "")) + " " + " ".join(p.get("tags") or [])
        ).lower()
        if any(w and w.lower() in words for w in c.avoid):
            continue
        closed_days = p.get("closed_days")
        if str(c.visit_date) in (p.get("closed_dates") or []) or (
            closed_days is not None and weekday in closed_days
        ):
            continue
        unknown = p.get("hours") is None or closed_days is None
        if unknown and c.mode == "real" and not c.allow_estimates:
            continue
        yield unknown, p


def _bundle(plan, c, chosen, delays, j, failure):
    """묶음 후보: j 번을 바꾼 코스(chosen)에서 뒤 장소 한 곳이 또 늦으면(failure), 그 장소까지 함께 처리한 코스를 짠다.
    (다시 짠 코스, also) 또는 (None, None). also = 화면·기록에 쓰는 '함께 처리한 뒤 장소' 설명.
    - 순서: 같은 종류의 다른 곳으로 바꾸기(영업시간 아는 곳 먼저, 가까운 순 MAX_BUNDLE_TRIES 곳) → 모두 안 맞으면 그 장소 빼기.
      장소 수를 되도록 지키려고 바꾸기를 먼저 본다.
    - 한 곳까지만: 함께 처리한 뒤에도 또 다른 장소가 늦으면 _rebuild 가 실패해 이 후보는 내지 않는다(세 곳을 한 번에 바꾸지 않는다).
    - 하지 않는 경우: 뒤 장소가 예약한 곳·고정한 곳(한 곳 규칙과 같음), 실패 까닭이 영업 종료·마지막 입장이 아님(축제·휴무 등),
      이름으로 뒤 장소를 하나로 가릴 수 없음.
    - 바꾸려면: 시도 수는 MAX_BUNDLE_TRIES, 문구는 아래 text 두 줄(tests/test_delay_recovery.py 의 묶음 테스트도 함께)."""
    from .routes import distance

    if failure.get("reason") not in LATER_REASONS:
        return None, None
    found = [k for k in range(j + 1, len(chosen)) if chosen[k]["name"] == failure.get("place")]
    if len(found) != 1:
        return None, None
    k = found[0]
    later = chosen[k]
    locked = {int(i): pid for i, pid in c.locked.items()}
    if later.get("reservation") is True or k in locked:
        return None, None
    name, why = later["name"], _failure_text(failure, None)
    rows = sorted(
        _same_kind(plan, c, chosen, later), key=lambda row: (row[0], distance(later, row[1]))
    )
    for unknown, q in rows[:MAX_BUNDLE_TRIES]:
        both = list(chosen)
        both[k] = q
        updated, _ = _rebuild(plan, c, both, delays, j, False, extra=(k, False))
        if updated:
            new = q["name"]
            text = f"{why}. 그래서 {name}{_josa(name, '을', '를')} {new}{_ro(new)} 함께 바꿔요."
            also = dict(index=k, place=name, action="replace", id=q["id"], name=new)
            return updated, dict(also, hours_known=not unknown, text=text)
    rest = chosen[:k] + chosen[k + 1 :]
    skip_c = c.model_copy(update={"locked": {i - (i > k): pid for i, pid in locked.items()}})
    updated, _ = _rebuild(plan, skip_c, rest, delays, j, False, extra=(k, True))
    if updated:
        text = f"{why}. 그래서 {name}{_josa(name, '은', '는')} 함께 빼요."
        also = dict(index=k, place=name, action="skip", id=None, name=None)
        return updated, dict(also, hours_known=True, text=text)
    return None, None


def _options(plan, check, c, j, delays):
    places = plan["places"]
    target = places[j]
    group = _group(target)
    ids = {p["id"] for p in places}
    from .quality import same_place
    from .routes import distance

    previous = _previous_point(plan, c, j, places)
    following = _next_point(plan, c, j, places)
    before = (plan["legs"][j].get("minutes") or 0) + _leaving_minutes(plan, j)
    departure, extra = _arrival_base(plan, check, c, j)
    weekday = c.visit_date.weekday()
    same_kind, fits = 0, []
    for p in candidate_pool(plan, c):
        if _group(p) != group or p["id"] in ids or any(same_place(p, q) for q in places):
            continue
        if not _located(p):
            continue
        same_kind += 1
        if p.get("reservation") is True:
            continue
        words = (
            p["name"] + " " + str(p.get("category", "")) + " " + " ".join(p.get("tags") or [])
        ).lower()
        if any(w and w.lower() in words for w in c.avoid):
            continue
        closed_days = p.get("closed_days")
        if str(c.visit_date) in (p.get("closed_dates") or []) or (
            closed_days is not None and weekday in closed_days
        ):
            continue
        unknown = p.get("hours") is None or closed_days is None
        # 추정을 허용하지 않은 실제 장소 코스는 운영 자료가 있는 곳만 쓴다(evaluate 의 엄격 규칙과 같다).
        if unknown and c.mode == "real" and not c.allow_estimates:
            continue
        come = _estimate(previous, p, c)
        go = _estimate(p, following, c) if following else None
        if come["minutes"] is None or come["minutes"] > c.max_leg:
            continue
        if go is not None and (go["minutes"] is None or go["minutes"] > c.max_leg):
            continue
        arrival = departure + come["minutes"] + c.transition_buffer_minutes + extra
        # 영업시간을 모르면 planner.ASSUMED_HOURS(종료 판단 없음, A5) — 자정을 넘긴다는 까닭만으로 후보를 버리지 않는다.
        visit = dict(
            p, hours=p.get("hours") or list(ASSUMED_HOURS), stay=p.get("stay") or c.stay_minutes
        )
        visit.setdefault("last_entry", None)
        _, problem = visit_window(visit, arrival)
        if problem:
            continue
        increase = come["minutes"] + (go["minutes"] if go else 0) - before
        fits.append((unknown, increase, distance(target, p), p, come, go))
    fits.sort(key=lambda row: row[:3])
    options, rejected, later = [], {}, None
    # 한 곳만 바꿔서는 안 되던 후보(뒤 장소가 또 늦음 등). 한 곳짜리 후보가 하나도 없을 때만 묶음 후보(_bundle)로 다시 본다.
    pending = []

    def offer(row, updated, also=None):
        unknown, increase, km, p, come, go = row
        hours = p.get("hours")
        options.append(
            dict(
                id=p["id"],
                name=p["name"],
                kind=kind_label(p),
                distance_m=round(km * 1000),
                extra_minutes=increase,
                legs=[come["minutes"], go["minutes"] if go else None],
                start=updated["timeline"][j]["arrival"],
                departure=updated["timeline"][j]["departure"],
                hours_known=not unknown,
                closes=clock(hours[1]) if hours else None,
                finish=updated["finish"],
                over_end=_over_end(updated, c),
                plan=updated,
                # 묶음 후보면 함께 처리한 뒤 장소(_bundle). 한 곳짜리 후보는 None — 화면은 있을 때만 한 줄 더 적는다.
                also=also,
            )
        )

    for row in fits[:MAX_TRIES]:
        if len(options) == MAX_OPTIONS:
            break
        p = row[3]
        chosen = list(places)
        chosen[j] = p
        failure = {}
        updated, reason = _rebuild(plan, c, chosen, delays, j, removed=False, failure=failure)
        if not updated:
            rejected[p["id"]] = reason
            later = later or reason
            pending.append((row, chosen, failure))
            continue
        offer(row, updated)
    if not options:
        for row, chosen, failure in pending:
            if len(options) == MAX_OPTIONS:
                break
            updated, also = _bundle(plan, c, chosen, delays, j, failure)
            if updated:
                rejected.pop(row[3]["id"], None)
                offer(row, updated, also)
    if options:
        note = None
    elif not same_kind:
        note = f"이 동네 후보에 같은 종류({kind_label(target)})의 다른 곳이 없어요."
    elif later:
        note = f"같은 종류로 바꿔도 {later}."
    else:
        note = f"같은 종류({kind_label(target)}) 후보 {same_kind}곳 가운데 그 시각에 열려 있고 가까운 곳이 없어요."
    return options, rejected, note


def _skip(plan, check, c, j, delays):
    places = plan["places"]
    target = places[j]
    if len(places) <= 1:
        return dict(allowed=False, reason="이 장소를 빼면 남는 장소가 없어요."), None
    chosen = places[:j] + places[j + 1 :]
    locked = {int(i): pid for i, pid in c.locked.items()}
    remapped = {i - (i > j): pid for i, pid in locked.items() if i != j}
    skip_c = c.model_copy(update={"locked": remapped})
    updated, reason = _rebuild(
        plan, skip_c, chosen, delays, j, removed=True, current=check["index"]
    )
    name = target["name"]
    if not updated:
        return dict(allowed=False, reason=f"{name}{_josa(name, '을', '를')} 빼도 {reason}."), None
    if j < len(chosen):
        nxt = chosen[j]["name"]
        text = f"{name}{_josa(name, '을', '를')} 빼면 {nxt}에 {updated['timeline'][j]['arrival']}부터 머물고, 끝나는 시각은 {updated['finish']}예요."
    else:
        text = f"{name}{_josa(name, '을', '를')} 빼면 끝나는 시각은 {updated['finish']}예요."
    return dict(
        allowed=True, reason=text, finish=updated["finish"], over_end=_over_end(updated, skip_c)
    ), updated


def _recover(plan, check):
    """(화면에 보낼 복구 안, 내부용 {후보 id 또는 None: 다시 짠 코스}, 거절 까닭). 대상이 없으면 (None, {}, {})."""
    j = _target(check)
    if j is None:
        return None, {}, {}
    from .naver_terms import EXPIRED_CHANGE_MESSAGE, has_expired_places

    c = Conditions.model_validate(plan["conditions"])
    target = plan["places"][j]
    result = dict(
        index=j,
        place=target["name"],
        kind=kind_label(target),
        options=[],
        skip=None,
        note=None,
        blocked=None,
    )
    if has_expired_places(plan):
        result["blocked"] = EXPIRED_CHANGE_MESSAGE
        return result, {}, {}
    if target.get("reservation") is True:
        result["blocked"] = (
            "예약한 곳이라 대신 갈 곳을 고르지 않았어요. 예약처에 연락해 도착 시간을 바꿀 수 있는지 먼저 물어보세요."
        )
        return result, {}, {}
    if j in {int(i) for i in c.locked}:
        result["blocked"] = (
            "고정한 장소라 바꾸거나 빼지 않았어요. 고정을 풀면 대신 갈 곳을 고를 수 있어요."
        )
        return result, {}, {}
    delays = _delays(plan, check["index"], check["delay"])
    options, rejected, note = _options(plan, check, c, j, delays)
    skip, skipped = _skip(plan, check, c, j, delays)
    plans = {o["id"]: o.pop("plan") for o in options}
    if skipped:
        plans[None] = skipped
    result.update(
        options=options, skip=skip, note=note, delays={str(k): v for k, v in delays.items()}
    )
    return result, plans, rejected


def recovery_for(plan, check):
    """지각 확인 응답에 붙일 복구 안(읽기 전용, 저장하지 않음). 고칠 장소가 없으면 None."""
    return _recover(plan, check)[0]


def apply(plan, index, delay, target, replacement_id, owner):
    """고른 복구를 적용해 새 코스로 저장한다. 화면이 본 결과와 지금 계산이 다르면 저장하지 않는다(Refused → 409)."""
    from .delay_check import other_kept_note
    from .plan_changes import save_change

    check = delay_check(plan, index, delay)
    result, plans, rejected = _recover(plan, check)
    if not result:
        raise Refused(
            "지금 계산으로는 늦어서 맞출 수 없는 장소가 없어요. 지각 확인을 다시 눌러 주세요."
        )
    if result["index"] != target:
        raise Refused("지각 확인 결과가 바뀌었어요. 지각 확인을 다시 눌러 주세요.")
    if result["blocked"]:
        raise Refused(result["blocked"])
    name = result["place"]
    if replacement_id is not None:
        option = next((o for o in result["options"] if o["id"] == replacement_id), None)
        if not option:
            reason = rejected.get(replacement_id)
            raise Refused(
                f"고른 곳으로 바꾸면 {reason}. 바꾸지 않았어요."
                if reason
                else "고른 곳은 지금 조건으로는 대신 갈 곳이 아니에요. 지각 확인을 다시 눌러 주세요."
            )
        updated = plans[replacement_id]
        action = f"{name}{_josa(name, '을', '를')} {option['name']}{_ro(option['name'])} 바꾸고"
        # 묶음 후보: 함께 처리한 뒤 장소도 문장에 잇는다('… 바꾸고 C 를 Y 로 바꾸고' / '… 바꾸고 C 를 빼고').
        also = option.get("also")
        if also:
            later = also["place"]
            action += f" {later}{_josa(later, '을', '를')} " + (
                f"{also['name']}{_ro(also['name'])} 바꾸고"
                if also["action"] == "replace"
                else "빼고"
            )
    else:
        if not result["skip"]["allowed"]:
            raise Refused(result["skip"]["reason"])
        updated = plans[None]
        option = None
        action = f"{name}{_josa(name, '을', '를')} 빼고"
    total = int(result["delays"].get(str(index), 0))
    updated = copy.deepcopy(updated)
    # _rebuild 가 실어 둔 임시 기록: 이 코스 계산에 쓴 지연(장소를 뺐으면 새 번호)과, 기준이 된 장소가 빠져 버린 지연.
    used = updated.pop("delay_recovery")
    lost = dict(used["lost"])
    # 지금 다루는 장소(index) 말고 다른 장소에 앞서 반영해 둔 지연은 그대로 둔다 — 남긴 것도, 버린 것도 문장으로 알린다.
    others = [v for k, v in result["delays"].items() if int(k) != index and int(k) not in lost]
    updated["change_reason"] = (
        f"{total}분 늦어진 것을 반영해 {action} 남은 시간표를 다시 계산했어요."
        + other_kept_note(others)
        + "".join(
            f" {plan['places'][k]['name']}에 앞서 반영한 {v}분 지연은 그 장소를 빼서 넣지 않았어요."
            for k, v in lost.items()
        )
    )
    record = dict(
        delays=used["delays"],
        index=index,
        target=result["index"],
        action="replace" if option else "skip",
        place=name,
        replacement=option["name"] if option else None,
    )
    # 묶음 후보로 저장했으면 함께 처리한 뒤 장소도 남긴다(이력·점검용. 지연 계산은 delays 만 본다). 한 곳짜리는 키를 두지 않는다.
    if option and option.get("also"):
        also = option["also"]
        record["also"] = dict(place=also["place"], action=also["action"], replacement=also["name"])
    try:
        saved = save_change(updated, plan, owner, recovery=record)
    except ValueError as exc:
        raise Refused(str(exc)) from exc
    c = Conditions.model_validate(saved["conditions"])
    warnings = []
    over = _over_end(saved, c)
    if over:
        warnings.append(
            f"끝나는 시각 {saved['finish']} — 정한 종료 {c.end}보다 {over}분 늦어요. 그대로 저장했어요."
        )
    # 실제 길찾기 값이 있던 코스(자동차)에서만: 새로 생긴 구간은 길찾기를 새로 부르지 않고 추정했다.
    if any(leg.get("status") == "api" for leg in plan.get("legs") or []):
        warnings.append(
            "바꾼 자리 앞뒤 이동 시간은 길찾기를 새로 부르지 않고 직선거리로 추정했어요. 출발 전에 길찾기로 확인해 주세요."
        )
    if option:
        if not option["hours_known"]:
            warnings.append(
                f"{option['name']}의 영업시간 자료가 없어 연다고 가정했어요. 가기 전에 확인해 주세요."
            )
        also = option.get("also")
        if also and also["action"] == "replace" and not also["hours_known"]:
            warnings.append(
                f"{also['name']}의 영업시간 자료가 없어 연다고 가정했어요. 가기 전에 확인해 주세요."
            )
    saved["delay_recovery_result"] = dict(
        message=f"{updated['change_reason']} 끝나는 시각 {plan.get('finish')} → {saved['finish']}.",
        warnings=warnings,
    )
    return saved
