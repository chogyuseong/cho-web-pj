"""방문 순서 제안(2026-11-23): 같은 장소들을 다른 순서로 돌면 이동이 줄어드는지 보고, 줄어들면 그 순서를 제안한다.

왜: 코스는 장소를 고른 순서대로 저장되는데, A 골목 → B 골목 → A 골목처럼 되돌아가는 동선이 생길 수 있다
(docs/product-improvement-prompts-80.ko.md 14번 '두 장소 사이 되돌아가는 동선 줄이기'). 사용자가 직접 순서를 끌어 옮기는 화면 대신,
서버가 가능한 순서를 모두 계산해 '가장 많이 줄어드는 순서 하나'만 제안한다 — 영업시간·종료 시각을 직접 따져 볼 필요가 없게.

정한 것:
- 비교는 같은 산정 방식으로: 지금 순서와 후보 순서를 모두 '추정 구간'(routes.candidate_routes — 외부 호출 없음)으로 다시 계산해 견준다.
  자동차 코스에 실제 길찾기 값이 저장돼 있어도 비교에는 쓰지 않는다(한쪽만 실제 값이면 줄어든 분이 가짜가 된다).
  저장할 때는 장소 바꾸기와 같이 plan_changes.save_change 가 자동차 구간을 실제 길찾기로 다시 확인한다.
- 움직이지 않는 장소: 고정한 장소(conditions.locked)와 예약한 장소(reservation=True)는 제자리. 나머지끼리만 자리를 바꾼다.
- 후보 순서는 planner.evaluate 를 그대로 통과해야 한다(영업시간·마지막 입장·휴게·종료 시각·구간 상한·예산·총 도보 — 추천과 같은 규칙).
  그리고 조건 확인(condition_audit)에서 '지키지 못함'이 새로 생기면 안 되고, 축제 방문은 있던 대로(자리 종류가 같게) 남아야 한다.
- 이동이 MIN_SAVING 분 이상 줄어드는 순서만 제안한다. 여럿이면 가장 많이 줄어드는 것, 같으면 지금 순서와 가까운 것(번호 순).
- 제안하지 않는 코스(까닭을 글로 돌려준다): 장소 1곳, 보관 기한이 지나 좌표가 지워진 코스, 지각을 반영한 코스(지연이 장소 번호에 묶여 있다),
  구간마다 수단을 바꾼 코스(수단 예외가 (출발, 도착) 짝에 묶여 있어 순서를 바꾸면 사라진다 — 비교가 같은 방식이 아니게 된다).

하지 않는 것: 사용자가 순서를 직접 정하기(끌어 옮기기), 장소를 빼거나 바꾸는 것까지 섞은 제안, 여러 제안 보여 주기.

바꾸려면: 최소 절약 분은 MIN_SAVING, 문구는 이 파일의 글(tests/test_order_suggestion.py 도 함께). 장소는 최대 5곳이라 순서는 많아야 120가지다.
"""

import copy
import itertools

from .models import Conditions
from .planner import minutes

# 이만큼(분)도 줄지 않는 순서는 제안하지 않는다. 추정 구간의 오차(직선거리 × 1.35)보다 작은 차이로 순서를 바꾸라고 하지 않으려는 값.
MIN_SAVING = 5


class Refused(ValueError):
    pass


# 이동 합계는 화면 카드·지도와 같은 정의(점검 보고서 F9). 이 모듈 이름으로도 부를 수 있게 그대로 둔다(테스트·main 이 씀).
from .recommendation_summary import travel_minutes  # noqa: E402,F401


def _fixed(plan, c):
    """제자리에 두는 장소 번호: 고정한 장소와 예약한 장소."""
    locked = {int(i) for i in c.locked}
    return locked | {i for i, p in enumerate(plan["places"]) if p.get("reservation") is True}


def _blocked(plan, c):
    """순서를 견주지 않는 까닭(글). 견줄 수 있으면 None."""
    from .delay_check import carried_delays
    from .naver_terms import EXPIRED_CHANGE_MESSAGE, has_expired_places

    count = len(plan["places"])
    if count < 2:
        return "장소가 한 곳이라 바꿀 순서가 없어요."
    if has_expired_places(plan):
        return EXPIRED_CHANGE_MESSAGE
    if carried_delays(plan):
        return "지각을 반영해 고친 코스는 순서를 견주지 않아요. 지연이 장소 순서에 맞춰 적혀 있어요."
    if c.leg_modes:
        return "구간마다 이동 수단을 따로 정한 코스는 순서를 견주지 않아요. 순서를 바꾸면 그 설정이 사라져요."
    if count - len(_fixed(plan, c)) < 2:
        return "고정했거나 예약한 장소를 빼면 자리를 바꿀 곳이 없어요."
    return None


def _unmet(plan):
    return {r["condition"] for r in plan.get("condition_checks") or [] if r["state"] == "unmet"}


def _festival_kind(plan):
    visit = plan.get("festival_visit")
    return visit.get("position") if isinstance(visit, dict) else None


