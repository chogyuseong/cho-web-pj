"""Shared, transparent interpretation of both search text and free-form requests."""
import re
from decimal import Decimal
from functools import lru_cache
from .sports import SPORTS,BY_KEY as SPORT_BY_KEY,OUTDOOR_KEYS

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
 # 종목(클라이밍·볼링·…·패러글라이딩)은 app/sports.py 한 곳에서 정의한다. 판별은 혼동 방지 정규식을 쓴다.
 **{s.key:('레저·활동',list(s.words)) for s in SPORTS},
 'view':('산책·풍경',['야경','전망','노을','일몰']),
 'shopping':('오락·놀이',['쇼핑','소품샵','소품숍','편집샵','편집숍']),
 'rest':('휴식·힐링',['힐링','휴식','스파','찜질방','족욕','온천']),
}
# 요청 문장에서만 쓰는 흔한 표현. 장소 이름 대조(matches)에는 쓰지 않는다:
# '바다'·'체험' 같은 넓은 말로 엉뚱한 장소가 활동에 맞거나 제외되면 안 된다.
REQUEST_WORDS={
 'cafe':['브런치','찻집','빵집','로스터리','티룸'],
 'meal':['먹으러','먹고 싶','맛있는 거','맛있는 곳','오마카세','파인다이닝','파인 다이닝','고깃집','미식'],
 'culture':['전시회','미술','아트센터','미디어아트'],
 'cinema':['무비','상영관'],
 'performance':['연주회','오페라','발레','국악','버스킹','공연장'],
 'museum':['과학관','기념관','유적','고궁','궁궐'],
 'book':['독서','북스테이','책 읽'],
 'workshop':['원데이클래스','원데이 클래스','클래스','체험','쿠킹','베이킹','캔들','가죽 공예','목공','꽃꽂이','플라워','드로잉','그림 그리'],
 'walk':['걷기','걷고','걷는','걸으며','둘레길','강변','호숫가','호수','해변','바닷가','바다','수목원','식물원','꽃구경','꽃놀이','벚꽃','단풍','나들이'],
 'game':['코인노래방','노래방','피시방','PC방','VR'],
 'activity':['액티비티'],
 'view':['경치','풍경','오션뷰','루프탑','전망대','해돋이','일출','석양'],
 'shopping':['아울렛','백화점','쇼핑몰','플리마켓','시장 구경','팝업스토어','팝업 스토어'],
 'rest':['쉬고 싶','쉬러','쉬엄쉬엄','마사지','템플스테이','호캉스'],
}
# 단어 바로 뒤의 부정 표현. '카페 말고 전시'에서 전시까지 부정하지 않도록 짧은 꼬리만 본다.
NEGATIVE=re.compile(r'\s*(?:는|은|을|를|도|에|건|거는|거|게|것은|것도|쪽은)?\s*(?:말고|빼|제외|싫|별로|좋아하지|않|'
    r'안\s*(?:좋아|원해|가|갈|먹|마[시셔]|땡|끌|해)|못\s*(?:가|먹|마[시셔]|걷|해)|피하|피해|없이|없[는이]|패스|지겨|질려|질렸|힘들|'
    r'관심\s*없|알레르기|알러지|[가-힣]{1,2}기\s*싫|(?:[가-힣]{1,2}고\s*)?싶지\s*않|원하지\s*않)')
