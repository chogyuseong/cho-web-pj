"""'지금 N분 늦으면 어디서 처음 문제가 생기는가' 읽기 전용 확인 (docs/product-priorities-deep-review.ko.md 5번).

사용자가 고른 코스에서 남은 첫 장소(index)와 지연 분(delay)을 받아, 방문 순서를 그대로 둔 채 남은 시간표를 다시 평가한다.
- 지연의 기준: 선택한 장소의 '원래 도착 예정 시각' = 앞 장소를 떠난 시각(첫 장소면 출발 시각) + 그 구간 이동 + 전환 여유.
  저장된 timeline 의 arrival 은 개점 대기·휴게 시간을 반영한 '이용 시작'이라 기준으로 쓰지 않는다.
- 그 도착 시각에 지연을 더하고, 남은 장소마다 기존 플래너 규칙(app.planner.visit_window: 개점 대기, 휴게 시간,
  마지막 입장, 영업 종료)을 차례로 적용한다. 모든 시각에 같은 지연을 더하지 않는다(개점 전 대기가 지연을 흡수할 수 있다).
- 이동 시간은 코스에 저장된 구간 값을 그대로 쓴다(새로 조회하지 않는다). 추정 구간이면 근거와 함께 알린다.
- 코스 끝에 둔 저녁 축제(plan['festival_visit'].position == 'last', app/festival_time.py)가 있으면 저장된 돌아오는 구간과
  운영 시간으로 축제 줄을 더한다(개막 전이면 기다리고, 운영 종료를 넘기면 문제). 코스 중간 축제(position 'middle', after=i)면
  장소 i 줄 바로 뒤에 같은 축제 줄(festival=True)을 넣고, 장소 i+1 은 축제가 끝난 때 행사장에서 출발한다.
- 귀가가 있으면 귀가 구간을 더하고, 끝으로 일정 종료 시각(conditions.end)과 비교한다.
- 영업시간·휴무 자료가 없는 장소는 추천 계산(planner.evaluate, 실제 장소 + 추정 허용)과 같은 규칙으로 '하루 종일 연다'고 가정해
  계속 계산하고, 그 장소를 pending(먼저 확인할 것)과 그 줄의 state='unchecked' 로 알린다.
  예전(2026-11-19 오전 배포)에는 그 장소에서 계산을 멈췄는데, 실제 장소는 대부분 영업시간 자료가 없어 첫 장소에서 바로
  '판단 보류'만 나와 기능이 쓸모없었다(사용자 신고 스크린샷). status: 문제가 있으면 'problem', 문제는 없지만 가정한 곳이 있으면
  'unknown'(끝나는 시각은 계산함), 모두 자료가 있고 문제가 없으면 'ok'.
- 지각 복구(app/delay_recovery.py)로 저장한 코스는 그때 반영한 지연을 plan['delay_recovery'].delays({장소 번호: 분})에 남긴다.
  그 장소를 남은 첫 장소로 고르면 원래 도착 예정에 그 지연을 더한 '지금 시간표의 도착 예정'을 기준으로 삼는다(carried_delay).
  남은 첫 장소보다 뒤 번호에 적힌 지연도 그 장소에 닿을 때 더한다(planner._evaluate 의 delays 와 같은 규칙, 2026-11-24).
  더하지 않으면 '더 늦었는데 더 일찍 끝난다'고 답한다 — 0분으로 확인하면 어느 번호에서 시작하든 지금 시간표가 그대로 나와야 한다.
원본 코스·공유본·방문 기록을 바꾸지 않는다(저장하지 않는다). 대신 갈 곳·빼고 진행은 app/delay_recovery.py 가 따로 계산한다.
"""

from .festival_time import hours_range, places_start
from .leg_modes import middle_after
from .models import Conditions
from .planner import clock, minutes, visit_window

MAX_DELAY = 180


def _leg_minutes(leg, c):
    return (leg.get("minutes") or 0) + leg.get("buffer_minutes", c.transition_buffer_minutes)


