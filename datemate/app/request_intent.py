"""Shared, transparent interpretation of both search text and free-form requests.

해석 결과(interpret)는 기존 결과(intents·excluded·patch·warnings …)와 함께 두 목록을 낸다.
- items: 이해한 조건. 항목마다 id('조건 종류:값'), field, value, label(화면 이름), evidence(근거가 된 원문 조각),
  source('rule'), estimated(장소 자료로 직접 확인할 수 없어 장소 유형으로 근사한 조건), note(근사 방법).
- unparsed: 반영하지 못한 원문 조각. reason 은 'unknown'(규칙이 모르는 표현), 'conflict'(다른 조건과 함께 고를 수 없음),
  'conditional'(날씨에 따른 조건부 요청), 'amount'(금액이 여러 개). message 는 화면에 그대로 쓰는 문장이다.
기존 결과는 items 에서 다시 만든다(_assemble). 사용자가 화면에서 뺀 항목(ignore)은 그 항목만 빼고 같은 규칙으로 다시 만들고,
뺀 항목은 ignored 로 돌려준다. 나중에 다른 출처(source='ai') 항목을 더할 때도 같은 구조와 _assemble 을 쓴다.
"""
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
 'cafe':['브런치','찻집','빵집','로스터리','티룸','카패'],
 'meal':['먹으러','먹고 싶','맛있는 거','맛있는 곳','오마카세','파인다이닝','파인 다이닝','고깃집','미식',
         '식당','외식','저녁 먹','점심 먹','저녁식사','점심식사','저녁 식사','점심 식사','먹방'],
 'culture':['전시회','미술','아트센터','미디어아트','문화생활'],
 'cinema':['무비','상영관'],
 'performance':['연주회','오페라','발레','국악','버스킹','공연장'],
 'museum':['과학관','기념관','유적','고궁','궁궐'],
 'book':['독서','북스테이','책 읽','책 보'],
 'workshop':['원데이클래스','원데이 클래스','클래스','체험','쿠킹','베이킹','캔들','가죽 공예','목공','꽃꽂이','플라워','드로잉','그림 그리'],
 'walk':['걷기','걷고','걷는','걸으며','둘레길','강변','호숫가','호수','해변','바닷가','바다','수목원','식물원','꽃구경','꽃놀이','벚꽃','단풍','나들이'],
 'game':['코인노래방','노래방','피시방','PC방','VR','보드겜','방탈'],
 'activity':['액티비티'],
 'view':['경치','풍경','오션뷰','루프탑','전망대','해돋이','일출','석양','뷰 좋은','뷰가 좋은'],
 'shopping':['아울렛','백화점','쇼핑몰','플리마켓','시장 구경','팝업스토어','팝업 스토어'],
 'rest':['쉬고 싶','쉬러','쉬엄쉬엄','마사지','템플스테이','호캉스','쉬자'],
}
# 낱말 경계가 필요한 요청 표현(정규식). '볶음밥'·'밥값'의 밥은 식사 요청이 아니다.
REQUEST_PATTERNS={'meal':[r'(?<![가-힣])밥(?![가-힣])|(?<![가-힣])밥(?=이랑|랑|도|은|을|먹|하고)']}
# 단어 바로 뒤의 부정 표현. '카페 말고 전시'에서 전시까지 부정하지 않도록 짧은 꼬리만 본다.
# 꼬리: '술 마시는 데는 말고'·'전시 같은 데는 별로'처럼 짧은 수식어·의존 명사와 '무서워서 싫어' 같은 이유 한 낱말까지.
NEG_CORE=(r'말고|말구|빼|제외|싫|별로|별루|좋아하지|않|'
    r'안\s*(?:좋아|원해|가|갈|먹|마[시셔]|땡|끌|해)|못\s*(?:가|먹|마[시셔]|걷|해)|피하|피해|없이|없[는이]|패스|지겨|질려|질렸|힘들|'
    r'관심\s*없|알레르기|알러지|[가-힣]{1,2}기\s*싫|(?:[가-힣]{1,2}고\s*)?싶지\s*않|원하지\s*않|극혐|노노|ㄴㄴ|사절|부담스|질색|무리')
NEG_TAIL=(r'(?:\s*(?:음식|요리))?(?:\s*(?:마시는|먹는|하는|보는|가는|파는|나오는|타는|치는))?(?:\s*(?:같은|이런|그런))?'
    r'(?:\s*(?:곳|데|덴|장소|거|건|것|집|쪽|종류))?')
