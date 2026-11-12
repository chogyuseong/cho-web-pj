from .service_time import today
"""Explain evidence without treating search ranking or retrieval dates as ratings."""
from datetime import date,datetime
from collections import Counter

TRANSPORT_NAMES={'walk':'도보','transit':'대중교통','car':'자동차','bicycle':'자전거'}


def travel_mode(plan):
    """이동 시간이 어떤 수단·근거로 계산됐는지. 구간 자료(status)를 그대로 따른다."""
    c=plan.get('conditions') or {};legs=plan.get('legs') or []
    name=TRANSPORT_NAMES.get(c.get('transport'),'이동')
    statuses={leg.get('status') for leg in legs}
    if c.get('mode')=='demo':basis='가상 직선거리 추정'
    elif legs and statuses=={'api'}:basis='네이버 길찾기'
    elif 'api' in statuses:basis='일부 네이버 길찾기 · 일부 추정'
    else:basis='추정'
    return dict(transport=c.get('transport'),name=name,basis=basis,label=f'{name} · {basis}')


def festival_context(plan):
    """고른 축제와 코스 시간의 관계. 운영 시간은 이미 조회해 둔 관광공사 상세 캐시만 쓴다(추가 호출 없음)."""
    import re
    from . import store
    from .planner import minutes,clock
    c=plan.get('conditions') or {};f=c.get('festival')
    if not f:return None
    detail=store.cached('festival-detail:v1:'+f['id']) if re.fullmatch(r'\d{1,12}',str(f['id'])) else None
    hours=(detail or {}).get('hours')
    notes=[f"‘{f['title']}’ 행사장을 출발점으로 삼아 주변 장소로 코스를 짰어요. 축제 방문 시간은 코스에 넣지 않았어요."]
    m=re.search(r'(\d{1,2})\s*:\s*(\d{2})\s*[~\-–]\s*(\d{1,2})\s*:\s*(\d{2})',hours or '')
    if m and int(m[1])<24 and int(m[3])<=24:
        opening,closing=int(m[1])*60+int(m[2]),int(m[3])*60+int(m[4])
        if closing<=opening:closing+=1440
        start,finish=minutes(c['start']),minutes(plan.get('finish') or c['end'])
        overlap=min(finish,closing)-max(start,opening)
        if overlap>=30:notes.append(f'안내된 운영 시간 {hours} 중 코스 시간과 겹치는 때는 {clock(max(start,opening))}~{clock(min(finish,closing)%1440)}이에요.')
        elif finish<=opening:notes.append(f'축제는 안내된 운영 시간({hours})상 {clock(opening)}부터라 코스가 끝난 {clock(finish)} 뒤에 들를 수 있어요.')
        else:notes.append(f'안내된 운영 시간({hours})과 코스 시간이 거의 겹치지 않아요. 시작·종료 시간을 조정해 보세요.')
    elif hours:notes.append(f'축제 운영 시간 안내: {hours}')
    else:notes.append('축제 운영 시간은 확인하지 못했어요. 주최 측 안내를 확인해 주세요.')
    return dict(id=f['id'],title=f['title'],hours=hours,notes=notes)


def enrich(plan):
    kinds=Counter(p.get('category','기타') for p in plan['places'])
    category=kinds.most_common(1)[0][0] if kinds else '데이트'
    names={'카페·미식':'카페와 미식을 즐기는 하루','문화·예술':'전시와 문화를 만나는 하루','산책·풍경':'풍경을 따라 걷는 하루','체험·제작':'함께 만들고 경험하는 하루'}
    travel=sum(x.get('minutes') or 0 for x in plan.get('legs',[]))
    mode=travel_mode(plan)
    changes=(plan.get('search_adjustments') or {}).get('messages',[])
    plan['decision_summary']=dict(title=names.get(category,category+' 중심의 하루')+' · '+(plan.get('option_purpose') or '추천 코스'),travel_minutes=travel,travel_mode=mode,
        reason=' · '.join(filter(None,[plan.get('option_purpose'),f"{len(plan['places'])}곳 · {mode['name']} 이동 약 {travel}분",'조건 변경 있음' if changes else '상세 조건 확인 가능'])))
    matches=(plan.get('course_search') or {}).get('matches') or {}
    facts=[]
    for i,p in enumerate(plan['places']):
        row=plan.get('costs',[])[i] if i<len(plan.get('costs',[])) else {}
        quotes=row.get('price_evidence') or []
        age=None
        try:age=(today()-datetime.fromisoformat(p.get('operations_checked_at') or '').date()).days
        except (ValueError,TypeError):pass
        facts.append(dict(place_id=p['id'],address=p.get('address') or '주소 미확인',
            identity='등록된 주소로 지도 위치를 찾았어요 · 같은 지점인지는 확인하지 못했어요',
            operating_age_days=age,operating_current=age is not None and 0<=age<=90,
            operating_status='최근 90일 안에 확인한 영업 자료가 있어요' if age is not None and 0<=age<=90 else '최근 영업 정보를 확인하지 못했어요 · 방문 전 확인해 주세요',
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
    if plan.get('option_purpose')=='편안한 동선':title=f"{mode['name']} 이동 약 {travel}분 · "+title
    plan['decision_summary']['title']=title
    plan['decision_summary']['activity_label']=' · '.join(counts)
    if c.get('setting') in ('indoor','outdoor'):
        n=sum(p.get('setting')==c['setting'] for p in plan['places'])
        reasons.append(f"{'실내' if c['setting']=='indoor' else '실외'} 요청: 확인된 후보 {n}/{len(plan['places'])}곳이에요.")
    note={'네이버 길찾기':'네이버 길찾기로 조회한 시간이에요.','일부 네이버 길찾기 · 일부 추정':'일부 구간만 네이버 길찾기로 조회했고 나머지는 추정이에요.'}.get(mode['basis'],'직선거리로 추정한 시간이에요.')
    reasons.append(f"장소 사이 이동은 {mode['name']} 기준 약 {travel}분이에요. {note}")
    plan['decision_summary']['fit_reasons']=reasons
    context=festival_context(plan)
    if context:plan['festival_context']=context
    return plan

