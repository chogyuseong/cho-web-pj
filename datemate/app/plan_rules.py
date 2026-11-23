"""이미 있는 코스를 다시 계산·저장할 때 모든 변경 경로가 함께 쓰는 규칙 (2026-11-24).

왜 한 곳에 모았나: 80·81·82차 배포와 2026-11-24 전체 점검의 A1~A4 가 모두 '변경 경로 하나가 규칙 하나를 빠뜨림'이었다
(수단 바꾸기가 지연을 빠뜨림 → 장소 바꾸기·레저 → 식사·합의 → 지각 확인 자신, 그리고 '빼고 진행' 뒤의 장소 수, 식사 초안의 수단 예외).
같은 일이 경로마다 복사돼 있으면 새 경로를 더할 때 또 빠뜨린다. 설계: docs/superpowers/specs/2026-11-24-delay-and-place-count-design.md

여기 있는 것
- reevaluate: '저장된 코스 + 새 장소 목록 → 다시 계산한 시간표'. 저장된 지연을 다시 넣고, 계산에만 늦춘 종료 시각을 되돌리고,
  장소 수를 검사하지 않는다. 변경 경로는 planner.evaluate 를 직접 부르지 않고 이것만 부른다
  (tests/test_delay_and_place_count.py 의 test_only_the_planner_and_plan_rules_call_evaluate_directly 가 지킨다).
- settle_leg_modes: 저장·초안 직전에 지금 코스에 없는 구간의 수단 예외를 지운다(plan_changes.save_change 와 experience.make_draft 가 같이 쓴다).
- count_for: 사용자가 장소 수를 직접 정하는 초안(식사 추가·교체)의 conditions.count.

장소 수와 conditions.count 의 규칙(이 파일이 기준)
- conditions.count 는 '사용자가 요청한 장소 수'다. 계산이 지켜야 하는 값이 아니다.
- 새 추천(planner.recommend)만 장소 수 = count 를 요구한다.
- 이미 있는 코스를 다시 계산할 때는 장소 수를 검사하지 않는다(reevaluate). 지각 복구의 '빼고 진행'은 count 를 그대로 두어
  조건 확인(condition_audit)이 '요청은 3곳이지만 2곳'을 계속 알린다 — 그 코스에서도 장소 바꾸기·레저 후보가 나와야 한다.
- 식사 추가·교체는 사용자가 장소 수를 직접 정한 것이라 count 를 장소 수에 맞춘다. 다만 모델 범위(2~5) 안에서만(count_for) —
  1곳 남은 코스의 식사 교체는 count 2·장소 1곳으로 두고 조건 확인이 차이를 알린다.

지연을 적은 장소 번호를 옮기는 규칙(번호가 달라지는 변경마다 다르다)은 app/delay_check.py 의 delays_after_insert·delays_after_removal 과
experience._with_carried_delay(장소 id 로 옮김)에 있다. 기록을 이어 붙이는 것(kept_record·moved_record)도 delay_check 에 있다.
"""

from .delay_check import carried_delays, delayed_conditions
from .models import Conditions

# reevaluate(delays=CARRIED): source 의 지각 기록에 적힌 지연을 그대로 넣는다(기본값). 번호가 달라지는 변경은 새 번호 기준 dict 를 준다.
CARRIED = object()

# models.Conditions.count 의 범위(ge=2, le=5).
MIN_COUNT, MAX_COUNT = 2, 5


def reevaluate(source, places, c, *, delays=CARRIED, late_end=False, **options):
    """저장된 코스 source 를 바탕으로 장소 목록 places 의 시간표를 조건 c 로 다시 계산한다. (코스, 오류) — planner.evaluate 와 같은 모양.

    - 지연: source 의 지각 기록(delay_recovery.delays)을 다시 넣는다. 넣지 않으면 시간표가 말없이 '늦지 않은 것'으로 돌아간다.
      장소 번호가 달라지는 변경(식사 추가·합의 코스·지각 복구의 빼기)은 새 번호 기준 {장소 번호: 분} 을 delays 로 준다.
      지연을 넣지 않아야 하면 delays={} (예: 지각 기록을 이어 가지 않는 재확인).
    - late_end=True: 지각 탓에 이미 종료 시각을 넘긴 코스는 '지금 끝나는 시각'까지 허용해 계산하고(delay_check.delayed_conditions),
      돌려주는 코스의 conditions.end 는 원래 값으로 둔다. 종료 시각을 엄격히 보는 계산(장소 바꾸기·레저 후보·자동차 재확인·합의 코스)이 켠다.
      soft 계산(수단 바꾸기·식사 초안·지각 복구)은 종료를 막지 않으므로 켜지 않는다 — 켜면 축제 창 계산(festival_time 이 c.end 를 본다)이 달라진다.
    - 장소 수: 검사하지 않는다(evaluate count_free). 까닭은 이 파일 맨 위.
    - options: planner.evaluate 의 나머지 인자(soft·verify_routes·route_fallback·failure·festival_after·festival_hint)."""
    from .planner import evaluate

    if delays is CARRIED:
        delays = carried_delays(source)
    working = delayed_conditions(source, c) if late_end else c
    plan, error = evaluate(places, working, delays=delays or None, count_free=True, **options)
    if plan and working is not c:
        # 계산에만 늦춘 종료 시각을 원래 값으로(저장되는 조건을 바꾸지 않는다).
        plan["conditions"]["end"] = c.end
    return plan, error


def count_for(places):
    """사용자가 장소 수를 직접 정한 초안(식사 추가·교체)의 conditions.count: 장소 수, 다만 모델 범위 안에서."""
    return min(MAX_COUNT, max(MIN_COUNT, len(places)))


def settle_leg_modes(plan):
    """plan['conditions'].leg_modes 에서 지금 코스에 없는 구간의 수단 예외를 지우고, 정리한 Conditions 를 돌려준다.
    예외는 (출발 id, 도착 id) 짝에 묶여 있다(app/leg_modes.py). 장소를 바꾸거나 끼우거나 순서를 바꿔 끊긴 구간은 이미 기본 수단으로
    계산됐으므로, 예외가 조건에 남으면 틀린 정보가 된다 — 순서 제안이 '구간마다 수단을 따로 정한 코스'라며 거절하고,
    남은 예외가 자동차면 자동차 구간이 없는데도 길찾기 재조회·재요청 제한이 걸린다(2026-11-24 점검 A3).
    plan 은 다시 계산이 끝난 코스여야 한다(구간·축제 자리가 정해진 뒤). 저장 경로 둘이 모두 부른다:
    plan_changes.save_change(장소·수단·레저·순서·지각 복구)와 experience.make_draft(식사·합의 초안)."""
    from .leg_modes import endpoints, festival_pair

    conditions = Conditions.model_validate(plan["conditions"])
    if not conditions.leg_modes:
        return conditions
    current = set(endpoints(plan)) | ({festival_pair(plan)} - {None})
    kept = [m for m in conditions.leg_modes if (m.from_, m.to) in current]
    if len(kept) != len(conditions.leg_modes):
        conditions = conditions.model_copy(update={"leg_modes": kept})
        plan["conditions"]["leg_modes"] = [m.model_dump() for m in kept]
    return conditions
