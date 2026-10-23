from collections import Counter
import re
from .catalog import places
from .models import Conditions
from .routes import leg, distance
from .taxonomy import classification_themes,concept_score

def minutes(value):
    hour,minute=map(int,value.split(':'))
    return hour*60+minute

def clock(value):return f'{value//60:02}:{value%60:02}'

def candidates(c):
    rows=[]
    classified=classification_themes(c)
    from .quality import pool,is_meal
    for p in pool(c):
        if p['region'] not in ('서울', '서울시', '서울특별시'):continue
        place_themes=set(p.get('themes') or [p['category']])
        meal=c.include_meal and is_meal(p)
        if c.themes and not place_themes.intersection(c.themes) and not meal:continue
        if classified and not place_themes.intersection(classified) and not meal:continue
        if c.date_category=='날씨별' and c.date_subcategory in ('비 오는 날','눈 오는 날') and p['setting']!='indoor':continue
        if c.setting!='any' and p['setting']!=c.setting:continue
        if any(word and word.lower() in (p['name']+' '+p['category']+' '+' '.join(p['tags'])).lower() for word in c.avoid):continue
        if p['reservation'] and not c.reservation:continue
        rows.append(p)
    # 명시적인 테마가 있으면 MBTI 가중치는 적용하지 않는다.
    preferred='휴식·힐링' if c.mbti.startswith('I') else '레저·활동'
    words=[w for w in re.findall(r'[가-힣A-Za-z0-9]+',c.request) if len(w)>1]
    rows.sort(key=lambda p: (-sum(w in (p['name']+' '+p['category']+' '+' '.join(p['tags'])) for w in words),-(.1 if c.use_mbti and c.mbti and not c.themes and not classified and p['category']==preferred else 0),distance(c.origin.model_dump(),p)))
    rows.sort(key=lambda p:-concept_score(p,c))
    from .request_intent import place_score
    rows.sort(key=lambda p:-place_score(p,c))
    return rows

