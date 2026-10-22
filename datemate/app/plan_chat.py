"""Answer schedule questions from the saved plan, without inventing live facts."""
import re
import math
from .routes import distance


def movement_advice(plan):
    """Compare modes on the same estimated distance, not a driving route as a walking route."""
    c=plan['conditions']
    points=[c['origin'],*plan['places']]
    if c.get('return_home') and c.get('home'):points.append(c['home'])
    lines=['이동 시간 비교: 도보 평균속도 시속 4km, 자차 평균속도 시속 25km를 계산 기준으로 가정했어요.']
    for i,leg in enumerate(plan['legs']):
        a,b=points[i:i+2] if i+1<len(points) else (None,None)
        if a and b and all(p.get(k) is not None for p in (a,b) for k in ('lat','lon')):
            km=distance(a,b)*(1 if c['mode']=='demo' else 1.35)
        else:
            lines.append(f"· {leg['origin']} → {leg['destination']}: 위치 자료가 부족해 도보·자차 시간을 비교할 수 없어요.")
            continue
        walk=math.ceil(km/4*60);car=math.ceil(km/25*60)
        lines.append(f"· {leg['origin']} → {leg['destination']}: 도보 약 {walk}분 소요(자차 이용 시 약 {car}분)")
        if walk>=30:lines.append('  도보 이동이 30분 이상인 구간이에요. 편한 신발과 휴식을 준비하고, 비·더위에는 다른 이동수단도 고려해 주세요.')
    lines.append(('가상 장소의 직선거리' if c['mode']=='demo' else '장소 간 직선거리 × 1.35의 추정 거리')+'로 비교한 참고값이에요. 실제 보행·차량 경로는 다를 수 있고, 신호 대기·경사·교통 정체·주차 시간은 제외했어요. 길찾기로 실제 경로를 확인해 주세요.')
    lines.append('위 시간 비교로 현재 일정의 이동수단이나 시간표를 자동 변경하지는 않아요.')
    return lines


def answer_plan(plan, question):
    q=re.sub(r'\s+', '', question)
    c=plan['conditions']; lines=[]
    def money(value):
        if value is None:return '미확인'
        return f'{value[0]:,}~{value[1]:,}원' if value[0]!=value[1] else f'{value[0]:,}원'
    if any(w in q for w in ('바꿔','변경해','추가해','빼줘','삭제해','교체해')):
        lines.append('질문으로 일정을 자동 변경하지는 않아요. 장소의 다른 장소로 변경 또는 식당의 이 식당을 일정에 넣기에서 변경안을 확인하고 확정해 주세요.')
    if any(w in q for w in ('가격','비용','얼마','예산','금액','메뉴')):
        lines.append(f"{c['people']}명 기준 계산된 총비용은 {money(plan['total'])}입니다. 확정 비용 {money(plan['confirmed'])}, 추정 비용 {money(plan['estimated'])}입니다.")
        for row in plan['costs']:
            lines.append(f"· {row['name']}: {money(row['amount'])} ({ {'confirmed':'확정','estimated':'추정','unknown':'미확인'}.get(row['status'],row['status'])})")
        if plan.get('unknown'):lines.append('합계에 포함되지 않은 미확인 비용: '+', '.join(plan['unknown']))
        lines.append(f"입력 예산은 {c['budget']:,}원이며, 실제 주문·현장 요금에 따라 달라질 수 있어요.")
    if any(w in q for w in ('시간','언제','몇시','순서','일정','요약','코스','동선','이동','거리','도보','걸어','귀가','얼마나걸')):
        lines.append(f"출발 {c['start']} → 종료 예정 {plan['finish']} · 전체 {plan['minutes']}분 · 총 도보 {plan['walking']}분")
        for p,t in zip(plan['places'],plan['timeline']):
            lines.append(f"· {t['arrival']}~{t['departure']} {p['name']} ({t['stay']}분 체류)")
        lines.extend(movement_advice(plan))
        lines.append('시간표는 계산된 예정 시간이며, 당일 교통·대기·영업 여부를 보장하지 않아요.')
    if any(w in q for w in ('주소','위치','어디')):
        lines.extend(f"· {p['name']}: {p.get('address') or '주소 미확인'}" for p in plan['places'])
    if any(w in q for w in ('조건','불일치','안맞','주의','준비','예약','운영','영업','휴무','날씨','비오')):
        checks=plan.get('condition_checks',[])
        selected=[r for r in checks if r['state'] in ('unmet','unknown') or any(w in q and w in str(r) for w in ('예약','영업','휴무','날씨'))]
        lines.extend('· '+r['message'] for r in selected)
        if not selected:lines.append('기록된 조건에서 추가 불일치는 없지만, 당일 영업·예약·날씨는 방문 전에 확인해 주세요.')
    if not lines:return None
    return dict(answer='\n'.join(lines),citations=[],status='plan_facts',trace=['saved_plan'],
                validation='현재 선택한 저장 일정의 계산값과 조건 점검 결과입니다. 실시간 현장 정보와 다를 수 있습니다.')