def _find(plan):
    """(제안 dict 또는 None, 제안이 없는 까닭). 제안 dict 의 plan 은 다시 짠 코스(저장 전)."""
    from .condition_audit import audit_plan
    from .festival_time import change_note
    from .leg_modes import middle_after
    from .plan_rules import reevaluate
    from .routes import candidate_routes

    # 지금 코스에 실제로 있는 구간의 수단 예외만 본다(plan_rules.settle_leg_modes). 2026-11-24 전에 식사를 끼워 저장한 코스에는
    # 끊긴 구간의 예외가 조건에 남아 있을 수 있다 — 그런 코스를 '구간마다 수단을 따로 정한 코스'로 거절하지 않는다. plan 은 바꾸지 않는다.
    from .plan_rules import settle_leg_modes

    c = settle_leg_modes(dict(plan, conditions=dict(plan["conditions"])))
    reason = _blocked(plan, c)
    if reason:
        return None, reason
    places = plan["places"]
    soft = bool(plan.get("best_effort"))
    fixed = _fixed(plan, c)
    movable = [i for i in range(len(places)) if i not in fixed]
    with candidate_routes():
        # 지금 순서도 같은 방식(추정 구간)으로 다시 계산한 값을 기준으로 삼는다.
        # 다시 계산은 plan_rules.reevaluate 로(장소 수를 검사하지 않는다 — 장소를 뺀 코스도 같은 장소끼리 순서를 견줄 수 있다).
        # 지각을 반영한 코스는 위 _blocked 가 이미 걸렀으므로 넣을 지연이 없다(delays={}).
        base, error = reevaluate(
            plan, places, c, delays={}, soft=soft, festival_hint=middle_after(plan)
        )
        if error:
            return None, "지금 순서를 같은 방식으로 다시 계산하지 못해 견주지 않았어요."
        base = audit_plan(base, c)
        before, unmet, kind = travel_minutes(base), _unmet(base), _festival_kind(base)
        latest = max(minutes(c.end), minutes(base["finish"]))
        best = None
        for arrangement in itertools.permutations(movable):
            if list(arrangement) == movable:
                continue
            order = list(range(len(places)))
            for slot, source in zip(movable, arrangement):
                order[slot] = source
            candidate, error = reevaluate(plan, [places[i] for i in order], c, delays={}, soft=soft)
            if error:
                continue
            saved = before - travel_minutes(candidate)
            # 덜 줄어드는 순서는 조건 확인까지 가지 않고 건너뛴다(조건 확인이 계산의 대부분이다).
            if saved < MIN_SAVING or (best and (saved, [-i for i in order]) <= best[0]):
                continue
            # 조건이 느슨한 코스(best_effort)는 evaluate 가 종료 시각을 막지 않으므로 여기서 본다: 지금보다 늦게 끝나면 안 된다.
            if _festival_kind(candidate) != kind or minutes(candidate["finish"]) > latest:
                continue
            candidate = audit_plan(candidate, c)
            if _unmet(candidate) - unmet:
                continue
            best = ((saved, [-i for i in order]), order, candidate)
    if not best:
        return None, f"지금 순서가 이동이 가장 짧거나, 다른 순서로는 {MIN_SAVING}분 넘게 줄지 않아요."
    (saved, _), order, candidate = best
    return dict(
        order=[places[i]["id"] for i in order],
        names=[places[i]["name"] for i in order],
        saved_minutes=saved,
        travel_before=before,
        travel_after=before - saved,
        finish_before=base["finish"],
        finish_after=candidate["finish"],
        # 순서를 바꾼 탓에 축제 자리가 달라지면 그 안내(같은 자리 종류 안에서 '몇 번째 장소 뒤'가 바뀌는 경우).
        festival_change=change_note(base.get("festival_visit"), candidate.get("festival_visit")),
        plan=candidate,
    ), None


def suggest(plan):
    """화면에 보낼 순서 제안(읽기 전용, 저장하지 않음). {'suggestion': dict 또는 None, 'reason': 제안이 없는 까닭 또는 None}."""
    found, reason = _find(plan)
    if found:
        found = {key: value for key, value in found.items() if key != "plan"}
    return dict(suggestion=found, reason=reason, basis="지금 순서와 새 순서 모두 직선거리 기반 추정으로 견줬어요.")


def apply(plan, order, owner):
    """제안한 순서로 바꿔 새 코스로 저장한다. 화면이 본 순서와 지금 계산이 다르면 저장하지 않는다(Refused → 409)."""
    from .festival_time import set_change_note
    from .plan_changes import change_delta, save_change
    from .preferences import hard_blocks
    from .pricing import price_plans

    found, _ = _find(plan)
    if not found or found["order"] != list(order):
        raise Refused("순서 제안이 바뀌었어요. 순서 제안을 다시 열어 주세요.")
    updated = copy.deepcopy(found["plan"])
    if plan.get("course_search"):
        updated["course_search"] = plan["course_search"]
    if plan.get("best_effort"):
        from .best_effort import annotate

        updated = annotate(updated, Conditions.model_validate(plan["conditions"]))
    updated = price_plans([updated])[0]
    if hard_blocks(updated) and not hard_blocks(plan):
        raise Refused("필수 조건을 충족하지 않아 순서를 바꾸지 않았어요.")
    updated["delta"] = change_delta(plan, updated)
    updated["change_reason"] = (
        f"방문 순서를 바꿔 이동을 추정 기준 {found['saved_minutes']}분 줄였어요. 시간·비용을 다시 계산했어요."
    )
    set_change_note(updated, plan)
    try:
        return save_change(updated, plan, owner)
    except ValueError as exc:
        raise Refused(str(exc)) from exc