def evaluate(selected,c,partial=False,soft=False,verify_routes=False):
    from .quality import same_place
    if any(same_place(a,b) for i,a in enumerate(selected) for b in selected[i+1:]):return None,'같은 장소 중복'
    if not partial and len(selected)!=c.count and not soft:return None,'방문 장소 수 불일치'
    route_conditions=c.model_copy(update={'allow_estimates':True}) if soft and c.mode=='real' else c
    now=minutes(c.start); end=minutes(c.end); legs=[]; timeline=[]; costs=[]; unknown=[]; walking=0
    previous=c.origin.model_dump()
    for original in selected:
        p=dict(original)
        if str(c.visit_date) in p.get('closed_dates',[]):return None,'방문일 휴무'
        if c.mode=='real' and (c.allow_estimates or soft):
            if p['hours'] is None:unknown.append(p['name']+' 영업시간');p['hours']=[0,1440]
            if p['closed_days'] is None:unknown.append(p['name']+' 휴무');p['closed_days']=[]
            if p['stay'] is None:p['stay']=c.stay_minutes;p['stay_basis']='사용자가 선택한 체류 시간'
            if p['reservation'] is None:unknown.append(p['name']+' 예약 여부')
        # 운영정보가 없으면 확인된 일정으로 추천하지 않고 누락 사유를 반환한다.
        if p['hours'] is None or p['stay'] is None or p['closed_days'] is None:
            return None,'운영시간·휴무·체류 시간 확인 필요'
        if c.visit_date.weekday() in p['closed_days']:return None,'방문일 휴무'
        route=leg(previous,p,route_conditions,force_api=verify_routes)
        if route['minutes'] is None:return None,'실제 이동 시간 계산 불가 (경로 공급자 또는 키 필요)'
        if route['minutes']>c.max_leg and not soft:return None,'구간 이동 시간 초과'
        walking+=route['walking'] or 0
        if c.max_walk is not None and route['walking'] is None:return None,'전체 도보 시간 확인 불가'
        now+=route['minutes']; opening,closing=p['hours']; now=max(now,opening)
        for start,finish in p.get('breaks') or []:
            if now<finish and now+p['stay']>start:now=finish
        if p['last_entry'] is not None and now>p['last_entry']:return None,'마지막 입장 시간 초과'
        if now+p['stay']>closing:return None,'영업시간 밖 방문'
        timeline.append(dict(place_id=p['id'],arrival=clock(now),departure=clock(now+p['stay']),stay=p['stay']))
        now+=p['stay']; legs.append(route)
        quantity=c.people if p['price_unit']=='person' else 1
        price=p['price']; amount=[v*quantity for v in price] if price is not None else None
        costs.append(dict(category=p['category'],name=p['name'],unit=price,quantity=quantity,
            formula=f'단가 × {quantity}',amount=amount,status=p.get('price_status','unknown' if price is None else 'confirmed'),
            source=p.get('operations_source',p['source']),checked_at=p.get('operations_checked_at',p['checked_at'])))
        if p.get('menu_pricing'):costs[-1].update(p['menu_pricing'])
        if price is None:unknown.append(p['name']+' 가격')
        if c.transport=='car':unknown.append(p['name']+' 주차비')
        previous=p
    if not partial and c.return_home:
        route=leg(previous,c.home.model_dump(),route_conditions,force_api=verify_routes)
        if route['minutes'] is None:return None,'귀가 경로 계산 불가'
        if route['minutes']>c.max_leg and not soft:return None,'귀가 구간 이동 시간 초과'
        if c.max_walk is not None and route['walking'] is None:return None,'귀가 도보 시간 확인 불가'
        now+=route['minutes'];walking+=route['walking'] or 0;legs.append(route)
    for r in legs:
        amount=[r['cost'],r['cost']] if r['cost'] is not None else None
        costs.append(dict(category='교통',name=r['origin']+' → '+r['destination'],unit=amount,quantity=1,formula='구간 총액 (인원 반영)',
            amount=amount,status='estimated' if amount is not None else 'unknown',source=r['source'],checked_at=r['checked_at']))
        if amount is None:unknown.append('교통 또는 대여 비용')
        if c.transport=='car' and r['toll'] is None:unknown.append('통행료')
    if now>end and not soft:return None,'전체 일정 시간 초과'
    if c.max_walk is not None and walking>c.max_walk and not soft:return None,'전체 도보 시간 초과'
    total=[sum(row['amount'][i] for row in costs if row['amount'] is not None) for i in (0,1)]
    if total[1]>c.budget and not soft:return None,'예산 초과 (가격 범위 상한 기준)'
    known=[sum(row['amount'][i] for row in costs if row['amount'] is not None and row['status']=='confirmed') for i in (0,1)]
    estimated=[total[i]-known[i] for i in (0,1)]
    status='데모 가정 기준 통과' if c.mode=='demo' else '실제 장소 · 추정 일정 (영업·총예산 미검증)' if c.allow_estimates else '확인 필요' if unknown else '확인 자료 기준 통과'
    if unknown:status+=' · 미확인 비용 있음'
    return dict(places=selected,timeline=timeline,legs=legs,costs=costs,total=total,confirmed=known,estimated=estimated,
        unknown=sorted(set(unknown)),remaining=[c.budget-total[1],c.budget-total[0]],minutes=now-minutes(c.start),
        walking=walking,finish=clock(now),status=status,conditions=c.model_dump(mode='json'),
        reasons=[f'{p["category"]} · 체류 {t["stay"]}분'+(' (사용자 설정)' if p['stay'] is None else '')+(' · 식사 방문 (시간·예산 포함)' if p.get('meal') else '')+(' · '+p['discovery_verification'] if p.get('discovery_verification') else '')+f' · 근거: {p["source"]}' for p,t in zip(selected,timeline)]),None