def carried_delay(plan, index):
    """지각 복구로 저장한 코스에서 index 번 장소 도착에 이미 반영한 지연(분). 없으면 0."""
    record = plan.get("delay_recovery")
    delays = record.get("delays") if isinstance(record, dict) else None
    try:
        return max(0, int((delays or {}).get(str(index), 0)))
    except (TypeError, ValueError):
        return 0


def carried_delays(plan):
    """지각 복구로 저장한 코스가 이미 반영한 지연 전체 {장소 번호(int): 분}. 기록이 없거나 값이 이상하면 {}.
    planner.evaluate(delays=…) 에 그대로 넘길 수 있는 모양이다. 수단 바꾸기(app/leg_modes.apply_change)가 시간표를 다시 짤 때
    이 지연을 다시 넣어, 수단을 바꿨다고 지연이 말없이 사라지지 않게 한다(2026-11-23)."""
    record = plan.get("delay_recovery")
    delays = record.get("delays") if isinstance(record, dict) else None
    out = {}
    for key, value in (delays or {}).items():
        try:
            index, late = int(key), int(value)
        except (TypeError, ValueError):
            continue
        if late > 0 and 0 <= index < len(plan.get("places") or []):
            out[index] = late
    return out


def kept_record(plan, how):
    """지연을 넣어 다시 계산한 코스에 이어 붙일 기록. 지연 기록이 없는 코스면 None(= 예전과 같은 동작).
    how: 'transport'(수단 바꾸기) 또는 'place'(같은 자리의 장소를 다른 곳으로 바꾸기 — 장소 번호가 그대로인 변경만).
    장소 번호가 달라지는 변경(식사 추가·합의 코스)은 moved_record 를 쓴다.
    kept 는 '이 코스는 지각 반영이 아니라 그 뒤의 다른 변경으로 만들어졌다'는 표시다 — 화면(static/plan-detail.js)의 되돌리기 단추 문구와
    저장(plan_changes.save_change)의 자동차 재확인 여부가 이 값을 본다. 80차에 저장된 값 True 는 'transport' 와 같게 읽는다."""
    return dict(plan["delay_recovery"], kept=how) if carried_delays(plan) else None


def moved_record(plan, delays, how):
    """장소 번호가 달라지는 변경(식사 추가 'meal'·합의 코스 'agreement')에서 지연을 새 번호로 옮겨 이어 붙일 기록.
    delays: 새 코스 기준 {장소 번호: 분}(비면 None — 이어 가지 않음). delays 만 새 번호로 바꾸고, index·target·place·also 는
    지각 복구 당시의 이력으로 그대로 둔다(지연 계산·지각 확인은 delays 만 본다). 설계: docs/superpowers/specs/2026-11-23-delay-kept-meal-consensus-design.md"""
    if not delays:
        return None
    return dict(
        plan["delay_recovery"], delays={str(k): v for k, v in sorted(delays.items())}, kept=how
    )


def kept_note(plan):
    """지연을 그대로 둔 변경의 안내 문장 끝에 붙이는 글(앞에 빈칸 포함). 지연 기록이 없으면 빈 글.
    기록은 보통 한 장소뿐이다. 다른 번호에서 다시 복구해 여러 장소에 적혀 있으면(2026-11-24 부터 남는다) 장소 순서대로 모두 적는다."""
    return _kept_text("앞서 반영한", list(carried_delays(plan).values()))


def _kept_text(lead, values):
    """'{lead} N분 지연은 그대로 뒀어요.'(앞에 빈칸 포함). 여럿이면 건수와 분을 모두 적는다. 없으면 빈 글."""
    if not values:
        return ""
    if len(values) == 1:
        return f" {lead} {values[0]}분 지연은 그대로 뒀어요."
    return f" {lead} 지연 {len(values)}건({'·'.join(f'{v}분' for v in values)})은 그대로 뒀어요."


