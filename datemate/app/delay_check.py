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
            now += _leg_minutes(leg, c)
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
    return dict(
        status=status,
        index=index,
        delay=delay,
        carried=carried,
        start_place=places[index]["name"],
        planned_arrival=clock(planned_arrival),
        delayed_arrival=clock(planned_arrival + delay),
        basis=f"{places[index]['name']}의 {planned}에 {delay}분을 더해, 방문 순서를 그대로 두고 다시 계산했어요.",
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