def recommend_strict(c,evidence=None):
    pool=candidates(c); reasons=Counter(); beam=[[]]
    if not pool:
        filters=[]
        if c.themes:filters.append('테마: '+', '.join(c.themes))
        if c.date_subcategory:filters.append('데이트 분류: '+c.date_subcategory)
        if c.setting!='any':filters.append('실내만' if c.setting=='indoor' else '실외만')
        return dict(plans=[],status='no_candidates',reasons=['현재 확보한 실제 장소 중 '+(' / '.join(filters) or '선택 조건')+'에 맞는 후보가 없습니다.'],
            suggestions=['테마·실내외·피할 활동 조건을 확인해 주세요. 조건은 자동으로 변경하지 않습니다.'],diagnostics={'catalog_count':len(places(c.mode)),'candidate_count':0})
    ready=[p for p in pool if c.allow_estimates or (p['hours'] is not None and p['stay'] is not None and p['closed_days'] is not None)]
    if not ready:
        return dict(plans=[],status='data_incomplete',reasons=['실제 장소의 운영시간·휴무·체류 정보가 부족해 일정을 검증할 수 없습니다.'],
            suggestions=['API 키 설정과 별개로 장소 운영정보 확보가 필요합니다. 추정 일정 허용을 선택하면 실제 장소로 코스를 만들 수 있습니다.'],
            diagnostics={'candidate_count':len(pool),'ready_count':0})
    if c.mode=='demo':
        nearest=min(leg(c.origin.model_dump(),p,c)['minutes'] for p in ready)
        if nearest>c.max_leg:
            return dict(plans=[],status='origin_too_far',reasons=[f'출발지에서 가장 가까운 가상 장소까지 추정 {nearest}분으로, 구간 이동 제한 {c.max_leg}분을 초과합니다.'],
                suggestions=['가상 장소는 서울 종로 시연 구역에 모여 있습니다. 데모 기본 조건으로 시연하거나 출발지·이동 제한을 직접 조정하세요.'],
                diagnostics={'nearest_minutes':nearest,'max_leg':c.max_leg})
    for position in range(c.count):
        next_beam=[]
        for selected in beam:
            options=[p for p in pool if p['id']==c.locked[position]] if position in c.locked else pool
            for p in options:
                if p['id'] in {x['id'] for x in selected}:continue
                if p['id'] in c.locked.values() and c.locked.get(position)!=p['id']:continue
                if c.theme_mode=='focus' and selected and p['category']!=selected[0]['category']:continue
                plan,error=evaluate(selected+[p],c,partial=position<c.count-1)
                if error:reasons[error]+=1
                else:next_beam.append(plan)
        # 제한된 빔 탐색: 비용·동선과 테마 다양성으로 후보를 줄여 폭발을 막는다.
        next_beam.sort(key=lambda p:(-sum(w in (x['name']+' '+x['category']) for x in p['places'] for w in re.findall(r'[가-힣A-Za-z0-9]{2,}',c.request)),-len({x['category'] for x in p['places']}) if c.theme_mode=='mix' else 0,
                                     sum(r['minutes'] for r in p['legs'])-(.1*sum(x['category']==('휴식·힐링' if c.mbti.startswith('I') else '레저·활동') for x in p['places']) if c.use_mbti and c.mbti and not c.themes and not c.date_subcategory else 0),p['total'][1]))
        if evidence:
            from .course_search import priority
            next_beam.sort(key=lambda p:-priority(p,evidence))
        from .quality import meal_penalty,meal_due,is_meal
        from .preferences import fit_score
        next_beam.sort(key=lambda p:-fit_score(p,c))
        if meal_due(c) and position<c.count-1:next_beam.sort(key=lambda p:max(0,sum(is_meal(x) for x in p['places'])-1))
        if position==c.count-1:next_beam.sort(key=lambda p:meal_penalty(p,c))
        from .request_intent import plan_penalty
        next_beam.sort(key=lambda p:plan_penalty(p,c))
        from .option_diversity import diverse_beam
        beam=[p['places'] for p in diverse_beam(next_beam,60)]
        if not beam:break
    final=[];sets=[]
    if beam and len(beam[0])==c.count:
        for selected in beam:
            ids={p['id'] for p in selected}
            if ids in sets:continue
            plan,error=evaluate(selected,c)
            if plan:final.append(plan);sets.append(ids)
    from .option_diversity import select_options
    final=select_options(final,c)
    return dict(plans=final,status='ok' if final else 'constraints_unmet',reasons=[k for k,_ in reasons.most_common(5)] if len(final)<3 else [],
        suggestions=['조건은 자동 완화하지 않았습니다. 시간·예산·테마·예약 가능 여부를 수정해 다시 검색하세요.'] if len(final)<3 else [],
        search_note='최대 60개 빔 후보 내 탐색 결과이며 가능한 모든 일정의 존재를 보장하지 않습니다.')

