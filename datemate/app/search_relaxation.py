"""Bounded, cumulative search steps; original user inputs are never overwritten."""
from math import ceil


def relaxation_steps(c):
    required=set(c.hard_constraints);patch={};history=[]
    def step(label,updates):
        changed={k:v for k,v in updates.items() if patch.get(k,getattr(c,k))!=v}
        if not changed:return None
        patch.update(changed);history.append(label)
        return c.model_copy(update=dict(patch)),list(history),dict(changed)
    def emit(label,updates):return step(label,updates)
    specifications=[]
    if c.mode=='real' and not c.allow_estimates:specifications.append(('운영·이동 정보가 부족한 장소도 추정을 표시해 비교',{'allow_estimates':True}))
    if c.trust_mode!='balanced':specifications.append(('공식 운영자료 우선에서 지역 검색으로 확인한 후보까지 확대',{'trust_mode':'balanced'}))
    if 'themes' not in required:
        specifications += [('한 유형 집중에서 여러 유형 조합까지 확대',{'theme_mode':'mix'}),
            ('선택한 테마 외의 활동 유형까지 확대',{'themes':[]}),
            ('선택한 데이트 분류 외의 활동까지 확대',{'date_category':'','date_subcategory':''})]
        from .request_intent import intent,INTENTS
        negative=' '.join(INTENTS[k][1][0]+' 제외' for k in intent(c)['excluded'])
        specifications.append(('자유 입력의 활동 선호를 넓혀 검색 (제외 요청 유지)',{'request':negative,'course_query':''}))
    if 'setting' not in required:specifications.append(('실내·실외 한정에서 전체 공간으로 확대',{'setting':'any'}))
    if 'reservation' not in required:specifications.append(('예약이 필요한 장소도 방문 전 확인 후보로 포함',{'reservation':True}))
    if 'avoid' not in required:specifications.append(('피할 활동·제외 유형 선호를 완화',{'avoid':[],'request':negative} if 'themes' not in required else {'avoid':[]}))
    if 'meal' not in required:specifications.append(('식사 코스 필수 구성 대신 별도 주변 식당으로 안내',{'include_meal':False}))
    for label,updates in specifications:
        value=emit(label,updates)
        if value:yield value
    # Small changes first, then larger changes; do not silently change the date or transport.
    for level in (1,2,3):
        numbers=[]
        if 'max_leg' not in required:numbers.append((f'구간 이동 제한 {c.max_leg}분 → {min(180,c.max_leg+15*level)}분',{'max_leg':min(180,c.max_leg+15*level)}))
        if c.max_walk is not None and 'max_walk' not in required:numbers.append((f'총 도보 제한 {c.max_walk}분 → {min(600,c.max_walk+30*level)}분',{'max_walk':min(600,c.max_walk+30*level)}))
        if 'budget' not in required:
            budget=min(10000000,c.budget+max(10000*level,ceil(c.budget*(.1,.25,.5)[level-1]/1000)*1000))
            numbers.append((f'예산 {c.budget:,}원 → {budget:,}원 범위로 비교',{'budget':budget}))
        if 'end' not in required:
            h,m=map(int,c.end.split(':'));end=min(1439,h*60+m+30*level)
            finish=f'{end//60:02}:{end%60:02}'
            numbers.append((f'종료 시간 {c.end} → {finish}까지 비교',{'end':finish}))
        for label,updates in numbers:
            value=emit(label,updates)
            if value:yield value
    for count in range(c.count-1,max(1,max(c.locked,default=-1)+1),-1):
        value=emit(f'방문 수 {c.count}곳 → {count}곳으로 비교',{'count':count})
        if value:yield value
    if 'neighborhood' not in required:
        radius=c.neighborhood_radius_km
        for expanded in sorted({r for r in (radius+1,5,10,20,40) if r>radius}):
            value=emit(f'선택 위치 유지 · 검색 반경 {radius:g}km → {expanded:g}km',{'area_center':c.area_center or c.origin,'neighborhood_radius_km':expanded})
            if value:yield value


def search_progressively(c,evidence=None):
    from .planner import recommend_strict
    from .condition_audit import audit_plan
    from .best_effort import annotate,suggest
    from .preferences import filter_required
    attempts=[];last=None
    for attempt,messages,changes in relaxation_steps(c):
        last=attempt
        result=recommend_strict(attempt,evidence)
        serialized=attempt.model_dump(mode='json')
        attempts.append(dict(step=len(attempts)+1,changes={key:serialized[key] for key in changes},plans=len(result['plans'])))
        options=[]
        for p in result['plans']:
            checked=audit_plan(p,attempt)
            if any(r['condition'] in ('meal','request_activity') and r['state']=='unmet' for r in checked['condition_checks']):continue
            p['conditions']=c.model_dump(mode='json')
            p=audit_plan(annotate(p,c),c)
            p['search_adjustments']=dict(stage='nearby' if attempt.neighborhood_radius_km>c.neighborhood_radius_km else 'same_location',
                origin_unchanged=True,original_radius_km=c.neighborhood_radius_km,effective_radius_km=attempt.neighborhood_radius_km,
                messages=messages,differences=[dict(label=r['label'],message=r['message']) for r in p['condition_checks'] if r['state']=='unmet'],
                attempts=list(attempts),effective_conditions=attempt.model_dump(mode='json'))
            options.append(p)
        options=filter_required(options)
        attempts[-1]['accepted_plans']=len(options)
        if options:return options
    # Last resort remains a labelled approximation; known closures and locks still apply.
    if last:
        options=suggest(last,evidence)
        for p in options:
            p['conditions']=c.model_dump(mode='json');audit_plan(annotate(p,c),c)
            p['search_adjustments']=dict(stage='nearby',origin_unchanged=True,original_radius_km=c.neighborhood_radius_km,
                effective_radius_km=last.neighborhood_radius_km,messages=messages+['단계별 검색으로도 충족되지 않은 조건은 차이를 표시한 참고 코스로 안내해요.'],
                differences=[dict(label=r['label'],message=r['message']) for r in p['condition_checks'] if r['state']=='unmet'],attempts=attempts)
        return filter_required(options)
    return []
