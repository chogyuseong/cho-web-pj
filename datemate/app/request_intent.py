"""Shared, transparent interpretation of both search text and free-form requests."""
import re
from decimal import Decimal
from functools import lru_cache

INTENTS={
 'cafe':('카페·미식',['카페','커피','디저트','카페투어','카페 투어','베이커리','티하우스']),
 'meal':('카페·미식',['맛집','식사','밥집','밥먹','밥 먹','음식점','레스토랑']),
 'culture':('문화·예술',['전시','미술관','갤러리']),
 'cinema':('문화·예술',['영화관','영화','시네마']),
 'performance':('문화·예술',['공연','연극','뮤지컬','콘서트']),
 'jazz':('문화·예술',['재즈바','재즈 바','재즈클럽','재즈 클럽']),
 'museum':('문화·예술',['박물관','역사']),
 'book':('문화·예술',['서점','책방','도서관','북카페']),
 'workshop':('체험·제작',['공방','도자기','원데이','향수','반지 만들','만들기']),
 'walk':('산책·풍경',['산책','공원','정원','숲길','피크닉','한강']),
 'game':('오락·놀이',['방탈출','보드게임','오락실','게임','만화카페']),
 'activity':('레저·활동',['운동','레저','스포츠']),
 'climbing':('레저·활동',['클라이밍','볼더링','암벽']),
 'bowling':('레저·활동',['볼링']),
 'table_tennis':('레저·활동',['탁구']),
 'badminton':('레저·활동',['배드민턴']),
 'skating':('레저·활동',['스케이트','스케이팅','아이스링크']),
 'screen_golf':('레저·활동',['스크린골프','스크린 골프']),
 'view':('산책·풍경',['야경','전망','노을','일몰']),
 'shopping':('오락·놀이',['쇼핑','소품샵','소품숍','편집샵','편집숍']),
}


@lru_cache(maxsize=512)
def interpret(text):
    # Separate short clauses so '카페 말고 전시' does not negate the exhibition too.
    active=[];excluded=[];warnings=[]
    for key,(_,words) in INTENTS.items():
        yes=False;no=False
        for word in sorted(words,key=len,reverse=True):
            for m in re.finditer(re.escape(word),text,re.I):
                tail=text[m.end():m.end()+16]
                negative=bool(re.match(r'\s*(?:는|은|을|를|도|에)?\s*(?:말고|빼|제외|싫|별로|좋아하지|안\s*(?:좋아|원해|가|갈|먹|마[시셔])|못\s*(?:가|먹|마[시셔])|피하|없이|없[는이])',tail))
                no|=negative;yes|=not negative
        if no:excluded.append(key)
        elif yes:active.append(key)
    patch={}
    if active:patch['themes']=list(dict.fromkeys(INTENTS[key][0] for key in active))
    if re.search(r'실내|비\s*(?:오는|와|가\s*오)|비올|우천',text):patch['setting']='indoor'
    elif re.search(r'야외|실외',text):patch['setting']='outdoor'
    if re.search(r'실내\s*(?:말고|제외|싫)',text):patch['setting']='outdoor'
    if re.search(r'야외\s*(?:말고|제외|싫)',text):patch['setting']='indoor'
    if re.search(r'비\s*(?:가\s*)?(?:오면|온다면)|맑으면|날씨에\s*따라',text):
        patch.pop('setting',None)
        warnings.append('날씨에 따른 조건부 요청이 있어요. 자동으로 실내·야외를 확정하지 않았으니 방문일에 맞춰 선택해 주세요.')
    for pattern,key in [(r'(?<!\d)([1-9]|1\d|20)\s*명','people'),(r'(?<!\d)([2-5])\s*(?:곳|군데)','count')]:
        m=re.search(pattern,text)
        if m:patch[key]=int(m[1])
    if 'people' not in patch:
        for word,value in [('둘이',2),('두 명',2),('셋이',3),('세 명',3),('넷이',4),('네 명',4)]:
            if word in text:patch['people']=value;break
    amounts=[]
    for m in re.finditer(r'(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*(?:(만)\s*(?:(\d+)\s*천\s*)?|(천)\s*)?원',text):
        value=Decimal(m[1].replace(',',''))*(10000 if m[2] else 1000 if m[4] else 1)+int(m[3] or 0)*1000
        if value==int(value):amounts.append(int(value))
    if len(amounts)==1 and 0<=amounts[0]<=10000000:patch['budget']=amounts[0]
    elif amounts:warnings.append('금액이 여러 개이거나 지원 예산 범위를 벗어나 자동 적용하지 않았어요. 전체 예산을 직접 확인해 주세요.')
    if re.search(r'대중교통|지하철|버스',text):patch['transport']='transit'
    elif re.search(r'자차|자가용|자동차',text):patch['transport']='car'
    elif re.search(r'걸어서|도보',text):patch['transport']='walk'
    if re.search(r'예약\s*(?:없이|안|없는)',text):patch['reservation']=False
    if re.search(r'사진|인생샷|포토',text):patch['priority']='photo'
    elif re.search(r'대화|조용|이야기',text):patch['priority']='talk'
    m=re.search(r'(?:총\s*)?(?:도보|걷기)\s*(\d+)\s*분\s*(?:이내|이하)',text)
    if m and int(m[1])<=600:patch['max_walk']=int(m[1])
    exclusive=len(active)==1 and bool(re.search(r'투어|위주|만\s*(?:가|갈|돌|보고|보고싶|추천|원해)|만$',text))
    if exclusive:
        patch['theme_mode']='focus'
        if active[0]!='meal':patch['include_meal']=False
    per_person=bool(re.search(r'(?<!\d)(?:1\s*인(?:당)?|한\s*(?:사람|명)당|인당|각자|각각)\s*(?:예산(?:은|이)?\s*)?(?:[은는]\s*)?\d|원\s*/\s*인',text))
    unit_budget=patch.pop('budget',None) if per_person else None
    if unit_budget is not None:
        warnings.append(f'1인당 {unit_budget:,}원은 선택한 인원수로 곱해 전체 예산에 반영해요.')
    return dict(intents=active,excluded=excluded,exclusive=exclusive,patch=patch,
                unit_budget=unit_budget,warnings=warnings)