def other_kept_note(values):
    """지각 복구가 지금 다루는 장소 말고 다른 장소에 남겨 둔 지연의 안내(app/delay_recovery.apply)."""
    return _kept_text("다른 장소에 앞서 반영한", list(values))


def delays_after_insert(delays, at):
    """장소 하나를 번호 at 자리에 끼운 뒤의 지연 {장소 번호: 분}. 그 자리부터 번호가 하나씩 밀리므로 at 이상인 번호를 +1 한다
    (지연은 그 장소를 따라간다 — 식사 추가, 82차). at 이 None 이면(같은 자리 교체) 그대로."""
    return {k + (at is not None and at <= k): v for k, v in delays.items()}


def delays_after_removal(delays, removed, current=None):
    """장소를 뺀 뒤의 지연. (새 번호 기준 {장소 번호: 분}, 버린 지연 {원래 번호: 분}). 2026-11-24
    removed: 뺀 장소의 원래 번호들. current: 지각 복구가 지금 다루는 '남은 첫 장소' 번호(없으면 None).
    - 뺀 장소보다 뒤 번호의 지연은 번호를 하나 당긴다(지연은 그 장소를 따라간다 — 식사 추가와 같은 규칙).
    - 뺀 장소에 앞서 적어 둔 지연은 버린다. 분은 '그 장소의 도착 예정'에 붙은 상대값이라 장소가 빠지면 기준이 없다
      (82차 합의 코스와 같은 판단 — 다른 장소에 붙이면 지연을 지어내는 셈). 버린 것은 호출한 쪽이 문장으로 알린다.
    - 다만 지금 다루는 지연(current)은 그 장소를 빼도 번호에 남긴다: 사용자는 지금 그만큼 늦었고, 그 자리로 당겨진 다음 장소에
      그만큼 늦게 닿는다(지각 복구가 처음부터 써 온 규칙). 다음 장소에도 지연이 있으면 더한다."""
    moved, lost = dict(delays), {}
    for gone in sorted(removed, reverse=True):
        if gone != current and gone in moved:
            lost[gone] = moved.pop(gone)
        shifted = {}
        for k, v in moved.items():
            shifted[k - (k > gone)] = shifted.get(k - (k > gone), 0) + v
        moved = shifted
    return dict(sorted(moved.items())), lost


def delayed_conditions(plan, c):
    """지연이 든 코스를 다시 계산할 때 쓰는 조건. 지각 탓에 이미 종료 시각(c.end)을 넘긴 코스면 종료를 지금 끝나는 시각으로 본다.
    - 왜: 지연을 넣으면 어떤 후보든 '전체 일정 시간 초과'로 떨어져 장소 바꾸기 후보가 0곳이 된다. 지각 복구도 종료 초과는 막지 않고 알린다.
    - 그래서: '지금보다 더 늦게 끝나지 않는' 후보까지만 낸다. 넘기지 않은 코스·지연 기록이 없는 코스는 c 그대로.
    - 주의: 이 조건으로 계산한 코스의 conditions.end 는 원래 값으로 되돌려야 한다(저장되는 조건을 바꾸지 않는다).
      직접 부르지 말고 app/plan_rules.reevaluate(late_end=True) 를 쓸 것 — 넣기와 되돌리기를 거기서 함께 한다(2026-11-24).
      끝나는 시각이 자정을 넘겨 'HH:MM' 으로 못 적는 코스는 그대로 둔다(그런 코스는 예전처럼 후보가 안 나올 수 있다)."""
    if not carried_delays(plan):
        return c
    try:
        if minutes(plan["finish"]) > minutes(c.end):
            return c.model_copy(update={"end": plan["finish"]})
    except (KeyError, TypeError, ValueError):
        pass
    return c