# 이유 한마디('무서워서', '너무 더워서', '저번에 봤으니까')와 부사('잘 못 먹어', '진짜 싫어')는 건너뛴다.
NEG_REASON=r'(?:\s*(?:너무|좀|진짜|정말|넘|많이|[가-힣]{1,4}에))?(?:\s*[가-힣]{1,4}(?:서|니까))?'
NEG_ADVERB=r'(?:\s*(?:잘|너무|좀|진짜|정말|넘|딱히|그다지|많이))?'
NEGATIVE=re.compile(NEG_TAIL+r'\s*(?:는|은|을|를|도|에|건|거는|거|게|것은|것도|쪽은)?'+NEG_REASON+NEG_ADVERB+r'\s*(?:'+NEG_CORE+')')
# '매운 음식이랑 술은 빼줘'처럼 '…랑/과 …'로 이어 함께 부정하는 경우.
CONJ_NEGATIVE=re.compile(r'(?:\s*(?:음식|거|것))?(?:이랑|랑|과|와)\s*[가-힣]{1,8}?'+NEGATIVE.pattern)
# '안 매운', '못 걷고' 처럼 단어 앞에서 부정하는 경우.
NEGATED_BEFORE=re.compile(r'(?:^|[^가-힣])(?:안|못)\s*$')
# 음식 제외는 장소 유형이 아니라 이름·분류 단어로 거른다(메뉴까지 확인하지는 않는다).
# 네 번째 값: 부정 표현 없이도 제외로 보는 말('맵찔이', '순한 맛', '노알콜').
FOOD_AVOID=[
 (r'매운|매콤|얼큰|맵(?:지|고|게|기|찔|다)|마라|불닭|순한\s*(?:맛|거|걸|음식|메뉴)','매운 음식',['매운','마라','불닭','짬뽕','떡볶이','닭발','쭈꾸미','낙지'],r'맵찔|순한'),
 (r'(?<![가-힣])술(?:집)?|음주|알코올|알콜|(?:노|논|무)\s*알(?:콜|코올)','술',['술집','주점','포차','호프','이자카야','와인바','칵테일바'],r'[노논무]\s*알'),
 (r'해산물|해물|생선|조개|갑각류|날것|(?<![가-힣])회(?=\s|는|를|도|랑|$)','해산물',['해산물','해물','횟집','수산','조개','생선'],None),
]
RAIN=r'(?<![가-힣])비\s*(?:가\s*)?(?:많이\s*|좀\s*|계속\s*)?(?:오는|와|온|올|내리)|(?<![가-힣])비올|우천|장마|소나기'
SNOW=r'눈\s*(?:오는|와서|이\s*오|내리|올)|폭설|함박눈'
# '영하'는 '수영하고'처럼 낱말 안에 섞이므로 앞에 한글이 붙으면 보지 않는다.
HARSH=r'폭염|무더위|더운\s*(?:날|데|때)|더워|한파|추운\s*(?:날|데|때)|추워|(?<![가-힣])영하|미세\s*먼지|황사'
# 날씨와 상관없이 다닐 수 있는 곳 = 실내. '실내'라는 말은 부정('실내는 싫어')을 따로 본다.
INDOOR=(r'우산\s*(?:없이|안\s*(?:쓰|챙기)|필요\s*없)|날씨\s*(?:랑|와|에)?\s*(?:상관\s*없|관계\s*없|영향\s*(?:없|안|을\s*안)|걱정\s*없|안\s*타)'
    r'|비\s*(?:를\s*)?(?:안\s*맞|맞지\s*않)|(?<![가-힣])안에서')
OUTDOOR_WORDS=r'야외|실외|밖에서|바깥'
OUTDOOR=r'바람\s*(?:쐬|쐴)|탁\s*트인|햇(?:빛|볕|살)\s*(?:받|쬐)|하늘\s*보'
CONDITIONAL=(r'비\s*(?:가\s*)?(?:오면|온다면)|눈\s*(?:이\s*)?(?:오면|온다면)|맑으면|날씨\s*(?:가\s*)?좋으면|(?<![가-힣])날\s*(?:이\s*)?좋으면'
    r'|추우면|더우면|날씨에\s*따라')
CLEAR=r'맑은\s*날|화창|날씨\s*(?:가\s*)?좋은|햇살\s*좋은'
SEASONS=[('봄',r'(?<![가-힣])봄(?![가-힣])|(?<![가-힣])봄(?:날|철|꽃|나들이|에|엔)'),('여름',r'(?<![가-힣])여름|바캉스|피서'),
    ('가을',r'(?<![가-힣])가을'),('겨울',r'(?<![가-힣])겨울|크리스마스|연말')]
CONCEPTS=[('콘셉트별','즐거운 데이트',r'즐거운|신나는|재밌는|재미있는'),('콘셉트별','편안한 데이트',r'편안한|편하게|여유로운|여유롭|느긋|한적'),
    ('콘셉트별','지적인 데이트',r'지적인|배우는|교양'),('콘셉트별','동심 데이트',r'동심|어릴\s*적|키덜트|레트로\s*게임'),
    ('타입별','활동적인',r'활동적|액티브|몸\s*(?:쓰는|움직)|땀\s*흘리'),('타입별','사교적인',r'사교적|여럿이|사람들과\s*어울')]
# 걷는 양을 줄이고 싶다는 말. '걷기 적게'의 '걷기'는 산책 요청이 아니다.
WALK_LESS=re.compile(r'(?:많이|오래|멀리|너무)\s*(?:안|못)\s*(?:걷|걸)|걷(?:기|는\s*(?:거|것|건|게))?\s*(?:를|은|는|도)?\s*(?:적게|조금|최소|덜|짧게)'
    r'|(?:조금만|적게|덜|최소한으로|최소로|짧게)\s*(?:걷|걸)|다리\s*(?:가\s*)?아[프파]|(?<![가-힣])발\s*(?:이\s*)?아[프파]|(?<![가-힣])힐\s*(?:을\s*)?신|구두\s*(?:를\s*)?신'
    r'|체력이?\s*(?:약|없|안\s*좋)|오래\s*(?:못|안)\s*걸|걷지\s*(?:않|말)')
