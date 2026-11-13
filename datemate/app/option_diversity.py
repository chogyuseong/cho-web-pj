"""Choose distinct venue sets with three explicit comparison purposes.

선택 방식은 DATEMATE_OPTION_SELECTOR(config.option_selector)로 정한다.
- place: 장소 차이만 보는 기존 선택기(legacy_select_options). 완전히 되돌릴 때 쓴다
- shadow: 기존 선택기 결과를 그대로 쓰고, 새 선택기는 진단·로그로만 남긴다
- experience(기본): 활동 구성·이동량이 실제로 다른 안을 먼저 고르고, 모자란 자리는 같은 구성의 다른 장소로 채운다(experience_select)
"""
import logging
from collections import Counter
from .quality import same_place,is_meal

EXPERIENCE_VERSION='exp-v2'
# 활동 구성 묶음. 기타는 차이로 세지 않는다.
CATEGORY_GROUPS={'문화·예술':'보기','산책·풍경':'걷기','체험·제작':'하기','오락·놀이':'하기','레저·활동':'하기','휴식·힐링':'쉬기'}
GROUP_ORDER=['식사','카페','보기','걷기','하기','쉬기']
GROUP_LABELS={'식사':'식사','카페':'카페','보기':'전시·관람','걷기':'산책','하기':'체험·놀이','쉬기':'휴식'}
BASE_ROLE=('기준 코스','요청 조건 비교에서 가장 앞선 조합이에요')
SAME_COMPOSITION_ROLE='같은 구성 · 다른 장소'


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


# 빔 구성 할당(beam-v1). 수치는 scripts/measure_option_diversity.py의 부산·경주 재현 조건으로 정했다.
# - 순위 보호(BEAM_PROTECT): 정렬 상위 절반은 구성과 관계없이 그대로 남긴다. 1안이 될 부분 경로가
#   상위권에서 빠지지 않게 하는 장치다(1안 동일 여부는 측정 스크립트로 확인).
# - 구성 상한(BEAM_CAP): 한 구성(부분 경로의 group 다중집합)이 빔의 절반을 넘으면 나머지는 뒤로 미룬다.
# - 구성별 최소 보장(BEAM_GUARANTEE): 구성마다 상위 몇 개를 먼저 넣는다. 부분 경로는 2개, 완료 후보는 3개.
#   완료 후보에서 3개면 선택기가 같은 구성 안에서도 장소가 다른 안을 고를 여지가 남는다.
# 할당은 같은 우선 등급(tier) 안에서만 자리를 옮긴다. 등급이 앞선 후보(필수 조건·식사 배치·요청 낱말·
# 블로그 근거·선호 점수)는 상한에 걸려도 등급이 뒤진 후보보다 먼저 들어간다. 평가 횟수는 그대로다.
BEAM_PROTECT=0.5
BEAM_CAP=0.5
BEAM_GUARANTEE_PARTIAL=2
BEAM_GUARANTEE_FINAL=3


def composition_beam(plans,limit,tier=None,final=False,enabled=True):
    """정렬된 plans에서 빔 limit개를 고른다. 순서는 입력 순위를 유지한다(결정적, 난수 없음).
    enabled=False거나 후보가 limit 이하면 diverse_beam과 같다."""
    unique=diverse_beam(plans,len(plans))
    if not enabled or len(unique)<=limit:return unique[:limit]
    protect=int(limit*BEAM_PROTECT);cap=max(1,int(limit*BEAM_CAP))
    guarantee=BEAM_GUARANTEE_FINAL if final else BEAM_GUARANTEE_PARTIAL
    seen=Counter();order=[]
    for rank,plan in enumerate(unique):
        key=composition_label(plan);n=seen[key];seen[key]+=1
        bucket=0 if rank<protect else 1 if n<guarantee else 2 if n<cap else 3
        order.append((tier(plan) if tier else (),bucket,rank))
    keep=sorted(rank for *_,rank in sorted(order)[:limit])
    return [unique[r] for r in keep]


def legacy_select_options(plans,c):
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


# ---------------------------------------------------------------------------
# 경험 기준 선택기 (exp-v2: exp-v1 규칙 + 장소 기준 완화·같은 구성 채우기)
# ---------------------------------------------------------------------------

