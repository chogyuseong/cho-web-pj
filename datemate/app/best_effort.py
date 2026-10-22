"""조건에 가까운 코스. 원래 조건은 보존하고 차이를 명시한다."""
import re
from .catalog import places
from .routes import distance
from .taxonomy import classification_themes

CONDITION_LABELS={'themes':'테마','date_subcategory':'데이트 분류','weather':'날씨','setting':'실내·실외',
    'reservation':'예약','max_leg':'구간 이동 시간','end':'종료 시간','max_walk':'총 도보 시간',
    'budget':'예산','count':'방문 장소 수','theme_mode':'테마 구성','allow_estimates':'추정 사용'}

def annotate(plan,c):
    from .planner import minutes
    changes=[]
    def add(key,message,penalty,state='unmet'):changes.append(dict(condition=key,label=CONDITION_LABELS[key],state=state,message=message,penalty=round(penalty,3)))
    selected=plan['places'];wanted=set(c.themes);classified=set(classification_themes(c))
    for p in selected:
        themes=set(p.get('themes') or [p['category']])
        if wanted and not themes.intersection(wanted):add('themes',p['name']+' — 요청한 '+', '.join(c.themes)+' 테마 대신 '+p['category']+' 장소예요.',3)
        if classified and not themes.intersection(classified):add('date_subcategory',p['name']+' — 선택한 ‘'+c.date_subcategory+'’에 해당하는 활동 유형과 달라요.',3)
        indoor=c.setting=='indoor' or c.date_subcategory in ('비 오는 날','눈 오는 날')
        if indoor and p['setting']!='indoor':
            weather=c.date_subcategory in ('비 오는 날','눈 오는 날')
            prefix=p['name']+' — '+('‘'+c.date_subcategory+'’에는 실내 장소를 찾지만, ' if weather else '실내만 원하셨지만, ')
            unknown=p['setting'] is None
            add('weather' if weather else 'setting',prefix+('이 장소의 실내 여부는 확인되지 않았어요.' if unknown else '이 장소는 야외예요.'),3,'unknown' if unknown else 'unmet')
        if c.setting=='outdoor' and p['setting']!='outdoor':
            unknown=p['setting'] is None
            add('setting',p['name']+' — 실외만 원하셨지만, '+('이 장소의 실외 여부는 확인되지 않았어요.' if unknown else '이 장소는 실내예요.'),3,'unknown' if unknown else 'unmet')
        if p['reservation'] and not c.reservation:add('reservation',p['name']+' — 사전 예약 필요',4)
    for route in plan['legs']:
        excess=route['minutes']-c.max_leg
        if excess>0:add('max_leg',f"{route['origin']} → {route['destination']}: {route['minutes']}분 (요청 {c.max_leg}분보다 {excess}분 초과)",excess/15)
    excess=minutes(c.start)+plan['minutes']-minutes(c.end)
    if excess>0:add('end',f"종료 {plan['finish']} — 요청 {c.end}보다 {excess}분 늦음",excess/30)
    if c.max_walk is not None and plan['walking']>c.max_walk:
        excess=plan['walking']-c.max_walk;add('max_walk',f"총 도보 {plan['walking']}분 — 요청보다 {excess}분 초과",excess/15)
    if plan['total'][1]>c.budget:
        excess=plan['total'][1]-c.budget;add('budget',f'확인·추정 비용 상한이 예산보다 {excess:,}원 초과 (미확인 비용 별도)',excess/max(10000,c.budget))
    if len(selected)!=c.count:add('count',f'요청 {c.count}곳 → 제안 {len(selected)}곳',4*abs(c.count-len(selected)))
    if c.theme_mode=='focus' and len({p['category'] for p in selected})>1:add('theme_mode','한 유형 집중 대신 여러 장소 유형으로 구성',2)
    if c.mode=='real' and not c.allow_estimates:add('allow_estimates','추정 비허용 요청이지만 운영정보가 부족하여 이동·체류 시간을 추정했어요.',2)
    unmet=list(dict.fromkeys(x['label'] for x in changes if x['state']=='unmet'))
    uncertain=list(dict.fromkeys(x['label'] for x in changes if x['state']=='unknown'))
    summary=('·'.join(unmet)+' 조건을 모두 맞추지는 못했지만, 조건에 가까운 코스로 제안해요.') if unmet else '확인이 필요한 조건이 있어 참고 코스로 제안해요.'
    if uncertain:summary+=' '+ '·'.join(uncertain)+' 조건은 정보가 부족해 충족 여부를 확인해야 해요.'
    plan.update(best_effort=True,deviations=changes,condition_summary=summary,penalty=round(sum(x['penalty'] for x in changes),3),
        status='조건에 가까운 대안 · 차이 확인 필요')
    return plan

def suggest(c,evidence=None):
    from .planner import evaluate
    from .quality import pool as quality_pool,meal_penalty
    pool=[p for p in quality_pool(c) if not any(w.lower() in (p['name']+' '+p['category']+' '+' '.join(p['tags'])).lower() for w in c.avoid if w)]
    # 후보 수를 제한하되 가까운 장소와 요청 테마에 맞는 장소 모두 포함한다.
    pool.sort(key=lambda p:distance(c.origin.model_dump(),p))
    desired=set(c.themes)|set(classification_themes(c))
    matching=[p for p in pool if desired.intersection(p.get('themes') or [p['category']])]
    mentioned=[p for p in pool if p['id'] in (evidence or {}).get('matches',{})]
    chosen={p['id']:p for p in pool[:40]+matching[:25]+mentioned+[p for p in pool if p['id'] in c.locked.values()]}
    pool=list(chosen.values());beam=[[]];final=[]
    target=min(c.count,len(pool))
    if not target or any(i>=target for i in c.locked):return []
    words=re.findall(r'[가-힣A-Za-z0-9]{2,}',c.request)
    def score(plan):
        relevance=sum(w in (p['name']+' '+p['category']) for w in words for p in plan['places'])
        from .course_search import priority
        return (meal_penalty(plan,c) if len(plan['places'])==target else 0,-priority(plan,evidence or {}),plan['penalty'],sum(r['minutes'] for r in plan['legs'])-.1*relevance,plan['total'][1])
    for position in range(target):
        options=[]
        for selected in beam:
            for p in pool:
                if position in c.locked and p['id']!=c.locked[position]:continue
                if p['id'] in c.locked.values() and c.locked.get(position)!=p['id']:continue
                if p['id'] in {x['id'] for x in selected}:continue
                plan,error=evaluate(selected+[p],c,partial=position<target-1,soft=True)
                if not error:options.append(annotate(plan,c))
        options.sort(key=score)
        if not options:break
        final=options[:40];beam=[p['places'] for p in final]
    results=[];seen=set()
    for plan in final:
        if len(plan['places'])!=target:continue
        ids=frozenset(p['id'] for p in plan['places'])
        if ids in seen:continue
        seen.add(ids);results.append(plan)
        if len(results)==3:break
    return results