WALK_NEGATABLE=re.compile(r'걷(?:기|고|는)?|걸어\s*다니|도보\s*이동')
# 가장 중요한 것(priority)은 하나만 고른다. 사진 > 대화·조용함 > 활동 > 음식 순서(기존 규칙).
PHOTO=re.compile(r'사진\s*(?:이\s*)?잘\s*나오|사진\s*(?:을\s*)?(?:남기|찍(?:는|기|을)?)|사진발|사진|인생\s*샷(?:\s*(?:건질|건지|찍을|남길))?|인증\s*샷|포토'
    r'|인스타(?:에)?(?:\s*(?:올릴|업로드))?|(?:예쁜|이쁜)\s*(?:곳|데|사진|카페|장소)|찍기\s*좋은')
QUIET=re.compile(r'(?:조용|한산|차분|한적|호젓|고즈넉|아늑)(?:한|히|하고|하게|해서)?|사람\s*(?:이\s*)?(?:적|없|별로\s*없|많지\s*않|덜)|인파\s*(?:가\s*)?(?:적|없)'
    r'|(?:붐비|북적(?:이|거리)?|복잡하|시끄럽|번잡하)지\s*않|안\s*(?:붐비|북적|시끄러|복잡)|덜\s*(?:붐비|북적|시끄)'
    r'|대화|이야기|얘기|수다(?:\s*떨)?|오래\s*앉아(?:\s*있)?|앉아서\s*(?:쉬|얘기|이야기|수다)|편하게\s*앉')
# 부정하면 '조용한 곳'이 되는 말: '시끄러운 데는 싫어', '사람 많은 곳 말고', '핫플 말고'.
NOISY=re.compile(r'시끄러운|시끄럽|북적(?:북적)?(?:이는|거리는|대는|한|는)?|붐비는|붐비|사람\s*(?:이\s*)?많은|사람\s*(?:이\s*)?많이|인파|핫플|번잡한|복잡한')
ACTIVE_PRIORITY=r'활동적|액티브|몸\s*(?:쓰는|움직)|땀\s*(?:좀\s*)?흘[리려]|신나게'
FOOD_PRIORITY=r'먹는\s*게\s*(?:제일|가장)?\s*중요|미식|먹방|맛\s*위주'
CHEAP=(r'저렴|싸게|(?<![가-힣])싼\s*(?:곳|데|코스)|가성비|알뜰|돈\s*(?:이\s*)?(?:안|적게|별로\s*안)\s*(?:드는|들|쓰는)|무료|짠돌|짠순'
    r'|저예산|착한\s*가격|돈\s*(?:이\s*)?(?:별로\s*)?없|지갑이?\s*(?:얇|가벼)|아껴|비싸지\s*않|안\s*비싼')

PRIORITY_LABELS={'talk':'조용한 곳·대화 우선','photo':'사진 잘 나오는 곳 우선','activity':'몸 쓰는 활동 우선','food':'음식 우선'}
PRIORITY_NOTES={
 'talk':'장소의 소음·인파 자료가 없어, 카페·휴식 유형을 먼저 고르는 방식으로 근사해요. 실제로 조용한지는 확인하지 못해요.',
 'photo':'촬영 명소 자료가 없어, 산책·풍경·문화 유형을 먼저 고르는 방식으로 근사해요.',
 'activity':'공방·레저·놀이 유형을 먼저 골라요.',
 'food':'식당·미식 유형을 먼저 골라요.',
}
TRANSPORT_LABELS={'walk':'도보로 이동','transit':'대중교통으로 이동','car':'자가용으로 이동','bicycle':'자전거로 이동'}
WALK_WARNING='걷는 이동을 줄이고 싶다고 하셔서 이동 수단을 대중교통으로 바꿨어요. 자가용이면 직접 바꿔 주세요.'
LOW_WARNING='저렴한 코스를 원하셔서 같은 조건이면 비용이 적은 조합을 먼저 비교해요. 예산 금액은 폼에서 직접 정해 주세요.'
AMOUNT_WARNING='금액이 여러 개이거나 지원 예산 범위를 벗어나 자동 적용하지 않았어요. 전체 예산을 직접 확인해 주세요.'
CONDITIONAL_WARNING='날씨에 따른 조건부 요청이 있어요. 자동으로 실내·야외를 확정하지 않았으니 방문일에 맞춰 선택해 주세요.'
HARSH_WARNING='더위·추위 표현이 있지만 야외 활동 요청도 있어 실내로 제한하지 않았어요.'