def place_group(place):
    if is_meal(place):return '식사'
    if place.get('category')=='카페·미식':return '카페'
    return CATEGORY_GROUPS.get(place.get('category'),'기타')


def composition(plan):
    counts=Counter(place_group(p) for p in plan['places'])
    return {g:counts[g] for g in GROUP_ORDER if counts[g]}


def dcomp(a,b):
    """활동 구성 거리: 묶음별 개수 차이의 합 ÷ 2(올림). 기타는 세지 않는다."""
    A,B=composition(a),composition(b)
    l1=sum(abs(A.get(g,0)-B.get(g,0)) for g in GROUP_ORDER)
    return (l1+1)//2


def travel_minutes(plan):
    return sum(r.get('minutes') or 0 for r in plan.get('legs') or [])


def travel_differs(a,b):
    ta,tb=travel_minutes(a),travel_minutes(b)
    return abs(ta-tb)>=max(10,0.3*max(ta,tb))


def confirm_items(plan):
    """방문 전 확인할 항목 수. 계산할 자료가 없으면 None."""
    from .preferences import operating_source_current
    places=plan.get('places');costs=plan.get('costs')
    if places is None or costs is None:return None
    try:
        unconfirmed_places=sum(p.get('hours') is None or p.get('closed_days') is None or not operating_source_current(p) for p in places)
        unconfirmed_costs=sum(r.get('amount') is None or r.get('price_kind')=='planning_assumption' for r in costs)
    except (TypeError,AttributeError,KeyError):return None
    return unconfirmed_places+unconfirmed_costs


def travel_basis(plan):
    from .recommendation_summary import travel_mode
    return travel_mode(plan)['basis']


def fit_key(plan,c):
    from .request_intent import plan_penalty
    from .quality import meal_penalty
    return (plan_penalty(plan,c),meal_penalty(plan,c),plan.get('penalty',0))


def forbidden(plan,c):
    from .request_intent import intent,matches
    excluded=intent(c)['excluded']
    if any(matches(p,k) for p in plan['places'] for k in excluded):return True
    words=[w.lower() for w in c.avoid if w]
    return any(w in (p['name']+' '+p.get('category','')+' '+' '.join(p.get('tags') or [])).lower() for p in plan['places'] for w in words)


def changeable_seats(plan,c):
    return max(0,len(plan['places'])-len(c.locked))


def _difference(plan,base):
    A,B=composition(plan),composition(base)
    added={g:A.get(g,0)-B.get(g,0) for g in GROUP_ORDER if A.get(g,0)>B.get(g,0)}
    removed={g:B.get(g,0)-A.get(g,0) for g in GROUP_ORDER if B.get(g,0)>A.get(g,0)}
    delta=travel_minutes(plan)-travel_minutes(base)
    up,ub=confirm_items(plan),confirm_items(base)
    kinds=['places']
    if dcomp(plan,base):kinds.append('composition')
    if travel_differs(plan,base):kinds.append('travel_shorter' if delta<0 else 'travel_longer')
    confirm_delta=None if up is None or ub is None else up-ub
    if confirm_delta is not None and confirm_delta<=-2:kinds.append('confirm_fewer')
    return dict(base_option=1,places_changed=changed_places(plan,base),composition_changed=dcomp(plan,base),
        added=[dict(group=g,count=n) for g,n in added.items()],removed=[dict(group=g,count=n) for g,n in removed.items()],
        travel_delta_minutes=delta,confirm_delta=confirm_delta,kinds=kinds)


def _counted(rows):
    # 표시 이름에 이미 가운뎃점이 있어('전시·관람') 항목 사이는 쉼표로 나눈다.
    return ', '.join(f"{GROUP_LABELS[r['group']]} {r['count']}곳" for r in rows)


def _same_composition_text(number,changed):
    return f"코스 {number}{'와' if number==2 else '과'} 같은 구성에서 장소 {changed}곳이 달라요"


