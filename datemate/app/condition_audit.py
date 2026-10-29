"""추천 경로와 무관하게 원래 입력의 모든 조건을 결과와 대조한다."""
import re
from .models import Conditions
from .taxonomy import classification_themes

def audit_plan(plan,c=None):
    c=c or Conditions.model_validate(plan['conditions'])
    from .taxonomy import CONCEPT_PROFILES,concept_signals
    plan['concept_matches']=[dict(place_id=p['id'],signals=concept_signals(p,c)) for p in plan['places']] if c.date_subcategory in CONCEPT_PROFILES else []
    checks=[];venues=plan['places'];routes=plan['legs'];real=c.mode=='real'
    def add(key,label,state,message):checks.append(dict(condition=key,label=label,state=state,message=message))
    def test(key,label,ok,yes,no):add(key,label,'met' if ok else 'unmet',yes if ok else no)
    from .request_intent import intent,matches,INTENTS
    parsed=intent(c)
    plan['request_interpretation']=dict(intents=[INTENTS[k][1][0] for k in parsed['intents']],excluded=[INTENTS[k][1][0] for k in parsed['excluded']],applied=parsed['patch'],warnings=parsed.get('warnings',[]))
    for key in parsed['intents']:
        matched=[p['name'] for p in venues if matches(p,key)]
        if parsed['exclusive']:
            ok=len(matched)==len(venues)
        else:ok=bool(matched)
        test('request_activity','입력한 활동',ok,INTENTS[key][1][0]+' 요청 반영: '+', '.join(matched),INTENTS[key][1][0]+' 요청에 맞는 장소가 부족해 다른 활동을 보완했어요. 입력한 지역·범위에서 후보를 확인해 주세요.')
    def mins(value):
        h,m=map(int,value.split(':'));return h*60+m
    names=lambda rows:', '.join(p['name'] for p in rows)
    from .quality import in_area,meal_due,meal_time_matches
    if c.area_center:
        test('neighborhood','동네 범위',all(in_area(p,c) for p in venues),f'{c.area_center.name} 반경 {c.neighborhood_radius_km:g}km 안의 장소로 구성했어요.','선택한 동네 범위 밖 장소가 있어요.')
    if meal_due(c):
        timed=meal_time_matches(plan)
        add('meal','식사 구성','met' if timed else 'unmet','식사 시간대에 음식점 방문을 포함했어요.' if timed else '조건에 맞는 식사 시간대의 음식점 구성을 찾지 못했어요. 식사 후보 또는 시간 조건을 확인해 주세요.')
    test('region','지역',all(p['region'] in ('서울','서울시','서울특별시') for p in venues),'방문 장소가 모두 서울 안에 있어요.','서울 밖 장소가 포함되어 있어요.')
    test('origin','출발지',bool(routes) and routes[0]['origin']==c.origin.name,'선택한 출발지에서 코스를 시작해요.','선택한 출발지가 경로에 반영되지 않았어요.')
    add('mode','장소 데이터','info','실제 장소로 구성했어요.' if real else '가상 장소 데모예요. 실제 방문할 수 없어요.')
    closed=[p for p in venues if (p['closed_days'] is not None and c.visit_date.weekday() in p['closed_days']) or str(c.visit_date) in p.get('closed_dates',[])]
    missing=[p for p in venues if p['hours'] is None or p['closed_days'] is None]
    if closed:add('visit_date','방문 날짜','unmet',str(c.visit_date)+'에 휴무인 장소가 있어요: '+names(closed))
    if missing:add('visit_date','방문 날짜·영업시간','unknown',str(c.visit_date)+'의 영업시간·휴무를 확인하지 못했어요: '+names(missing))
    if not closed and not missing:add('visit_date','방문 날짜','met',str(c.visit_date)+'의 등록된 영업시간·요일 휴무를 반영했어요.')
    for p,t in zip(venues,plan['timeline']):
        arrival,departure=mins(t['arrival']),mins(t['departure'])
        if p['hours'] and (arrival<p['hours'][0] or departure>p['hours'][1]):add('visit_date','영업시간','unmet',p['name']+' — 계획한 방문 시간이 등록된 영업시간 밖이에요.')
        if p['last_entry'] is not None and arrival>p['last_entry']:add('visit_date','마지막 입장','unmet',p['name']+' — 마지막 입장 시간이 지난 뒤 도착해요.')
        if any(arrival<end and departure>start for start,end in p.get('breaks') or []):add('visit_date','휴게시간','unmet',p['name']+' — 방문 시간이 등록된 휴게시간과 겹쳐요.')
    add('start','시작 시간','met',c.start+'에 출발하는 일정이에요.')
    excess=mins(c.start)+plan['minutes']-mins(c.end)
    test('end','종료 시간',excess<=0,'종료 '+plan['finish']+' — 요청한 '+c.end+' 이내예요.',f"종료 {plan['finish']} — 요청한 {c.end}보다 {excess}분 늦어요.")
    add('people','인원','unknown' if real and c.people>=10 else 'met',f'{c.people}명을 비용 계산에 반영했어요.'+(' 단체 방문이므로 장소별 단체 입장 가능 여부는 확인이 필요해요.' if real and c.people>=10 else ''))
    over=plan['total'][1]-c.budget
    if over>0:add('budget','예산','unmet',f'확인·추정 비용 상한 {plan["total"][1]:,}원이 예산 {c.budget:,}원보다 {over:,}원 많아요.')
    cost_unknown=any(row['amount'] is None for row in plan['costs']) or any('주차' in u or '통행료' in u for u in plan['unknown'])
    if cost_unknown:add('budget','예산','unknown',f'알려진 비용은 {plan["total"][0]:,}~{plan["total"][1]:,}원이지만, 미확인 입장료·교통비 등은 빠져 있어 예산 {c.budget:,}원 충족을 보장할 수 없어요.')
    elif over<=0:add('budget','예산','estimated' if any(r['status']=='estimated' for r in plan['costs']) else 'met',f'계산한 비용 상한 {plan["total"][1]:,}원은 예산 {c.budget:,}원 이내예요.')
    assumptions=[r for r in plan['costs'] if r.get('price_kind')=='planning_assumption']
    references=[r for r in plan['costs'] if r.get('price_kind')=='web_reference']
    if assumptions:add('price_data','가격 근거','info',f'{len(assumptions)}곳은 검색에서 실제 단가를 확보하지 못해 사용자가 허용한 계획용 범위를 사용했어요. 실제 청구 가격이 아니에요.')
    add('allow_price_estimates','가격 가정 사용','unmet' if assumptions and not c.allow_price_estimates else 'info',
        '가격 가정을 허용하지 않았지만 가정값이 포함되어 있어요.' if assumptions and not c.allow_price_estimates else '가격을 찾지 못한 경우 계획용 범위 사용을 허용했어요.' if c.allow_price_estimates else '계획용 가격 가정을 사용하지 않는 조건이에요.')
    if references:add('price_data','가격 근거','info',f'{len(references)}곳은 최근 웹 게시글의 참고 단가예요. 현재 공식 요금과 다를 수 있어요. 비용표의 원문을 확인해 주세요.')
    transport={'walk':'도보','transit':'대중교통','car':'자가용','bicycle':'자전거'}[c.transport]
    estimated=any(r['status']!='api' for r in routes)
    add('transport','교통수단·경로','estimated' if real and estimated and c.allow_estimates else 'unknown' if real and estimated else 'met',transport+' 기준으로 계산했어요.'+(' 허용하신 추정 경로예요. 실제 길찾기·시간표·도로 상황과 차이가 있을 수 있어요.' if real and estimated and c.allow_estimates else ' 실제 길찾기를 확인하지 못한 추정 경로예요.' if real and estimated else ''))
    test('count','방문 장소 수',len(venues)==c.count,f'요청한 {c.count}곳을 제안해요.',f'요청은 {c.count}곳이지만 {len(venues)}곳을 제안해요.')
    for key,label,wanted in [('themes','테마',c.themes),('date_subcategory',c.date_category or '데이트 분류',classification_themes(c))]:
        if not wanted:add(key,label,'info','별도 조건을 선택하지 않았어요.');continue
        from .quality import is_meal
        wrong=[p for p in venues if not (c.include_meal and is_meal(p)) and not set(p.get('themes') or [p['category']]).intersection(wanted)]
        selected=c.date_subcategory if key=='date_subcategory' else ', '.join(wanted)
        test(key,label,not wrong,'‘'+selected+'’에 해당하는 장소 유형으로 구성했어요.','‘'+selected+'’ 조건에 해당하지 않는 장소가 있어요: '+names(wrong))
        if key=='date_subcategory' and c.date_category=='계절별':add('season','계절 분위기','unknown','계절별 장소 유형은 반영하지만 개화·단풍·계절 행사 상태는 확인하지 못했어요.')
    if c.date_category=='날씨별' and c.date_subcategory:
        if c.date_subcategory in ('비 오는 날','눈 오는 날'):
            for p in venues:
                state='unknown' if p['setting'] is None else 'met' if p['setting']=='indoor' else 'unmet'
                add('weather','날씨',state,p['name']+' — ‘'+c.date_subcategory+'’에는 실내 장소를 찾지만, '+('실내 여부를 확인하지 못했어요.' if state=='unknown' else '야외 장소라 조건에 맞지 않아요.' if state=='unmet' else '실내 장소로 조건에 맞아요.'))
        else:add('weather','날씨','info','‘'+c.date_subcategory+'’에 맞는 활동 유형을 기준으로 구성했어요.')
        add('weather_forecast','실제 날씨','unknown','방문일의 실제 날씨 예보는 조회하지 않았어요. 선택한 날씨 조건만 반영해요.')
    diversity=len({p['category'] for p in venues})
    test('theme_mode','테마 구성',diversity==1 if c.theme_mode=='focus' else diversity>1,'선택한 테마 구성에 맞아요.','한 유형 집중 요청과 달리 여러 유형이 섞였어요.' if c.theme_mode=='focus' else '여러 유형 혼합을 원하셨지만 한 유형으로만 구성됐어요.')
    if c.setting!='any':
        for p in venues:
            state='unknown' if p['setting'] is None else 'met' if p['setting']==c.setting else 'unmet'
            add('setting','실내·실외',state,p['name']+' — '+('실내' if c.setting=='indoor' else '실외')+' 요청에 '+('맞는지 정보가 없어 확인이 필요해요.' if state=='unknown' else '맞아요.' if state=='met' else '맞지 않아요.'))
    else:add('setting','실내·실외','info','실내·실외 제한을 선택하지 않았어요.')
    hits=[p for p in venues if any(w.lower() in (p['name']+' '+p['category']+' '+' '.join(p['tags'])).lower() for w in c.avoid if w)]
    if hits:add('avoid','피할 활동','unmet','피하고 싶은 활동과 관련된 장소가 포함됐어요: '+names(hits))
    elif c.avoid:add('avoid','피할 활동','unknown' if real else 'met','장소명·분류·태그에서 '+', '.join(c.avoid)+' 항목은 제외했어요.'+(' 세부 활동 정보가 부족하여 완전한 제외 여부는 확인이 필요해요.' if real else ''))
    else:add('avoid','피할 활동','info','제외할 활동을 입력하지 않았어요.')
    unknown_reservations=[p for p in venues if p['reservation'] is None]
    if unknown_reservations:add('reservation','예약','unknown','예약 필요 여부는 방문 전 확인해 주세요: '+names(unknown_reservations))
    for p in venues:
        if p['reservation'] is None:continue
        elif p['reservation'] and not c.reservation:add('reservation','예약','unmet',p['name']+' — 예약 불가를 선택하셨지만 사전 예약이 필요한 장소예요.')
        elif p['reservation']:add('reservation','예약','unknown',p['name']+' — 예약 가능한 조건이지만 실제 예약 완료·잔여 자리는 미확인이에요.')
        else:add('reservation','예약','met',p['name']+' — 등록 정보상 예약이 필수는 아니에요.')
    for r in routes:
        excess=r['minutes']-c.max_leg if r['minutes'] is not None else None
        add('max_leg','구간 이동 시간','unknown' if excess is None else 'unmet' if excess>0 else 'estimated' if r['status']=='estimated' else 'met',
            r['origin']+' → '+r['destination']+': '+('이동 시간을 확인하지 못했어요.' if excess is None else f'{r["minutes"]}분 — 요청 {c.max_leg}분보다 {excess}분 초과해요.' if excess>0 else f'{r["minutes"]}분으로 요청 {c.max_leg}분 이내예요.'+(' (추정)' if r['status']=='estimated' else '')))
    if c.max_walk is not None:
        if any(r['walking'] is None for r in routes):add('max_walk','총 도보 시간','unknown','도보 정보가 없는 구간이 있어 총 도보 제한 충족 여부를 확인하지 못했어요.')
        else:test('max_walk','총 도보 시간',plan['walking']<=c.max_walk,f'총 도보 {plan["walking"]}분으로 요청 {c.max_walk}분 이내예요.',f'총 도보 {plan["walking"]}분 — 요청 {c.max_walk}분보다 {plan["walking"]-c.max_walk}분 초과해요.')
    else:add('max_walk','총 도보 시간','info','총 도보 제한을 선택하지 않았어요.')
    if c.return_home:
        ok=bool(routes) and routes[-1]['destination']==c.home.name and len(routes)==len(venues)+1
        test('return_home','귀가 포함',ok,'선택한 귀가지까지의 이동 시간·알려진 비용을 포함했어요.','요청한 귀가 경로가 일정에 포함되지 않았어요.')
    else:add('return_home','귀가 포함','info','귀가 포함을 선택하지 않았어요.')
    actual=[t['stay'] for t in plan['timeline']]
    test('stay_minutes','체류 시간',all(t==c.stay_minutes for t in actual),f'장소당 {c.stay_minutes}분으로 계산했어요.',f'요청은 장소당 {c.stay_minutes}분이지만 실제 계획은 '+', '.join(map(str,actual))+'분이에요.')
    if any(p['stay'] is None or p.get('stay_assumed') for p in venues):add('stay_minutes','체류 시간','estimated' if all(t==c.stay_minutes for t in actual) else 'info','체류 시간은 사용자 설정·식사 체류 가정으로 계산해요. 실제 소요시간과 다를 수 있어요.')
    used=estimated or any(p['stay'] is None or p.get('stay_assumed') for p in venues)
    if used and not c.allow_estimates and real:add('allow_estimates','추정 사용','unmet','추정 비허용 요청이지만 참고 코스를 만들기 위해 이동·체류 시간을 추정했어요.')
    else:add('allow_estimates','추정 사용','info','이동·체류 추정을 허용한 조건이에요.' if c.allow_estimates else '데모 또는 등록 운영정보로 계산했어요.')
    if c.use_mbti and not c.mbti:add('mbti','MBTI 참고','unknown','MBTI 참고를 선택했지만 유형을 입력하지 않아 적용하지 못했어요.')
    elif c.use_mbti and c.mbti:add('mbti','MBTI 참고','info',c.mbti+'는 보조 선호 기준이에요. 명시한 테마·데이트 분류가 우선하며 취향에 맞는다는 보장은 아니에요.')
    else:add('mbti','MBTI 참고','info','MBTI 참고를 선택하지 않았거나 유형이 비어 있어 반영하지 않았어요.')
    if c.request.strip():
        residual=c.request
        for pattern,key,label,actual,multiplier in [(r'(\d+)\s*명','people','인원',c.people,1),(r'(\d+)\s*(?:곳|군데)','count','방문 장소 수',c.count,1),(r'(\d+)\s*만\s*원','budget','예산',c.budget,10000)]:
            match=re.search(pattern,residual)
            if match and int(match[1])*multiplier!=actual:add(key,label,'unmet',f'자유 요청의 {label} 값과 폼 조건이 달라요. 자유 요청: {match[0]} / 적용값: {actual}')
            residual=re.sub(pattern,' ',residual)
        words=['서울에서','서울','박물관','전시','미술','카페','커피','식사','산책','풍경','공방','도자기','휴식','힐링','게임','놀이','운동','레저','데이트','코스','보고','가고','싶어요','싶어','추천','해주세요','해줘','정도','둘이서','명이서','함께','에서','하고','그리고']
        words += [word for _,synonyms in INTENTS.values() for word in synonyms]+['투어','위주','둘이','셋이','넷이']
        for word in sorted(words,key=len,reverse=True):residual=residual.replace(word,' ')
        residual=re.sub(r'[\s,.!?~·]+','',residual)
        add('request','자유 요청','unknown' if residual else 'info',('세부 요청은 추가 확인이 필요해요: '+c.request[:200]) if residual else '자유 요청의 테마·인원·방문 수·예산을 구조화 조건과 대조했어요.')
    else:add('request','자유 요청','info','추가 자유 요청이 없어요.')
    test('locked','고정 장소',all(i<len(venues) and venues[i]['id']==pid for i,pid in c.locked.items()),'고정한 장소와 순서를 유지했어요.' if c.locked else '고정한 장소가 없어요.','고정한 장소 또는 순서가 달라졌어요.')
    issues=[r for r in checks if r['state'] in ('unmet','unknown')]
    bad=len({r['condition'] for r in issues if r['state']=='unmet'});unknown=len({r['condition'] for r in issues if r['state']=='unknown'})
    from .restaurants import meal_suggestions
    plan.update(condition_checks=checks,deviations=issues,meal_suggestions=meal_suggestions(plan),
        confirmed_facts=[dict(name=p['name'],source=p['operations_source'],checked_at=p['operations_checked_at'],scope=p['operations_scope'],hours=p.get('hours'),price=p.get('price')) for p in venues if p.get('operations_source')],
        condition_summary=f'요청과 다른 조건 {bad}개 · 방문 전 확인 {unknown}개. 계산에 사용한 추정값은 전체 조건에서 확인할 수 있어요.')
    if real and not plan.get('best_effort'):plan['status']='실제 장소 · '+('이동 추정' if estimated else '경로 확인')+(f' · 방문 전 확인 {unknown}개' if unknown else ' · 등록 정보 확인')
    if plan.get('search_adjustments'):
        plan['search_adjustments']['differences']=[dict(label=r['label'],message=r['message']) for r in checks if r['state']=='unmet']
    return plan