# 반영하지 못한 조각을 고를 때 건너뛰는 말(조사를 뗀 뒤 비교). 요청 내용이 아니라 문장을 잇는 말이다.
EDGE_WORDS=set('''데이트 코스 일정 곳 데 대 장소 추천 추천해 추천해줘 추천해줘요 추천해주세요 추천좀 부탁 부탁해 부탁해요 부탁드려요 짜줘 짜줘요 짜주세요
 알려줘 알려주세요 찾아줘 찾아주세요 해줘 해주세요 가자 가쟈 가요 갈래 갈까 가고싶어 가고싶다 가고싶어요 보러갈래 싶어 싶어요 싶다 싶음 싶네
 좋겠어 좋겠다 좋겠어요 좋을까 괜찮아 괜찮아요 상관없어 어디 어디가 어디든 뭐 뭘 좀 너무 넘 진짜 완전 그냥 아무 아무데나 데나 ㄱ ㄱㄱ ㄱㄱㄱ 고고
 ㅎㅎ ㅋㅋ ㅠㅠ 하루 오늘 요즘 위주 위주로 이내 정도 쯤 ok OK 오케이 플리즈 굿 거야 거예요 건데 없나 있나 할까 하자 놀자 다니자'''.split())
FILLER_WORDS=EDGE_WORDS|set('''같이 함께 우리 저희 나 저 한번 다 또 해 해요 하고 하구 하는 할 한 하면 하기 해서 가 가고 가서 갈 가는 갈만한 보고 보러 보구 볼 보자
 놀 놀고 놀러 다닐 다니고 돌고 싶은 좋은 좋아 좋게 좋을 괜찮은 괜찮게 괜찮을 상관없는 수 있는 있을 있으면 있어 있어요 만한 만큼 날 이런 그런 어떤 어때
 어떨까 중심 후 다음 그리고 근데 또는 아니면 이거 그거 되는 될 돼 됨 되면 가능 가능한 및 등 많은 심한 다른 밖 특별한 특별하게 보내고 치고 들렀다가 먹자
 먹고 먹을 갈게 갈래요 할게 가져갈게 타고 데려가 데려가줘 나누고 많이 오래 멀리 길 예산 거 것 건 게 걸 괜찮은데 좋은데 하고싶어 싶은데
 안 사람 안쪽 이하 미만 이상 결혼 겸'''.split())
# 서비스가 아직 조건으로 다루지 않는 말(거리·시간대·동반·편의시설). 한 낱말만 남아도 '반영하지 못함'으로 알린다.
UNSUPPORTED=re.compile(r'가까[운이워]|멀지|(?<![가-힣])먼|늦게|늦은|일찍|주차|반려|강아지|애견|아기|유모차|휠체어|웨이팅|줄\s*서|택시|주말|평일'
    r'|저녁|점심|아침|오전|오후|(?<![가-힣])밤|새벽|\d+\s*시')
# 조사를 뗀 뒤에도 서술어 끝처럼 보이는 한 낱말(받는·치러·온대·가볍게)은 문장을 잇는 말일 때가 많아 혼자서는 알리지 않는다.
PREDICATE_END=re.compile(r'(?:는|은|운|한|게|고|서|면|어|아|해|자|러|대|데|요|지|며|던|까)$')
JOSA=re.compile(r'(?:이랑|랑|에서|으로|로|은|는|이|가|을|를|에|도|만|과|와|의|이라서|라서|이라|라|인데|이면|면|요|까지|부터|처럼|보다|이니까|니까)$')
TOKEN=re.compile(r'[^\s,.!?~·/()+&]+')
BOUNDARY=re.compile(r'[,.!?~·/\n+&]')
# '분위기' 한 낱말만 남은 조각은 이미 이해한 분위기 말(조용한 분위기)을 꾸미는 말이라 알리지 않는다.
MOOD_ONLY=re.compile(r'분위기|느낌|감성')


def _negation_end(text,start,end):
    """부정 표현이 있으면 그 끝 위치, 없으면 None."""
    m=NEGATIVE.match(text,end,min(len(text),end+40)) or CONJ_NEGATIVE.match(text,end,min(len(text),end+50))
    if m:return m.end()
    if NEGATED_BEFORE.search(text[max(0,start-6):start]):return end
    return None


def negated(text,m):
    return _negation_end(text,m.start(),m.end()) is not None


def request_words(key):return INTENTS[key][1]+REQUEST_WORDS.get(key,[])


def intent_label(key):return INTENTS[key][1][0]


def _intent_matches(key,text):
    if key in SPORT_BY_KEY:yield from SPORT_BY_KEY[key].request_re.finditer(text);return
    for word in sorted(request_words(key),key=len,reverse=True):
        for m in re.finditer(re.escape(word),text,re.I):
            # '놀이공원·테마공원'은 산책할 공원이 아니다.
            if word=='공원' and re.search(r'(?:놀이|테마)\s*$',text[max(0,m.start()-3):m.start()]):continue
            yield m
    for pattern in REQUEST_PATTERNS.get(key,[]):yield from re.finditer(pattern,text)


def _intent_spans(key,text):return [(m.start(),m.end()) for m in _intent_matches(key,text)]


def _josa(word,batchim,plain):
    last=next((ch for ch in reversed(word) if '가'<=ch<='힣' or ch.isdigit()),'')
    if not last:return plain
    if last.isdigit():return batchim if last in '013678' else plain
    return batchim if (ord(last)-0xAC00)%28 else plain


def _stem(token):
    stripped=JOSA.sub('',JOSA.sub('',token))
    return stripped or token