def resolved_patch(parsed,people=2,explicit_people=False):
    """Resolve per-person amounts with the actual form, never a cached total."""
    patch=dict(parsed['patch'])
    if explicit_people:patch.pop('people',None)
    if parsed.get('unit_budget') is not None:
        total=parsed['unit_budget']*patch.get('people',people)
        if total<=10000000:patch['budget']=total
    return patch


def intent(c):return interpret(c.course_query+' '+c.request)


def normalize(c):
    parsed=intent(c)
    patch=resolved_patch(parsed,c.people,'people' in c.explicit_fields)
    # Explicit free text takes precedence over the generic quick-start concept.
    if parsed['intents']:
        patch.update(date_category='',date_subcategory='')
    for key in c.explicit_fields:
        patch.pop(key,None)
    if 'count' in patch and any(i>=patch['count'] for i in c.locked):patch.pop('count')
    return type(c).model_validate(c.model_dump()|patch)


def matches(place,key):
    text=' '.join(str(v) for v in [place.get('name'),place.get('description'),place.get('cuisine'),*(place.get('tags') or [])] if v).casefold()
    meal=bool(place.get('meal')) or place.get('id','').startswith('food:') or 'restaurant' in (place.get('tags') or [])
    if key=='meal':return meal
    if key=='cafe':
        # A broad dining theme attached to a museum is not evidence of a cafe.
        cafe_text=' '.join(str(v) for v in [place.get('name'),place.get('description'),place.get('cuisine'),
            *(t for t in (place.get('tags') or []) if t!='카페·미식')] if v).casefold()
        return not meal and (bool(re.search(r'카페|커피|디저트|베이커리|티하우스|찻집|cafe|coffee',cafe_text)) or 'cafe' in (place.get('tags') or []))
    if key in (place.get('tags') or []):return True
    return any(w.casefold() in text for w in INTENTS[key][1])


def place_score(place,c):
    parsed=intent(c)
    return sum(matches(place,k) for k in parsed['intents'])*5


def plan_penalty(plan,c):
    parsed=intent(c);venues=plan['places']
    missing=sum(not any(matches(p,k) for p in venues) for k in parsed['intents'])
    off=sum(not any(matches(p,k) for k in parsed['intents']) for p in venues) if parsed['exclusive'] else 0
    excluded=sum(any(matches(p,k) for k in parsed['excluded']) for p in venues)
    return excluded*10+missing*5+off


def search_terms(c):
    parsed=intent(c)
    return [INTENTS[k][1][0] for k in parsed['intents']]