def _role(plan,base,difference,same_composition_only,chosen=None,stage=1):
    """기준 코스와의 실제 차이로 역할 이름과 설명을 만든다. 모르는 값은 말하지 않는다.
    stage 3(같은 구성으로 채운 안)은 구성이 같은 코스(앞선 코스 중 첫째)와 비교해 장소 차이만 말한다."""
    if stage==3 and chosen:
        for number,other in enumerate(chosen,1):
            if other is plan:break
            if not dcomp(plan,other):
                text=_same_composition_text(number,changed_places(plan,other))
                if number==1 and 'confirm_fewer' in difference['kinds']:text+=f". 확인할 정보도 {-difference['confirm_delta']}개 적어요"
                return SAME_COMPOSITION_ROLE,text
    if same_composition_only and not difference['composition_changed']:
        name=SAME_COMPOSITION_ROLE;text=_same_composition_text(1,difference['places_changed'])
    elif difference['composition_changed']:
        added,removed=difference['added'],difference['removed']
        if added:name=', '.join(GROUP_LABELS[r['group']] for r in added)+' 넣은 코스'
        else:name='구성이 다른 코스'
        if added and removed:text=f'코스 1의 {_counted(removed)} 대신 {_counted(added)}이 들어가요'
        elif added:text=f'코스 1에 없던 {_counted(added)}이 들어가요'
        else:text=f'코스 1의 {_counted(removed)}이 빠져요'
    else:
        basis='길찾기 조회 기준' if travel_basis(plan)=='네이버 길찾기' and travel_basis(base)=='네이버 길찾기' else '추정 기준'
        delta=difference['travel_delta_minutes']
        if delta<0:name='이동이 짧은 안';text=f'약 {-delta}분 짧아요({basis})'
        else:name='같은 활동 · 다른 동선';text=f'코스 1과 활동 구성은 같고 이동이 약 {delta}분 길어요({basis})'
    if 'confirm_fewer' in difference['kinds']:text+=f". 확인할 정보도 {-difference['confirm_delta']}개 적어요"
    return name,text


def _experience(plan):
    return dict(composition=composition(plan),travel_minutes=travel_minutes(plan),travel_basis=travel_basis(plan),
        confirm_items=confirm_items(plan),version=EXPERIENCE_VERSION)


# 3안 선택 단계(exp-v2). 자리마다 1단계부터 차례로 찾고, 앞 단계에 후보가 없을 때만 다음 단계로 내려간다.
# 1단계: 구성이나 이동이 이미 고른 모든 안과 다르고 장소도 min(2, 바꿀 수 있는 자리)곳 이상 다른 안(exp-v1 규칙).
# 2단계: 구성이나 이동은 다르고 장소는 1곳 이상 다른 안(1단계의 장소 기준만 낮춤). 식당 하나를 거의 모든 조합이 공유하는 지역(경주 황리단길 재현:
#        식당 1곳이 41개 조합 전부에 들어감)에서는 바꿀 수 있는 자리가 사실상 2곳이라, 1단계 기준으로는 셋째 안이 모두
#        'places'로 빠진다. 장소 집합이 완전히 같은 안은 고르지 않는다.
# 3단계: 구성까지 같은 안 중 장소가 다른 안(기존 place 선택기 규칙: 장소 차이 우선, 둘째 자리는 장소 차이, 셋째 자리는 이동·비용).
# 모든 단계에서 적합도(기준 코스보다 요청 조건에 덜 맞는 안 제외)·금지 조건을 지키고, 후보 풀이 이미 고정 장소·필수 조건을 지킨다.
STAGES=(1,2,3)


