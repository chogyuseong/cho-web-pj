from .service_time import today
"""Explain evidence without treating search ranking or retrieval dates as ratings."""
from datetime import date,datetime
from collections import Counter

def enrich(plan):
    kinds=Counter(p.get('category','기타') for p in plan['places'])
    category=kinds.most_common(1)[0][0] if kinds else '데이트'
    names={'카페·미식':'카페와 미식을 즐기는 하루','문화·예술':'전시와 문화를 만나는 하루','산책·풍경':'풍경을 따라 걷는 하루','체험·제작':'함께 만들고 경험하는 하루'}
    travel=sum(x.get('minutes') or 0 for x in plan.get('legs',[]))
    changes=(plan.get('search_adjustments') or {}).get('messages',[])
    plan['decision_summary']=dict(title=names.get(category,category+' 중심의 하루')+' · '+(plan.get('option_purpose') or '추천 코스'),travel_minutes=travel,
        reason=' · '.join(filter(None,[plan.get('option_purpose'),f"{len(plan['places'])}곳 · 이동 약 {travel}분",'조건 변경 있음' if changes else '상세 조건 확인 가능'])))
    matches=(plan.get('course_search') or {}).get('matches') or {}
    facts=[]
    for i,p in enumerate(plan['places']):
        row=plan.get('costs',[])[i] if i<len(plan.get('costs',[])) else {}
        quotes=row.get('price_evidence') or []
        age=None
        try:age=(today()-datetime.fromisoformat(p.get('operations_checked_at') or '').date()).days
        except (ValueError,TypeError):pass
        facts.append(dict(place_id=p['id'],address=p.get('address') or '주소 미확인',
            identity='등록 주소·좌표 연결 정보 · 지점 일치 여부는 원문 확인 필요',
            operating_age_days=age,operating_status='최근 90일 자료' if age is not None and 0<=age<=90 else '최신 운영 확인 필요',
            blog_match=bool(matches.get(p['id'])),price_kind=row.get('price_kind') or row.get('status','unknown'),
            price_checked_at=row.get('checked_at'),price_sources=quotes,
            reason=(plan.get('reasons') or [''])[i] if i<len((plan.get('reasons') or [])) else '조건 기반 후보'))
    plan['place_evidence']=facts
    plan['decision_summary']['source_matched_places']=sum(f['blog_match'] for f in facts)
    plan['decision_summary']['unknown_prices']=sum(r.get('amount') is None for r in plan.get('costs',[]))
    plan['decision_summary']['assumed_prices']=sum(r.get('price_kind')=='planning_assumption' for r in plan.get('costs',[]))
    from .request_intent import interpret,matches,INTENTS
    c=plan.get('conditions') or {}
    parsed=interpret((c.get('request') or '')+' '+(c.get('course_query') or ''))
    counts=[];reasons=[]
    for key in parsed['intents']:
        n=sum(matches(p,key) for p in plan['places'])
        label=INTENTS[key][1][0]
        if n:reasons.append(f'{label} 요청에 맞는 후보 {n}곳을 포함했어요.')
    for label,category in [('카페·식사','카페·미식'),('전시·문화','문화·예술'),('산책','산책·풍경'),('체험','체험·제작'),('놀이','오락·놀이'),('활동','레저·활동'),('휴식','휴식·힐링')]:
        n=kinds.get(category,0)
        if n:counts.append(f'{label} {n}곳')
    title=' · '.join(counts) or '함께 보내는 하루'
    if plan.get('option_purpose')=='편안한 동선':title=f'이동 약 {travel}분 · '+title
    plan['decision_summary']['title']=title
    plan['decision_summary']['activity_label']=' · '.join(counts)
    if c.get('setting') in ('indoor','outdoor'):
        n=sum(p.get('setting')==c['setting'] for p in plan['places'])
        reasons.append(f"{'실내' if c['setting']=='indoor' else '실외'} 요청: 확인된 후보 {n}/{len(plan['places'])}곳이에요.")
    reasons.append(f'장소 사이 이동은 약 {travel}분이에요. 경로 추정이 포함될 수 있어요.')
    plan['decision_summary']['fit_reasons']=reasons
    return plan

