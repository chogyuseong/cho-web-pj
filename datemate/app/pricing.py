"""코스 비용 계산. 등록된 단가(업체 제공·등록 출처·운영자가 확인한 메뉴)와 계획용 가정 범위를 구분한다.

네이버 검색 API 특약 2.2·2.3(2026-09 개정, docs/naver-terms-stage2-design.ko.md 3.2(a)):
블로그 검색 요약에서 금액을 읽어 비용 표·합계·예산 판정에 넣던 것(extract_quote·lookup_price, 'web_reference' 가격)을 없앴다.
가격을 찾는 외부 호출은 없다. 등록된 단가가 없는 장소는 사용자가 허용하면 계획용 가정 범위(ASSUMPTIONS)로, 아니면 '확인 필요'(합계에서 빠짐)로 둔다.
그래서 합계는 '계획용 가정 범위' 중심이고 실제 가격과 다를 수 있다 — 화면이 비용 표 옆에 그렇게 적는다(static/plan-detail.js).
"""
import copy
from datetime import datetime,timezone

# 조회 가격이 아닌 예산 계획용 1인 범위. 사용자가 허용한 경우에만 사용한다.
ASSUMPTIONS={'문화·예술':[0,10000],'카페·미식':[6000,15000],'체험·제작':[15000,40000],
    '오락·놀이':[10000,30000],'레저·활동':[10000,30000],'휴식·힐링':[0,15000],'산책·풍경':[0,5000]}
ASSUMPTION_BASIS='계획용 1인 범위 · 등록된 단가가 없어 넣은 가정 (실제 단가 아님)'
ASSUMPTION_SOURCE='서비스 예산 계획용 가정'
UNKNOWN_BASIS='등록된 단가가 없어요. 가격은 방문 전에 확인해 주세요.'
# 메뉴를 골라 넣은 식당 가격(app/experience.meal_draft). operator_menu = 운영자가 확인한 제공 메뉴(app/operating_evidence.py),
# naver_menu = 네이버 화면에서 읽던 메뉴(app/naver_pages.py 가 꺼져 있어 새로 생기지 않음).
MENU_PRICE_KINDS=('operator_menu','naver_menu')

def apply_prices(plan):
    plan=copy.deepcopy(plan)
    if plan['conditions']['mode']!='real':return plan
    allow=plan['conditions'].get('allow_price_estimates',True);people=plan['conditions']['people'];updates=[]
    for index,place in enumerate(plan['places']):
        row=plan['costs'][index]
        if row.get('price_kind') in MENU_PRICE_KINDS:continue
        if row['unit'] is not None and not row.get('price_kind'):
            row['price_basis']=('업체 제공 단가 · 확인일 기준' if row.get('source_kind')=='merchant' else '등록 출처 단가 · 확인일 기준') if row['status']=='confirmed' else '저장된 단가 · 지금 가격은 따로 확인해 주세요';continue
        if not allow:
            row.update(price_basis=UNKNOWN_BASIS);continue
        unit=ASSUMPTIONS.get(place['category'],[0,20000])
        amount=[v*people for v in unit]
        row.update(unit=unit,quantity=people,formula=f'1인 기준 × {people}',amount=amount,status='estimated',source=ASSUMPTION_SOURCE,
            checked_at=None,price_basis=ASSUMPTION_BASIS,price_kind='planning_assumption')
        updates.append(place['name']+' 가격')
    plan['unknown']=[u for u in plan['unknown'] if u not in updates]
    total=[sum(r['amount'][i] for r in plan['costs'] if r['amount'] is not None) for i in (0,1)]
    known=[sum(r['amount'][i] for r in plan['costs'] if r['amount'] is not None and r['status']=='confirmed') for i in (0,1)]
    budget=plan['conditions']['budget']
    # 예산 무관: 예산 대비 차액을 만들지 않고 예산 초과로 표시하지도 않는다.
    unlimited=bool(plan['conditions'].get('budget_unlimited'))
    over=not unlimited and total[1]>budget
    plan.update(total=total,confirmed=known,estimated=[total[i]-known[i] for i in (0,1)],remaining=None if unlimited else [budget-total[1],budget-total[0]],
        pricing_checked_at=datetime.now(timezone.utc).isoformat())
    if over:plan.update(best_effort=True,status='예산을 넘는 대안 · 비용 확인 필요')
    from .condition_audit import audit_plan
    plan=audit_plan(plan)
    if not over and plan['status'].startswith('예산을 넘는'):
        if not any(d['state']=='unmet' for d in plan['deviations']):plan['best_effort']=False
        plan['status']='조건에 가까운 대안 · 차이 확인 필요'
        plan=audit_plan(plan)
    return plan

def price_plans(plans):
    """코스마다 비용을 계산한다(외부 호출 없음)."""
    return [apply_prices(p) for p in plans]