# '안 매운', '못 걷고' 처럼 단어 앞에서 부정하는 경우.
NEGATED_BEFORE=re.compile(r'(?:^|[^가-힣])(?:안|못)\s*$')
# 음식 제외는 장소 유형이 아니라 이름·분류 단어로 거른다(메뉴까지 확인하지는 않는다).
FOOD_AVOID=[
 (r'매운|매콤|얼큰|맵(?:지|고|게|기|찔|다)|마라|불닭','매운 음식',['매운','마라','불닭','짬뽕','떡볶이','닭발','쭈꾸미','낙지']),
 (r'(?<![가-힣])술(?:집)?|음주|알코올|알콜','술',['술집','주점','포차','호프','이자카야','와인바','칵테일바']),
 (r'해산물|해물|생선|조개|갑각류','해산물',['해산물','해물','횟집','수산','조개','생선']),
]
RAIN=r'비\s*(?:오는|와|가\s*오)|비올|우천|장마|소나기'
SNOW=r'눈\s*(?:오는|와서|이\s*오|내리|올)|폭설|함박눈'
# '영하'는 '수영하고'처럼 낱말 안에 섞이므로 앞에 한글이 붙으면 보지 않는다.
HARSH=r'폭염|무더위|더운\s*날|더워|한파|추운\s*날|추워|(?<![가-힣])영하|미세\s*먼지|황사'
SEASONS=[('봄',r'(?<![가-힣])봄(?![가-힣])|(?<![가-힣])봄(?:날|철|꽃|나들이|에|엔)'),('여름',r'(?<![가-힣])여름|바캉스|피서'),
    ('가을',r'(?<![가-힣])가을'),('겨울',r'(?<![가-힣])겨울|크리스마스|연말')]
CONCEPTS=[('콘셉트별','즐거운 데이트',r'즐거운|신나는|재밌는|재미있는'),('콘셉트별','편안한 데이트',r'편안한|편하게|여유로운|여유롭|느긋|한적'),
    ('콘셉트별','지적인 데이트',r'지적인|배우는|교양'),('콘셉트별','동심 데이트',r'동심|어릴\s*적|키덜트|레트로\s*게임'),
    ('타입별','활동적인',r'활동적|액티브|몸\s*(?:쓰는|움직)|땀\s*흘리'),('타입별','사교적인',r'사교적|여럿이|사람들과\s*어울')]


def negated(text,m):
    return bool(NEGATIVE.match(text,m.end(),m.end()+20)) or bool(NEGATED_BEFORE.search(text[max(0,m.start()-6):m.start()]))


def request_words(key):return INTENTS[key][1]+REQUEST_WORDS.get(key,[])