class _Reader:
    def __init__(self,text):
        self.text=text;self.spans=[];self.items=[];self.notes=[];self.held=[]

    def cover(self,start,end):
        if end>start:self.spans.append((start,end))

    def fragment(self,start,end):
        t=self.text
        while start>0 and not t[start-1].isspace():start-=1
        while end<len(t) and not t[end].isspace():end+=1
        return t[start:end].strip(' ,.!?~·')

    def add(self,id,field,value,label,spans,estimated=False,note='',**extra):
        spans=[s for s in spans if s and s[1]>s[0]]
        for s,e in spans:self.cover(s,e)
        evidence=list(dict.fromkeys(self.fragment(s,e) for s,e in spans))
        for item in self.items:
            if item['id']==id:
                item['evidence']=list(dict.fromkeys(item['evidence']+evidence));return item
        item=dict(id=id,field=field,value=value,label=label,evidence=evidence,source='rule',estimated=estimated,note=note,
                  **{'_'+k:v for k,v in extra.items()})
        self.items.append(item);return item

    def hold(self,start,end,reason,message):
        """알아들었지만 적용하지 않은 조각(조건부 날씨·우선순위 충돌·금액 여러 개)."""
        self.cover(start,end)
        text=self.fragment(start,end)
        if not any(h['text']==text and h['reason']==reason for h in self.held):
            self.held.append(dict(text=text,reason=reason,message=message.format(text=text,eun=_josa(text,'은','는'))))

    def first(self,field):return next((i for i in self.items if i['field']==field),None)


def _span(m):return (m.start(),m.end())


def _unknown(text,spans):
    """규칙이 쓰지 않은 원문 조각. 문장 부호에서 끊고, 잇는 말만 남은 조각은 버린다."""
    tokens=list(TOKEN.finditer(text));out=[];group=[]
    def flush():
        if not group:return
        stems=[_stem(t[0]) for t in group]
        content=[i for i,s in enumerate(stems) if s not in FILLER_WORDS and group[i][0] not in FILLER_WORDS]
        if content:
            words=[t[0] for t in group]
            if all(MOOD_ONLY.fullmatch(stems[i]) for i in content) and not any(w in ('좋은','좋게','있는','있게','있고') for w in words):
                group.clear();return
            only=content[0]
            if len(content)==1 and (PREDICATE_END.search(stems[only]) or PREDICATE_END.search(words[only])) and not UNSUPPORTED.search(words[only]):
                group.clear();return
            last=len(group)-1
            while last>content[-1] and (stems[last] in EDGE_WORDS or words[last] in EDGE_WORDS):last-=1
            piece=text[group[content[0]].start():group[last].end()]
            out.append(dict(text=piece,reason='unknown',message=f'‘{piece}’{_josa(piece,"은","는")} 아직 반영하지 못했어요.'))
        group.clear()
    for index,t in enumerate(tokens):
        covered=any(t.start()<e and s<t.end() for s,e in spans)
        if index and BOUNDARY.search(text[tokens[index-1].end():t.start()]):flush()
        if covered:flush();continue
        group.append(t)
    flush()
    return out