def delay_check(plan, index, delay):
    c = Conditions.model_validate(plan["conditions"])
    places, legs, timeline = plan["places"], plan["legs"], plan["timeline"]
    if not 0 <= index < len(places):
        raise ValueError("남은 첫 장소를 다시 골라 주세요.")
    if not 0 <= delay <= MAX_DELAY:
        raise ValueError(f"지연은 0~{MAX_DELAY}분 사이로 입력해 주세요.")
    if len(legs) < len(places) or any(
        legs[i].get("minutes") is None for i in range(index, len(places))
    ):
        raise ValueError("이 코스는 구간 이동 시간이 저장돼 있지 않아 다시 계산할 수 없어요.")
    # 첫 장소의 출발 시각: 축제를 맨 앞에 고정한 코스는 축제가 끝난 때(app/festival_time.py), 아니면 코스 시작.
    # 코스 중간 축제 바로 뒤 장소면 축제가 끝난 때 행사장에서 떠난다.
    visit = plan.get("festival_visit")
    after = middle_after(plan)
    if index and index - 1 == after:
        previous_departure = minutes(visit["departure"])
    else:
        previous_departure = minutes(timeline[index - 1]["departure"]) if index else places_start(c)
    carried = carried_delay(plan, index)
    planned_arrival = previous_departure + _leg_minutes(legs[index], c) + carried
    now = planned_arrival + delay
    rows, pending, estimated, no_last_entry = [], [], [], []
    first_problem = None
    # 남은 첫 장소보다 뒤 번호에 앞서 반영한 지연(계산에 넣은 것만). 근거 문장에 적는다.
    carried_later = []

    def festival_row(back, origin_name):
        """행사장으로 가는 구간(back)을 지나 축제 줄을 더한다. (줄, 끝난 시각, 문제 또는 None)."""
        arrival = now + _leg_minutes(back, c)
        if back.get("status") != "api":
            estimated.append(
                dict(
                    leg=f"{origin_name} → {visit['title']} 행사장",
                    minutes=back.get("minutes"),
                    basis=back.get("source") or "거리 기반 추정",
                )
            )
        _, window = hours_range(visit.get("hours"))
        start = max(arrival, window[0]) if window else arrival
        row = dict(
            name=f"축제 · {visit['title']}",
            arrival=clock(arrival),
            start=clock(start),
            departure=clock(start + visit["stay"]),
            wait=start - arrival,
            original_start=visit["arrival"],
            shift=start - minutes(visit["arrival"]),
            stay=visit["stay"],
            stay_assumed=False,
            state="ok",
            missing=[],
            festival=True,
        )
        problem = None
        if window and start + visit["stay"] > window[1]:
            over = start + visit["stay"] - window[1]
            row.update(
                state="problem",
                reason="축제 운영 시간 안에 마치지 못해요",
                limit=clock(window[1]),
                over=over,
            )
            problem = dict(
                place=row["name"],
                time=row["start"],
                reason=row["reason"],
                kind="festival",
                limit=row["limit"],
                over=over,
            )
        return row, start + visit["stay"], problem

    for j in range(index, len(places)):
        p = dict(places[j])
        leg = legs[j]
        if j > index:
            # 이 장소에 앞서 반영한 지연이 있으면 여기서 더한다(planner._evaluate 가 delays.get(position) 을 더하는 자리와 같다).
            later = carried_delay(plan, j)
            now += _leg_minutes(leg, c) + later
            if later:
                carried_later.append(dict(index=j, place=p["name"], minutes=later))
        if leg.get("status") != "api":
            estimated.append(
                dict(
                    leg=f"{leg.get('origin', '')} → {leg.get('destination', p['name'])}",
                    minutes=leg.get("minutes"),
                    basis=leg.get("source") or "거리 기반 추정",
                )
            )
        original_start = minutes(timeline[j]["arrival"])
        missing = [
            label
            for key, label in (("hours", "영업시간"), ("closed_days", "휴무일"))
            if p.get(key) is None
        ]
        if missing:
            # 자료가 없으면 planner.evaluate 처럼 '하루 종일 연다·휴무 없음'으로 가정하고 계속 간다(개점 대기·영업 종료 판단 없음).
            pending.append(dict(place=p["name"], fields=missing))
            if p.get("hours") is None:
                p["hours"] = [0, 1440]
        stay_assumed = p.get("stay") is None
        p["stay"] = p.get("stay") or c.stay_minutes
        if p.get("last_entry") is None:
            no_last_entry.append(p["name"])
        start, problem = visit_window(p, now)
        row = dict(
            name=p["name"],
            arrival=clock(now),
            start=clock(start),
            departure=clock(start + p["stay"]),
            wait=start - now,
            original_start=timeline[j]["arrival"],
            shift=start - original_start,
            stay=p["stay"],
            stay_assumed=stay_assumed,
            state="problem" if problem else "unchecked" if missing else "ok",
            missing=missing,
        )
        if problem:
            limit = problem["limit"]
            row.update(
                reason=problem["reason"],
                limit=clock(limit),
                over=start - limit
                if problem["kind"] == "last_entry"
                else start + p["stay"] - limit,
            )
            first_problem = dict(
                place=p["name"],
                time=clock(start),
                reason=problem["reason"],
                kind=problem["kind"],
                limit=clock(limit),
                over=row["over"],
            )
            rows.append(row)
            break
        rows.append(row)
        now = start + p["stay"]
        # 코스 중간 축제: 이 장소 뒤에 행사장으로 가서 축제를 본다(festival_visit.leg). 다음 장소 구간(legs[j+1])은 행사장에서 출발.
        if j == after and isinstance(visit.get("leg"), dict):
            row, now, first_problem = festival_row(visit["leg"], p["name"])
            rows.append(row)
            if first_problem:
                break
    if (
        not first_problem
        and isinstance(visit, dict)
        and visit.get("position") == "last"
        and visit.get("leg")
    ):
        row, now, first_problem = festival_row(visit["leg"], places[-1]["name"])
        rows.append(row)
    finish = None
    if not first_problem:
        if c.return_home and len(legs) > len(places):
            now += _leg_minutes(legs[-1], c)
            if legs[-1].get("status") != "api":
                estimated.append(
                    dict(
                        leg=f"{legs[-1].get('origin', '')} → {legs[-1].get('destination', '귀가')}",
                        minutes=legs[-1].get("minutes"),
                        basis=legs[-1].get("source") or "거리 기반 추정",
                    )
                )
        finish = clock(now)
        if now > minutes(c.end):
            first_problem = dict(
                place="일정 종료",
                time=finish,
                reason="정한 종료 시각을 넘겨요",
                kind="end",
                limit=c.end,
                over=now - minutes(c.end),
            )
    status = "problem" if first_problem else "unknown" if pending else "ok"
    planned = (
        f"도착 예정 시각 {clock(planned_arrival)}(앞서 {carried}분 늦음을 반영해 저장한 시각)"
        if carried
        else f"원래 도착 예정 시각 {clock(planned_arrival)}"
    )
    later_note = (
        " 뒤 장소에 앞서 반영한 지연("
        + ", ".join(f"{row['place']} {row['minutes']}분" for row in carried_later)
        + ")도 그대로 넣었어요."
        if carried_later
        else ""
    )
    return dict(
        status=status,
        index=index,
        delay=delay,
        carried=carried,
        carried_later=carried_later,
        start_place=places[index]["name"],
        planned_arrival=clock(planned_arrival),
        delayed_arrival=clock(planned_arrival + delay),
        basis=f"{places[index]['name']}의 {planned}에 {delay}분을 더해, 방문 순서를 그대로 두고 다시 계산했어요."
        + later_note,
        rows=rows,
        first_problem=first_problem,
        pending=pending,
        finish=finish,
        original_finish=plan.get("finish"),
        end=c.end,
        estimated_legs=estimated,
        no_last_entry=no_last_entry,
        read_only="이 확인은 코스·공유본·방문 기록을 바꾸지 않아요.",
    )