@lru_cache(maxsize=512)
def interpret(text):
    # Separate short clauses so '카페 말고 전시' does not negate the exhibition too.
    active=[];excluded=[];warnings=[]
    for key in INTENTS:
        yes=False;no=False
        if key in SPORT_BY_KEY:found=SPORT_BY_KEY[key].request_re.finditer(text)
        else:found=(m for word in sorted(request_words(key),key=len,reverse=True) for m in re.finditer(re.escape(word),text,re.I))
        for m in found:
            negative=negated(text,m)
            no|=negative;yes|=not negative
        if no:excluded.append(key)
        elif yes:active.append(key)
    patch={}
    from .regions import REGIONS
    for region,names in REGIONS.items():
        if any(re.search(r'(?<![가-힣])'+re.escape(name)+r'(?=\s|에서|으로|로|에|의|$)',text) for name in sorted(names,key=len,reverse=True)):
            patch['region']=region
            break
    if active:patch['themes']=list(dict.fromkeys(INTENTS[key][0] for key in active))
    rain,snow,harsh=(re.search(p,text) for p in (RAIN,SNOW,HARSH))
    outdoor_wish=bool(({'walk','view','activity'}|OUTDOOR_KEYS)&set(active))
    if re.search(r'실내',text) or rain or snow:patch['setting']='indoor'
    elif re.search(r'야외|실외|밖에서|바깥',text):patch['setting']='outdoor'
    elif harsh and not outdoor_wish:patch['setting']='indoor'
    elif harsh:warnings.append('더위·추위 표현이 있지만 야외 활동 요청도 있어 실내로 제한하지 않았어요.')
    if re.search(r'실내\s*(?:말고|제외|싫)',text):patch['setting']='outdoor'
    if re.search(r'야외\s*(?:말고|제외|싫)',text):patch['setting']='indoor'
    conditional=re.search(r'비\s*(?:가\s*)?(?:오면|온다면)|눈\s*(?:이\s*)?(?:오면|온다면)|맑으면|날씨\s*(?:가\s*)?좋으면|추우면|더우면|날씨에\s*따라',text)
    if conditional:
        patch.pop('setting',None)
        warnings.append('날씨에 따른 조건부 요청이 있어요. 자동으로 실내·야외를 확정하지 않았으니 방문일에 맞춰 선택해 주세요.')
    # 날씨·계절·분위기는 활동을 말하지 않았을 때만 데이트 분류로 옮긴다(활동이 있으면 활동이 우선).
    if not active and not conditional:
        weather='비 오는 날' if rain else '눈 오는 날' if snow else '맑은 날' if re.search(r'맑은\s*날|화창|날씨\s*(?:가\s*)?좋은|햇살\s*좋은',text) else None
        season=next((name for name,pattern in SEASONS if re.search(pattern,text)),None)
        concept=next(((major,minor) for major,minor,pattern in CONCEPTS if re.search(pattern,text)),None)
        chosen=('날씨별',weather) if weather else ('계절별',season) if season else concept
        if chosen:patch.update(date_category=chosen[0],date_subcategory=chosen[1])
    for pattern,key in [(r'(?<!\d)([1-9]|1\d|20)\s*명','people'),(r'(?<!\d)([2-5])\s*(?:곳|군데)','count')]:
        m=re.search(pattern,text)
        if m:patch[key]=int(m[1])
    if 'people' not in patch:
        for word,value in [('둘이',2),('두 명',2),('셋이',3),('세 명',3),('넷이',4),('네 명',4)]:
            if word in text:patch['people']=value;break
    if 'people' not in patch:
        if re.search(r'커플|연인|여자\s*친구|남자\s*친구|여친|남친|애인|와이프|남편|아내|부부',text):patch['people']=2
        elif re.search(r'(?<![가-힣])혼자|나\s*홀로',text):patch['people']=1
    if re.search(r'첫\s*(?:데이트|만남)|소개팅|처음\s*만나',text):patch['meeting_type']='first'
    elif re.search(r'기념일|(?:\d+|백)\s*일\s*(?:기념|째)|\d+\s*주년|생일|프러?포즈',text):patch['meeting_type']='anniversary'
    avoid=[];avoided=[]
    for pattern,label,words in FOOD_AVOID:
        if any(negated(text,m) or m[0].startswith('맵찔') for m in re.finditer(pattern,text)):avoid+=words;avoided.append(label)
    if avoid:
        patch['avoid']=avoid
        warnings.append(' · '.join(avoided)+' 제외: 이름이나 분류에 관련 단어가 들어간 장소를 뺐어요. 메뉴까지 확인한 것은 아니에요.')
    amounts=[]
    # Start only at the beginning of a digit/comma run: otherwise every position in a
    # long "1,1,1,..." run restarts the scan and the search becomes quadratic.
    for m in re.finditer(r'(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*(?:(만)\s*(?:(\d+)\s*천\s*)?|(천)\s*)?원',text):
        value=Decimal(m[1].replace(',',''))*(10000 if m[2] else 1000 if m[4] else 1)+int(m[3] or 0)*1000
        if value==int(value):amounts.append(int(value))
    if len(amounts)==1 and 0<=amounts[0]<=10000000:patch['budget']=amounts[0]
    elif amounts:warnings.append('금액이 여러 개이거나 지원 예산 범위를 벗어나 자동 적용하지 않았어요. 전체 예산을 직접 확인해 주세요.')
    no_car=re.search(r'(?:차|자차|자가용)\s*(?:가|는|이)?\s*없|운전\s*(?:은\s*)?(?:못|안)',text)
    if re.search(r'대중교통|지하철|전철|버스(?!킹)',text):patch['transport']='transit'
    elif not no_car and re.search(r'자차|자가용|자동차|(?<![가-힣])차\s*(?:로|타고|끌고|가지고|갖고)|드라이브|운전해',text):patch['transport']='car'
    elif re.search(r'따릉이|자전거\s*(?:로|타고\s*이동)',text):patch['transport']='bicycle'
    elif re.search(r'걸어서|도보',text):patch['transport']='walk'
    # '걷는 건 싫어'는 걷는 이동을 줄이고 싶다는 뜻이다. 다른 수단을 말하지 않았을 때만 대중교통으로 바꾼다.
    if any(negated(text,m) for m in re.finditer(r'걷(?:기|고|는)?|걸어\s*다니|도보\s*이동',text)) and patch.get('transport') in (None,'walk'):
        patch['transport']='transit'
        warnings.append('걷는 이동을 줄이고 싶다고 하셔서 이동 수단을 대중교통으로 바꿨어요. 자가용이면 직접 바꿔 주세요.')
    if re.search(r'예약\s*(?:없이|안|없는)',text):patch['reservation']=False
    if re.search(r'사진|인생샷|포토|인스타|예쁜\s*(?:곳|데|사진)',text):patch['priority']='photo'
    elif re.search(r'대화|조용|이야기|수다|차분|한적|붐비지\s*않|사람\s*(?:많은|많이)\s*(?:곳|데)?\s*(?:은|는)?\s*(?:싫|별로|피)',text):patch['priority']='talk'
    elif re.search(r'활동적|액티브|몸\s*(?:쓰는|움직)|땀\s*흘리|신나게',text):patch['priority']='activity'
    elif re.search(r'먹는\s*게\s*(?:제일|가장)?\s*중요|미식|먹방|맛\s*위주',text):patch['priority']='food'
    budget_style=None
    if re.search(r'저렴|싸게|(?<![가-힣])싼\s*(?:곳|데|코스)|가성비|알뜰|돈\s*(?:이\s*)?(?:안|적게|별로\s*안)\s*(?:드는|들|쓰는)|무료|짠돌|짠순',text):
        budget_style='low'
        warnings.append('저렴한 코스를 원하셔서 같은 조건이면 비용이 적은 조합을 먼저 비교해요. 예산 금액은 폼에서 직접 정해 주세요.')
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
                unit_budget=unit_budget,warnings=warnings,budget_style=budget_style)


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
    # The chosen region and coordinates are explicit form inputs.
    patch.pop('region',None)
    # Explicit free text takes precedence over the generic quick-start concept.
    if parsed['intents']:
        patch.update(date_category='',date_subcategory='')
    # 사용자가 직접 고른 테마가 있으면 글의 날씨·계절 분류로 후보를 한 번 더 좁히지 않는다.
    elif c.themes or {'themes','date_category','date_subcategory'}&set(c.explicit_fields):
        patch.pop('date_category',None);patch.pop('date_subcategory',None)
    for key in c.explicit_fields:
        patch.pop(key,None)
    # 예산 무관을 고르면 글의 금액으로 예산을 바꾸지 않는다(어차피 쓰지 않는 값이다).
    if c.budget_unlimited:patch.pop('budget',None)
    # 대분류와 소분류는 함께 바뀌어야 한다. 하나만 직접 고른 경우 글의 분류를 적용하지 않는다.
    if ('date_category' in patch)!=('date_subcategory' in patch):
        patch.pop('date_category',None);patch.pop('date_subcategory',None)
    # 글에서 찾은 제외 단어는 사용자가 적은 '피할 활동'에 더한다(덮어쓰지 않는다).
    if 'avoid' in patch:patch['avoid']=list(dict.fromkeys([*c.avoid,*patch['avoid']]))[:30]
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
    if key in SPORT_BY_KEY:return bool(SPORT_BY_KEY[key].place_re.search(text))
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