def _choose(candidates,c,chosen,limit=3):
    """chosen(이미 고른 안, 첫 안이 기준)에 candidates 중 다른 안을 limit개까지 단계별로 더한다.
    반환: (추가로 고른 안 목록, 후보별 1단계 기준 마지막 탈락 사유 dict[id(plan)]=사유, 고른 안별 단계 목록)."""
    base=chosen[0];base_fit=fit_key(base,c);picked=[];stages=[]
    same_composition_only=c.theme_mode=='focus' or changeable_seats(base,c)==0
    required=min(2,changeable_seats(base,c))
    remaining=list(candidates);reasons={}
    def differs(p,current):
        return same_composition_only or all(dcomp(p,q)>=1 or travel_differs(p,q) for q in current)
    while remaining and len(chosen)+len(picked)<limit:
        current=chosen+picked;fit=[];stage_one=[]
        for p in remaining:
            if any(a>b for a,b in zip(fit_key(p,c),base_fit)):reasons[id(p)]='fit';continue
            fit.append(p)
            if any(changed_places(p,q)<required for q in current):reasons[id(p)]='places'
            elif not differs(p,current):reasons[id(p)]='same_experience'
            else:reasons.pop(id(p),None);stage_one.append(p)
        novelty={id(p):min(changed_places(p,q) for q in current) for p in fit}
        distinct=[p for p in fit if novelty[id(p)]>=1]
        if stage_one:
            stage=1;pick=min(stage_one,key=lambda p:(-min(dcomp(p,q) for q in current),remaining.index(p)))
        elif not same_composition_only and (stage_two:=[p for p in distinct if differs(p,current)]):
            stage=2;pick=min(stage_two,key=lambda p:(-min(dcomp(p,q) for q in current),-novelty[id(p)],remaining.index(p)))
        elif distinct:
            stage=3;most=max(novelty[id(p)] for p in distinct)
            eligible=[p for p in distinct if novelty[id(p)]>=min(required,most)]
            if len(current)==1:pick=min(eligible,key=lambda p:(-novelty[id(p)],p.get('penalty',0),remaining.index(p)))
            else:pick=min(eligible,key=lambda p:(travel_minutes(p),p['total'][1],p.get('penalty',0),remaining.index(p)))
        else:break
        picked.append(pick);stages.append(stage);remaining.remove(pick);reasons.pop(id(pick),None)
    return picked,reasons,stages


def _unique(plans):
    unique=[]
    for plan in plans:
        if not any(len(plan['places'])==len(p['places']) and changed_places(plan,p)==0 for p in unique):unique.append(plan)
    return unique


def composition_label(plan):
    """'식사+카페+보기'처럼 묶음 이름만으로 된 구성 표시(장소 이름 없음). 기타도 그대로 센다."""
    counts=Counter(place_group(p) for p in plan['places'])
    return '+'.join(g for g in GROUP_ORDER+['기타'] for _ in range(counts[g]))


def pool_stats(plans,top=8):
    """선택기에 들어온 후보 풀 요약: 장소 집합 수, 구성 종류 수, 구성별 후보 수(상위 top개)."""
    unique=_unique(plans)
    counts=Counter(composition_label(p) for p in unique)
    return dict(unique_sets=len(unique),distinct_compositions=len(counts),
        pool_compositions=dict(sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))[:top]))


def experience_select(plans,c):
    """새 선택기. 입력 plan은 바꾸지 않고 (고른 안, 안별 표시 정보, 진단)을 돌려준다."""
    unique=_unique(plans)
    allowed=[p for p in unique if not forbidden(p,c)]
    rejected=Counter(forbidden=len(unique)-len(allowed))
    chosen=[];annotations=[];stages=[]
    if allowed:
        base=allowed[0]
        picked,reasons,stages=_choose(allowed[1:],c,[base])
        chosen=[base]+picked
        rejected.update(reasons.values())
        annotations=annotate(chosen,[None]+stages,c,_shortfall_note(len(chosen),len(allowed),rejected,base,c,filled=3 in stages))
    diagnostics=dict(input_plans=len(plans),unique_sets=len(unique),
        distinct_compositions=len({tuple(sorted(composition(p).items())) for p in unique}),
        rejected={k:v for k,v in rejected.items() if v},returned=len(chosen),shortfall=max(0,3-len(chosen)),
        picked_by_stage={str(s):stages.count(s) for s in STAGES})
    return chosen,annotations,diagnostics


def _labels(rows):
    return ', '.join(GROUP_LABELS[r['group']] for r in rows)


