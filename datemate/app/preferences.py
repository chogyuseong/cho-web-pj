"""필수 조건은 불일치·미확인 상태를 통과시키지 않는다. 추정은 명시한다."""
from datetime import datetime,timezone

def hard_blocks(plan):
    required=set(plan.get('conditions',{}).get('hard_constraints',[]))
    if 'themes' in required:required.update(['date_subcategory','request_activity'])
    return [c for c in plan.get('condition_checks',[]) if c['condition'] in required and c['state'] in ('unmet','unknown')]

def filter_required(plans):return [p for p in plans if not hard_blocks(p)]

def operating_source_current(place):
    evidence=place.get('operations_evidence',{})
    if 'hours' in evidence and 'closed_days' in evidence:return bool(evidence['hours']['current'] and evidence['closed_days']['current'])
    if not place.get('operations_source') or place.get('hours') is None or place.get('closed_days') is None:return False
    if 'operations_verified_fields' in place and not {'hours','closed_days'}.issubset(place['operations_verified_fields']):return False
    try:age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(place['operations_checked_at']).date()).days
    except (KeyError,ValueError,TypeError):return False
    return 0<=age<=90

def fit_score(plan,c):
    from .taxonomy import concept_score
    weights={'balanced':{},'talk':{'카페·미식':1,'휴식·힐링':1},'food':{'카페·미식':1},'photo':{'산책·풍경':1,'문화·예술':.5},'activity':{'체험·제작':1,'레저·활동':1,'오락·놀이':1}}
    value=sum(weights[c.priority].get(p['category'],0)+(1 if c.priority=='food' and p.get('meal') else 0)-3*bool(p.get('report_pending')) for p in plan['places'])
    # 화면이 대신 넣은 데이트 분류(홈 동네 카드)는 거르지 않고, 분류에 맞는 장소가 든 코스에 1점, 분류 키워드 점수는
    # 코스에서 가장 높은 1곳만 더해 먼저 넣는다. 장소마다 합산하면 분류에 다 맞는 조합만 빔의 최상위 등급을 채워
    # (구성 할당은 같은 등급 안에서만 자리를 옮긴다) 3안이 한 구성으로 모인다(경주 '지적인 데이트': 식사+보기+하기 33개).
    # 사용자가 직접 고른 분류는 지금처럼 장소마다 합산한다.
    from .taxonomy import preferred_themes,matches_classification
    preferred=preferred_themes(c)
    concept=[concept_score(p,c) for p in plan['places']]
    if preferred:value+=max(concept,default=0)+any(matches_classification(p,preferred) for p in plan['places'])
    else:value+=sum(concept)
    if c.trust_mode=='discovery':value+=sum(p['id'].startswith('discovered:') for p in plan['places'])
    if c.trust_mode=='balanced':value+=.25*sum(operating_source_current(p) for p in plan['places'])
    if c.meeting_type=='first':value-=sum(r['minutes'] for r in plan['legs'])*.03
    from .request_intent import intent
    # '저렴하게·가성비' 요청: 같은 조건이면 비용 상한이 낮은 조합을 앞에 둔다(2만 원당 1점).
    if intent(c).get('budget_style')=='low':value-=(plan.get('total') or [0,0])[1]/20000
    if c.use_feedback:
        from .feedback_preferences import bonus
        value+=bonus(plan)
    return value

def selection_notes(c):
    notes=[]
    from .taxonomy import CONCEPT_PROFILES
    if c.date_subcategory in CONCEPT_PROFILES:notes.append(c.date_subcategory+': 장소명·설명의 '+', '.join(CONCEPT_PROFILES[c.date_subcategory]['keywords'][:4])+' 관련 단서를 우선 비교했어요. 실제 분위기는 별도 확인이 필요해요.')
    if c.meeting_type=='first':notes.append('첫 만남: 이동 부담이 적은 조합을 우선 비교했어요.')
    if c.meeting_type=='anniversary':notes.append('기념일: 예약·운영 확인이 필요해요. 기념일 적합성 자체를 보장하지는 않아요.')
    messages={'talk':'대화 우선: 카페·휴식 유형을 선호해요. 실제 소음·좌석 정보는 별도 확인이 필요해요.','food':'음식 우선: 식당·미식 유형을 우선 비교했어요.','photo':'사진 우선: 산책·문화 유형을 선호해요. 촬영 가능 여부·인파는 확인이 필요해요.','activity':'체험 우선: 공방·레저·놀이 유형을 우선 비교했어요.'}
    if c.priority in messages:notes.append(messages[c.priority])
    if c.hard_constraints:notes.append('필수 조건은 계산된 정보로 검사하며, 예산·이동이 추정이면 실제 결과와 다를 수 있어요.')
    return notes