@lru_cache(maxsize=512)
def _extract(text):
    r=_Reader(text)
    inside=lambda m,spans:any(m.start()<e and s<m.end() for s,e in spans)
    # 걷는 양 줄이기는 산책 낱말보다 먼저 본다.
    walk_less=[_span(m) for m in WALK_LESS.finditer(text)]
    for m in WALK_NEGATABLE.finditer(text):
        end=_negation_end(text,m.start(),m.end())
        if end is not None:walk_less.append((m.start(),end))
    active=[]
    for key in INTENTS:
        positive=[];negative=[]
        for m in _intent_matches(key,text):
            if key=='walk' and inside(m,walk_less):negative.append(_span(m));continue
            end=_negation_end(text,m.start(),m.end())
            if end is None:positive.append(_span(m))
            else:negative.append((m.start(),end))
        if key=='walk' and walk_less:negative+=walk_less
        if negative:r.add('exclude:'+key,'exclude',key,intent_label(key)+' 빼기',negative+positive)
        elif positive:r.add('activity:'+key,'activity',key,intent_label(key),positive);active.append(key)
    from .regions import REGIONS
    for region,names in REGIONS.items():
        found=next((m for name in sorted(names,key=len,reverse=True)
                    for m in re.finditer(r'(?<![가-힣])'+re.escape(name)+r'(?=\s|에서|으로|로|에|의|$)',text)),None)
        if found:r.add('region:'+region,'region',region,'지역: '+region,[_span(found)]);break
    rain,snow,harsh=(re.search(p,text) for p in (RAIN,SNOW,HARSH))
    outdoor_wish=bool(({'walk','view','activity'}|OUTDOOR_KEYS)&set(active))
    indoor_yes=[];indoor_no=[];outdoor_yes=[];outdoor_no=[]
    for m in re.finditer('실내',text):
        end=_negation_end(text,m.start(),m.end())
        (indoor_yes if end is None else indoor_no).append((m.start(),end or m.end()))
    indoor_yes+=[_span(m) for m in re.finditer(INDOOR,text)]
    for m in re.finditer(OUTDOOR_WORDS,text):
        end=_negation_end(text,m.start(),m.end())
        (outdoor_yes if end is None else outdoor_no).append((m.start(),end or m.end()))
    outdoor_yes+=[_span(m) for m in re.finditer(OUTDOOR,text)]
    weather=[_span(m) for m in (rain,snow) if m]
    setting=None;because=[]
    if indoor_yes or weather:setting,because='indoor',indoor_yes+weather
    elif outdoor_yes:setting,because='outdoor',outdoor_yes
    elif harsh and not outdoor_wish:setting,because='indoor',[_span(harsh)]
    elif harsh:r.notes.append(HARSH_WARNING)
    if harsh:r.cover(*_span(harsh))
    if indoor_no:setting,because='outdoor',indoor_no+outdoor_yes
    if outdoor_no:setting,because='indoor',outdoor_no+indoor_yes
    conditional=list(re.finditer(CONDITIONAL,text))
    if conditional:
        setting=None
        r.notes.append(CONDITIONAL_WARNING)
        for m in conditional:r.hold(m.start(),m.end(),'conditional','‘{text}’처럼 날씨에 따라 바뀌는 요청은 실내·야외를 자동으로 정하지 않았어요. 방문일에 맞춰 골라 주세요.')
        for s,e in indoor_yes+outdoor_yes+weather:r.cover(s,e)
    if setting:r.add('setting:'+setting,'setting',setting,'실내만' if setting=='indoor' else '실외만',because)
    # 날씨·계절·분위기는 활동을 말하지 않았을 때만 데이트 분류로 옮긴다(활동이 있으면 활동이 우선).
    clear=re.search(CLEAR,text)
    season=next(((name,m) for name,pattern in SEASONS for m in [re.search(pattern,text)] if m),None)
    concept=next(((major,minor,m) for major,minor,pattern in CONCEPTS for m in [re.search(pattern,text)] if m),None)
    if not active and not conditional:
        if rain:r.add('date:비 오는 날','date','비 오는 날','데이트 분류: 비 오는 날',[_span(rain)],category='날씨별')
        elif snow:r.add('date:눈 오는 날','date','눈 오는 날','데이트 분류: 눈 오는 날',[_span(snow)],category='날씨별')
        elif clear:r.add('date:맑은 날','date','맑은 날','데이트 분류: 맑은 날',[_span(clear)],category='날씨별')
        elif season:r.add('date:'+season[0],'date',season[0],'데이트 분류: '+season[0],[_span(season[1])],category='계절별')
        elif concept:
            r.add('date:'+concept[1],'date',concept[1],'데이트 분류: '+concept[1],[_span(concept[2])],estimated=True,
                  note='분위기는 장소 자료로 확인할 수 없어, 이 분류에 맞는 장소 유형을 먼저 고르는 방식으로 근사해요.',category=concept[0])
    else:
        for m in [clear,season and season[1],concept and concept[2]]:
            if not m:continue
            if active:r.hold(m.start(),m.end(),'conflict','‘{text}’{eun} 말씀하신 활동을 먼저 반영해서 데이트 분류로는 쓰지 않았어요.')
            else:r.cover(*_span(m))
    for pattern,key in [(r'(?<!\d)([1-9]|1\d|20)\s*명','people'),(r'(?<!\d)([2-5])\s*(?:곳|군데)','count')]:
        m=re.search(pattern,text)
        if m:r.add(f'{key}:{int(m[1])}',key,int(m[1]),f'{int(m[1])}명' if key=='people' else f'{int(m[1])}곳',[_span(m)])
    m=None if r.first('count') else re.search(r'(?<![가-힣])(두|세|네|다섯)\s*(?:곳|군데)',text)
    if m:
        value={'두':2,'세':3,'네':4,'다섯':5}[m[1]];r.add(f'count:{value}','count',value,f'{value}곳',[_span(m)])
    if not r.first('people'):
        for word,value in [('둘이',2),('두 명',2),('우리 둘',2),('두 사람',2),('셋이',3),('세 명',3),('세 사람',3),('넷이',4),('네 명',4),('네 사람',4)]:
            i=text.find(word)
            if i>=0:r.add(f'people:{value}','people',value,f'{value}명',[(i,i+len(word))]);break
    if not r.first('people'):
        m=re.search(r'커플|연인|여자\s*친구|남자\s*친구|여친|남친|애인|와이프|남편|아내|부부',text)
        if m:r.add('people:2','people',2,'2명',[_span(m)])
        else:
            m=re.search(r'(?<![가-힣])혼자|나\s*홀로',text)
            if m:r.add('people:1','people',1,'1명',[_span(m)])
    first=[_span(m) for m in re.finditer(r'첫\s*(?:데이트|만남)|소개팅|처음\s*만나|맞선|처음\s*보는',text)]
    anniversary=[_span(m) for m in re.finditer(r'기념일|(?:\d+|백|천)\s*일\s*(?:기념|째|이라|이니까|이야|인데)|\d+\s*주년|생일|프[러로]?포즈|기념(?!관|품)|특별한\s*날',text)]
    if first:r.add('meeting_type:first','meeting_type','first','첫 만남',first)
    elif anniversary:r.add('meeting_type:anniversary','meeting_type','anniversary','기념일',anniversary)
    for pattern,label,words,plain in FOOD_AVOID:
        hits=[]
        for m in re.finditer(pattern,text):
            end=_negation_end(text,m.start(),m.end())
            if end is not None:hits.append((m.start(),end))
            elif plain and re.match(plain,m[0]):hits.append(_span(m))
        if hits:r.add('avoid:'+label,'avoid',label,label+' 빼기',hits,estimated=True,
                      note='이름이나 분류에 관련 단어가 들어간 장소를 빼요. 메뉴까지 확인한 것은 아니에요.',words=words)
    amounts=[]
    # Start only at the beginning of a digit/comma run: otherwise every position in a
    # long "1,1,1,..." run restarts the scan and the search becomes quadratic.
    for m in re.finditer(r'(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*(?:(만)\s*(?:(\d+)\s*천\s*)?|(천)\s*)?원',text):
        value=Decimal(m[1].replace(',',''))*(10000 if m[2] else 1000 if m[4] else 1)+int(m[3] or 0)*1000
        if value==int(value):amounts.append((int(value),m))
    per_person=re.search(r'(?<!\d)(?:1\s*인(?:당)?|한\s*(?:사람|명)당|인당|각자|각각)\s*(?:예산(?:은|이)?\s*)?(?:[은는]\s*)?\d|원\s*/\s*인',text)
    if len(amounts)==1 and 0<=amounts[0][0]<=10000000:
        value,m=amounts[0]
        spans=[_span(m)]+([(per_person.start(),per_person.end()-1)] if per_person else [])
        label=('1인 ' if per_person else '예산 ')+(f'{value//10000:,}만 원' if value>=10000 and value%10000==0 else f'{value:,}원')
        r.add(f'budget:{value}','budget',value,label,spans,per_person=bool(per_person))
    elif amounts:
        r.notes.append(AMOUNT_WARNING)
        for _,m in amounts:r.hold(m.start(),m.end(),'amount','‘{text}’처럼 금액이 여러 개라 예산을 자동으로 정하지 않았어요. 전체 예산을 직접 골라 주세요.')
    no_car=re.search(r'(?:차|자차|자가용)\s*(?:가|는|이)?\s*없|운전\s*(?:은\s*)?(?:못|안)',text)
    transport=None
    for mode,pattern in [('transit',r'대중교통|지하철|전철|버스(?!킹)'),
                         ('car',None if no_car else r'자차|자가용|자동차|(?<![가-힣\d])차\s*(?:로|타고|끌고|가지고|갖고|가져)|드라이브|운전해'),
                         ('bicycle',r'따릉이|자전거\s*(?:로|타고\s*이동)'),('walk',r'걸어서|도보')]:
        found=[_span(m) for m in re.finditer(pattern,text)] if pattern else []
        if found:transport=(mode,found);break
    if no_car:r.cover(*_span(no_car))
    # '걷는 건 싫어'는 걷는 이동을 줄이고 싶다는 뜻이다. 다른 수단을 말하지 않았을 때만 대중교통으로 바꾼다.
    if walk_less and (transport is None or transport[0]=='walk'):
        r.add('transport:transit','transport','transit','걷기 적게 · 대중교통',walk_less+(transport[1] if transport else []),walk_less=True)
    elif transport:r.add('transport:'+transport[0],'transport',transport[0],TRANSPORT_LABELS[transport[0]],transport[1])
    m=re.search(r'예약\s*(?:없이|안\s*(?:하고|해도)|없는|(?:이\s*)?필요\s*없)',text) or re.search(r'예약\s*안',text)
    if m:r.add('reservation:off','reservation',False,'예약 없이 갈 수 있는 곳',[_span(m)])
    choices=[]
    photo=[]
    for m in PHOTO.finditer(text):
        end=_negation_end(text,m.start(),m.end())
        if end is None:photo.append(_span(m))
        else:
            clause=BOUNDARY.search(text,end);r.cover(m.start(),clause.start() if clause else len(text))
    if photo:choices.append(('photo',photo))
    quiet=[]
    for m in QUIET.finditer(text):
        if _negation_end(text,m.start(),m.end()) is None:quiet.append(_span(m))
    for m in NOISY.finditer(text):
        end=_negation_end(text,m.start(),m.end())
        if end is not None:quiet.append((m.start(),end))
    if quiet:choices.append(('talk',quiet))
    for key,pattern in [('activity',ACTIVE_PRIORITY),('food',FOOD_PRIORITY)]:
        found=[_span(m) for m in re.finditer(pattern,text)]
        if found:choices.append((key,found))
    if choices:
        key,spans=choices[0]
        r.add('priority:'+key,'priority',key,PRIORITY_LABELS[key],spans,estimated=key in ('talk','photo'),note=PRIORITY_NOTES[key])
        for other,spans in choices[1:]:
            for s,e in spans:r.hold(s,e,'conflict','‘{text}’'+'{eun}'+f' ‘{PRIORITY_LABELS[key]}’과 함께 고를 수 없어 반영하지 못했어요. 가장 중요한 것은 하나만 정해요.')
    cheap=[_span(m) for m in re.finditer(CHEAP,text)]
    for m in re.finditer(r'비싼',text):
        end=_negation_end(text,m.start(),m.end())
        if end is not None:cheap.append((m.start(),end))
    if cheap:r.add('budget_style:low','budget_style','low','저렴한 코스 먼저',cheap)
    m=re.search(r'(?:총\s*)?(?:도보|걷기)\s*(\d+)\s*분\s*(?:이내|이하)(?:로)?(?:만)?',text)
    if m and int(m[1])<=600:r.add(f'max_walk:{int(m[1])}','max_walk',int(m[1]),f'총 도보 {int(m[1])}분 이내',[_span(m)])
    # '투어·위주·만'은 활동 낱말 바로 뒤에 붙을 때만 한 종류 집중이다('실내 위주로 카페'·'고기 위주로 먹고'의 '위주'는 활동이 아니다).
    if len(active)==1:
        evidence=[span for item in r.items if item['id']=='activity:'+active[0] for span in _intent_spans(active[0],text)]
        focus=[m for m in re.finditer(r'투어|위주|만\s*(?:가|갈|돌|보고|보고싶|추천|원해)|만$',text)
               if any(s<=m.start() and m.start()-e<=3 for s,e in evidence)]
        if focus:r.add('theme_mode:focus','theme_mode','focus',intent_label(active[0])+'만 (한 종류 집중)',[_span(focus[0])])
    unparsed=r.held+_unknown(text,r.spans)
    return dict(items=r.items,notes=r.notes,unparsed=unparsed)