def _distinct_role(name,text,plan,other,number,difference,other_difference):
    """앞선 코스(other, 코스 number)와 역할 이름이 같을 때 둘 사이의 실제 차이로 이름을 다시 짓는다.
    활동 → 이동 순서로 보고, 이름으로 나타낼 차이가 없으면 사실인 꼬리말(· 다른 장소)만 붙인다."""
    josa='와' if number==2 else '과'
    changed=changed_places(plan,other)
    if name==SAME_COMPOSITION_ROLE:
        return '같은 구성 · 또 다른 장소',text+f'. 코스 {number}{josa}도 장소 {changed}곳이 달라요'
    if dcomp(plan,other):
        removed,added=difference['removed'],difference['added']
        if removed and removed!=other_difference['removed']:
            if name.endswith(' 넣은 코스'):return _labels(removed)+' 대신 '+name,text
            return _labels(removed)+' 뺀 코스',text
        if added and added!=other_difference['added']:return _counted(added)+' 넣은 코스',text
    if travel_differs(plan,other):
        delta=travel_minutes(plan)-travel_minutes(other)
        text+=f". 코스 {number}보다 이동이 약 {abs(delta)}분 {'짧아요' if delta<0 else '길어요'}"
        if name=='이동이 짧은 안' and delta<0:return '이동이 가장 짧은 안',text
        if name=='같은 활동 · 다른 동선':return '같은 활동 · 또 다른 동선',text
        return name+(' · 더 짧은 이동' if delta<0 else ' · 다른 동선'),text
    return name+' · 다른 장소',text+f'. 코스 {number}{josa}는 장소 {changed}곳이 달라요'


def annotate(chosen,stages,c,note):
    """고른 안마다 표시 정보(역할 이름·설명·기준 코스와의 차이)를 만든다. stages[0]은 기준 코스(None).
    한 응답 안에서 역할 이름은 겹치지 않는다. 뒤에 고른 안의 이름을 앞선 안과의 실제 차이로 다시 짓는다."""
    base=chosen[0];annotations=[]
    same_composition_only=c.theme_mode=='focus' or changeable_seats(base,c)==0
    for i,p in enumerate(chosen):
        others=[q for q in chosen if q is not p]
        minimum=min((changed_places(p,q) for q in others),default=len(p['places']))
        row=dict(experience=_experience(p),diversity_note=note,minimum_different_places=minimum)
        if i==0:row.update(option_purpose=BASE_ROLE[0],option_description=BASE_ROLE[1],difference=None)
        else:
            difference=_difference(p,base);difference['selection_stage']=stages[i]
            name,text=_role(p,base,difference,same_composition_only,chosen,stages[i])
            same=next((j for j,r in enumerate(annotations) if r['option_purpose']==name),None)
            if same is not None:
                name,text=_distinct_role(name,text,p,chosen[same],same+1,difference,annotations[same]['difference'])
                if any(r['option_purpose']==name for r in annotations):
                    name=annotations[same]['option_purpose']+' · 다른 장소'
            row.update(option_purpose=name,option_description=text,difference=difference)
        annotations.append(row)
    return annotations


def _shortfall_note(returned,allowed,rejected,base,c,filled=False):
    notes=[]
    if filled:notes.append('활동 구성이나 이동이 다른 조합이 부족해 같은 구성에서 장소만 다른 코스를 함께 보여요.')
    if returned<3:
        if rejected.get('same_experience'):notes.append(f"활동 구성이나 이동이 다른 코스를 찾지 못해 {returned}개만 보여요. 장소만 바꾸려면 '장소 바꾸기'를 이용해 주세요.")
        if rejected.get('fit'):notes.append('다른 구성의 조합은 요청 조건과 덜 맞아 제외했어요.')
        if allowed==1:notes.append(f'조건에 맞는 장소 조합이 {allowed}개뿐이에요.')
        if not notes:notes.append(f'서로 다른 장소 조합이 부족해 {returned}개만 보여요.')
    if c.locked:
        notes.append(f'고정한 장소 {len(c.locked)}곳은 모든 코스에서 유지해요.')
        seats=changeable_seats(base,c)
        if seats<=1:notes.append(f'바꿀 수 있는 자리가 {seats}곳뿐이에요.')
    return ' '.join(notes)


def apply_experience(chosen,annotations):
    for plan,row in zip(chosen,annotations):plan.update(row)
    return chosen


