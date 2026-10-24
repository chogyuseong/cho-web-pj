"""Shared, transparent interpretation of both search text and free-form requests."""
import re
from functools import lru_cache

INTENTS={
 'cafe':('카페·미식',['카페','커피','디저트','카페투어','카페 투어','베이커리','티하우스']),
 'meal':('카페·미식',['맛집','식사','밥집','밥먹','밥 먹','음식점','레스토랑']),
 'culture':('문화·예술',['전시','미술관','갤러리']),
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
    active=[];excluded=[];residual=text
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
    for pattern,key in [(r'([1-9]|1\d|20)\s*명','people'),(r'([2-5])\s*(?:곳|군데)','count')]:
        m=re.search(pattern,text)
        if m:patch[key]=int(m[1])
    if 'people' not in patch:
        for word,value in [('둘이',2),('두 명',2),('셋이',3),('세 명',3),('넷이',4),('네 명',4)]:
            if word in text:patch['people']=value;break
    m=re.search(r'(\d+)\s*만\s*(?:(\d+)\s*천\s*)?원',text)
    if m:
        amount=int(m[1])*10000+int(m[2] or 0)*1000
        if 0<=amount<=10000000:patch['budget']=amount
    else:
        m=re.search(r'(?<!\d)(\d[\d,]*)\s*원',text)
        if m and int(m[1].replace(',',''))<=10000000:patch['budget']=int(m[1].replace(',',''))
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
    return dict(intents=active,excluded=excluded,exclusive=exclusive,patch=patch)


def intent(c):return interpret(c.course_query+' '+c.request)


def normalize(c):
    parsed=intent(c)
    patch=dict(parsed['patch'])
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