def _public(item):return {k:v for k,v in item.items() if not k.startswith('_')}


def _assemble(items,notes):
    def every(field):return [i for i in items if i['field']==field]
    def one(field):return next(iter(every(field)),None)
    intents=[i['value'] for i in every('activity')];excluded=[i['value'] for i in every('exclude')]
    patch={};warnings=list(notes)
    if one('region'):patch['region']=one('region')['value']
    if intents:patch['themes']=list(dict.fromkeys(INTENTS[key][0] for key in intents))
    if one('setting'):patch['setting']=one('setting')['value']
    if one('date'):patch.update(date_category=one('date')['_category'],date_subcategory=one('date')['value'])
    for field in ('people','count','meeting_type'):
        if one(field):patch[field]=one(field)['value']
    avoid=every('avoid')
    if avoid:
        patch['avoid']=[word for item in avoid for word in item['_words']]
        warnings.append(' · '.join(item['value'] for item in avoid)+' 제외: 이름이나 분류에 관련 단어가 들어간 장소를 뺐어요. 메뉴까지 확인한 것은 아니에요.')
    unit_budget=None
    budget=one('budget')
    if budget and budget['_per_person']:
        unit_budget=budget['value'];warnings.append(f'1인당 {unit_budget:,}원은 선택한 인원수로 곱해 전체 예산에 반영해요.')
    elif budget:patch['budget']=budget['value']
    transport=one('transport')
    if transport:
        patch['transport']=transport['value']
        if transport.get('_walk_less'):warnings.append(WALK_WARNING)
    if one('reservation'):patch['reservation']=False
    if one('priority'):patch['priority']=one('priority')['value']
    budget_style='low' if one('budget_style') else None
    if budget_style:warnings.append(LOW_WARNING)
    if one('max_walk'):patch['max_walk']=one('max_walk')['value']
    exclusive=bool(one('theme_mode')) and len(intents)==1
    if exclusive:
        patch['theme_mode']='focus'
        if intents[0]!='meal':patch['include_meal']=False
    return dict(intents=intents,excluded=excluded,exclusive=exclusive,patch=patch,unit_budget=unit_budget,warnings=warnings,budget_style=budget_style)