def recommend(c,evidence=None):
    from .request_intent import normalize,plan_penalty
    c=normalize(c)
    from .condition_audit import audit_plan
    result=recommend_strict(c,evidence)
    # Activity and meal composition are scored during beam search; retry them too if unmet.
    checked=[audit_plan(p,c) for p in result['plans']]
    result['plans']=[p for p in checked if not any(r['condition'] in ('meal','request_activity') and r['state']=='unmet' for r in p['condition_checks'])]
    # 검색 글에서 확인한 장소가 일반 조건 필터에서 빠졌다면, 차이를 명시한 대안도 비교한다.
    if result['plans'] and evidence and evidence.get('matches'):
        from .course_search import priority
        if not any(priority(p,evidence) for p in result['plans']):
            from .best_effort import suggest
            sourced=suggest(c,evidence)
            if sourced and priority(sourced[0],evidence) and (not result['plans'] or plan_penalty(sourced[0],c)<=plan_penalty(result['plans'][0],c)):
                return dict(plans=[audit_plan(p,c) for p in sourced],status='best_effort',
                            reasons=['네이버 상위 글에 등장하는 장소를 우선 포함한 대안입니다. 입력 조건과의 차이를 확인하세요.'])
    if result['plans']:
        result['plans']=[audit_plan(p,c) for p in result['plans']]
        return result
    from .search_relaxation import search_progressively
    alternatives=search_progressively(c,evidence)
    if not alternatives:return result
    return dict(plans=[audit_plan(p,c) for p in alternatives],status='best_effort',reasons=['모든 조건을 만족하는 일정 대신 조건에 가까운 대안 코스를 찾았습니다.'],
        suggestions=['각 코스에 표시된 차이를 보고 조건을 수정하거나 장소를 교체해 주세요.'],strict_failure=result.get('status'),
        search_note='조건 차이와 이동·비용을 점수로 비교한 후보입니다. 미확인 운영정보·비용은 별도 확인이 필요합니다.')

def replacements(plan,index,locked):
    c=Conditions.model_validate(plan['conditions'])
    if index<0 or index>=len(plan['places']):raise ValueError('잘못된 장소 순서입니다.')
    if index in set(locked)|set(c.locked):raise ValueError('고정한 장소는 먼저 고정을 해제하세요.')
    alternatives=[]
    from .quality import pool as quality_pool
    pool=quality_pool(c) if plan.get('best_effort') else candidates(c)
    for p in pool:
        if any(w.lower() in (p['name']+' '+p['category']+' '+' '.join(p['tags'])).lower() for w in c.avoid if w):continue
        if p['id'] in {x['id'] for x in plan['places']}:continue
        chosen=list(plan['places']);chosen[index]=p
        if not plan.get('best_effort') and c.theme_mode=='focus' and len({x['category'] for x in chosen})>1:continue
        updated,error=evaluate(chosen,c,soft=bool(plan.get('best_effort')))
        if not error:
            if plan.get('course_search'):updated['course_search']=plan['course_search']
            if plan.get('best_effort'):
                from .best_effort import annotate
                updated=annotate(updated,c)
            updated['delta']=dict(minutes=updated['minutes']-plan['minutes'],cost=[updated['total'][i]-plan['total'][i] for i in (0,1)])
            updated['change_reason']='앞뒤 이동·시간·비용과 요청 조건 차이를 다시 계산했습니다.'
            alternatives.append(updated)
    if plan.get('best_effort'):alternatives.sort(key=lambda p:p['penalty'])
    from .condition_audit import audit_plan
    return [audit_plan(p,c) for p in alternatives[:8]]
