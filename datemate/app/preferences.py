"""필수 조건은 불일치·미확인 상태를 통과시키지 않는다. 추정은 명시한다."""
from datetime import datetime,timezone

def hard_blocks(plan):
    required=set(plan.get('conditions',{}).get('hard_constraints',[]))
    if 'themes' in required:required.update(['date_subcategory','request_activity'])
    return [c for c in plan.get('condition_checks',[]) if c['condition'] in required and c['state'] in ('unmet','unknown')]

def filter_required(plans):return [p for p in plans if not hard_blocks(p)]

def operating_source_current(place):
    if not place.get('operations_source') or place.get('hours') is None or place.get('closed_days') is None:return False
    try:age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(place['operations_checked_at']).date()).days
    except (KeyError,ValueError,TypeError):return False
    return 0<=age<=90

def fit_score(plan,c):
    from .taxonomy import concept_score
    weights={'balanced':{},'talk':{'카페·미식':1,'휴식·힐링':1},'food':{'카페·미식':1},'photo':{'산책·풍경':1,'문화·예술':.5},'activity':{'체험·제작':1,'레저·활동':1,'오락·놀이':1}}
    value=sum(weights[c.priority].get(p['category'],0)+(1 if c.priority=='food' and p.get('meal') else 0)-3*bool(p.get('report_pending')) for p in plan['places'])
    value+=sum(concept_score(p,c) for p in plan['places'])
    if c.trust_mode=='discovery':value+=sum(p['id'].startswith('discovered:') for p in plan['places'])
    if c.trust_mode=='balanced':value+=.25*sum(operating_source_current(p) for p in plan['places'])
    if c.meeting_type=='first':value-=sum(r['minutes'] for r in plan['legs'])*.03
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