@lru_cache(maxsize=512)
def interpret(text,ignore=()):
    """text 를 해석한다. ignore: 화면에서 사용자가 뺀 항목 id(튜플)."""
    raw=_extract(text)
    skip=set(ignore)
    items=[i for i in raw['items'] if i['id'] not in skip]
    result=_assemble(items,raw['notes'])
    # 집중 항목은 활동이 하나일 때만 효과가 있다. 활동을 빼서 효과가 없으면 보이지 않는다.
    shown=[i for i in items if i['field']!='theme_mode' or result['exclusive']]
    result.update(items=[_public(i) for i in shown],ignored=[_public(i) for i in raw['items'] if i['id'] in skip],
                  unparsed=[dict(u) for u in raw['unparsed']])
    return result


def resolved_patch(parsed,people=2,explicit_people=False):
    """Resolve per-person amounts with the actual form, never a cached total."""
    patch=dict(parsed['patch'])
    if explicit_people:patch.pop('people',None)
    if parsed.get('unit_budget') is not None:
        total=parsed['unit_budget']*patch.get('people',people)
        if total<=10000000:patch['budget']=total
    return patch


def ignored_ids(c):
    value=c.get('request_ignore') if isinstance(c,dict) else getattr(c,'request_ignore',None)
    return tuple(sorted(set(value or ())))


def intent(c):return interpret(c.course_query+' '+c.request,ignored_ids(c))


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
