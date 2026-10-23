"""Choose distinct venue sets with three explicit comparison purposes."""
from .quality import same_place


def changed_places(a,b):
    return sum(not any(same_place(p,q) for q in b['places']) for p in a['places'])


def diverse_beam(plans,limit):
    # Keep route-order alternatives, but prevent permutations of one set filling the beam.
    counts={};out=[]
    for plan in plans:
        key=frozenset(p['id'] for p in plan['places'])
        if counts.get(key,0)>=2:continue
        counts[key]=counts.get(key,0)+1;out.append(plan)
        if len(out)>=limit:break
    return out


def select_options(plans,c):
    unique=[]
    for plan in plans:
        if not any(len(plan['places'])==len(p['places']) and changed_places(plan,p)==0 for p in unique):unique.append(plan)
    if not unique:return []
    chosen=[unique.pop(0)]
    roles=[('취향 우선','요청한 취향과 추천 근거를 우선한 코스'),
           ('다른 매력','다른 장소와 경험을 비교하는 코스'),
           ('편안한 동선','이동 시간과 비용을 우선 비교한 코스')]
    while unique and len(chosen)<3:
        index=len(chosen)
        def novelty(p):return min(changed_places(p,q) for q in chosen)
        required=min(2,max(0,min(len(p['places']) for p in chosen)-len(c.locked)))
        eligible=[p for p in unique if novelty(p)>=required]
        if not eligible:
            most=max(novelty(p) for p in unique)
            eligible=[p for p in unique if novelty(p)==most]
        def travel(p):return sum(r.get('minutes') or 0 for r in p['legs'])
        if index==1:
            pick=min(eligible,key=lambda p:(-novelty(p),p.get('penalty',0),unique.index(p)))
        else:
            pick=min(eligible,key=lambda p:(travel(p),p['total'][1],p.get('penalty',0)))
        chosen.append(pick);unique.remove(pick)
    for i,p in enumerate(chosen):
        needed=min(2,max(0,len(p['places'])-len(c.locked)))
        minimum=min((changed_places(p,q) for q in chosen if q is not p),default=len(p['places']))
        note=''
        if len(chosen)<3:note='조건에 맞는 서로 다른 장소 조합이 부족해 '+str(len(chosen))+'개 옵션만 표시해요.'
        if minimum<needed:note+=' 후보가 부족해 다른 옵션과 일부 장소가 겹쳐요.'
        if c.locked:note+=' 사용자가 고정한 장소는 모든 옵션에서 유지해요.'
        p['option_purpose']=roles[i][0];p['option_description']=roles[i][1]
        p['diversity_note']=note.strip();p['minimum_different_places']=minimum
    return chosen