def reserve_candidates(pool,chosen,c,limit=12):
    """고르지 않은 후보 중 기준 코스(chosen 첫 안) 대비 자격이 있는 후보 limit개.
    구성(composition_label)별로 처음 나온 순서대로 한 개씩 돌아가며 고른다(구성 안에서는 입력 순서, 결정적).
    조건 완화 경로에서는 원래 조건 기준 차이(penalty)가 나중에 붙어, 입력 순서 상위가 한두 구성에 몰려 있으면 그 구성이
    모두 적합도 가드에 걸리고 다른 구성·같은 구성(3단계 채우기용) 후보가 예비에 남지 않는다. 구성을 고르게 남겨 그 경우를 막는다."""
    if not chosen:return []
    base=chosen[0];base_fit=fit_key(base,c);picked={id(p) for p in chosen}
    groups={}
    for p in _unique([q for q in pool if id(q) not in picked]):
        if any(changed_places(p,q)==0 for q in chosen) or forbidden(p,c):continue
        if any(a>b for a,b in zip(fit_key(p,c),base_fit)):continue
        groups.setdefault(composition_label(p),[]).append(p)
    rows=[];depth=0
    while len(rows)<limit and any(len(g)>depth for g in groups.values()):
        rows+=[g[depth] for g in groups.values() if len(g)>depth][:limit-len(rows)];depth+=1
    return rows


def refill_candidates(kept,reserve,c,limit=2):
    """가격 확인 뒤 줄어든 코스를 채울 예비 후보. kept 첫 안을 기준으로 같은 단계 규칙(_choose)을 적용한다."""
    pool=[p for p in _unique(reserve) if not forbidden(p,c) and all(changed_places(p,q) for q in kept)]
    if not pool:return []
    if not kept:
        picked,_,_=_choose(pool[1:],c,[pool[0]],limit=min(3,limit))
        return ([pool[0]]+picked)[:limit]
    picked,_,_=_choose(pool,c,list(kept),limit=min(3,len(kept)+limit))
    return picked


# ---------------------------------------------------------------------------
# 선택 모드 분기
# ---------------------------------------------------------------------------

def _ids(plans):
    return [[p['id'] for p in plan['places']] for plan in plans]


def select_options(plans,c,diagnostics=None,stage='planner'):
    """설정된 선택 모드로 코스를 고른다. diagnostics(dict)를 주면 option_selection을 기록한다."""
    from .config import option_selector
    selector=option_selector()
    plans=list(plans)
    record=dict(selector=selector,stage=stage,input_plans=len(plans),unique_sets=None,distinct_compositions=None,
        pool_compositions=None,rejected={},returned=0,shortfall=None,legacy_ids=None,experience_ids=None,error=None)
    try:record.update(pool_stats(plans))
    except Exception as exc:
        # 진단 계산 실패가 추천을 막지 않게 한다(experience 모드는 아래 선택에서 같은 계산을 다시 한다).
        record['error']=type(exc).__name__
    if selector=='experience':
        chosen,annotations,stats=experience_select(plans,c)
        record.update(stats,experience_ids=_ids(chosen),error=None)
        result=apply_experience(chosen,annotations)
    else:
        result=legacy_select_options(plans,c)
        record.update(legacy_ids=_ids(result),returned=len(result),shortfall=max(0,3-len(result)))
        if selector=='shadow':
            try:
                chosen,_,stats=experience_select(plans,c)
                record.update({k:v for k,v in stats.items() if k not in ('returned','shortfall')},experience_ids=_ids(chosen),
                    experience_returned=stats['returned'],experience_shortfall=stats['shortfall'])
            except Exception as exc:
                record['error']=type(exc).__name__
            _log(record)
    if diagnostics is not None:diagnostics['option_selection']=record
    return result


def _log(record):
    # 장소 ID와 숫자만 남긴다. 요청 문장·출발지·좌표는 넣지 않는다.
    try:
        rejected=','.join(f'{k}:{v}' for k,v in sorted(record['rejected'].items())) or '-'
        def ids(rows):return '|'.join('+'.join(row) for row in rows) if rows is not None else '-'
        logging.getLogger(__name__).info(
            'option_selection_shadow stage=%s input=%s unique=%s compositions=%s pool=%s rejected=%s legacy_returned=%s experience_returned=%s legacy=%s experience=%s error=%s',
            record['stage'],record['input_plans'],record['unique_sets'],record['distinct_compositions'],
            ','.join(f'{k}:{v}' for k,v in (record['pool_compositions'] or {}).items()) or '-',rejected,
            record['returned'],record.get('experience_returned','-'),ids(record['legacy_ids']),ids(record['experience_ids']),record['error'] or '-')
    except Exception:
        logging.getLogger(__name__).warning('option_selection_log_failed')
