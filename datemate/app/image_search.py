"""NAVER API HUB 이미지 검색. 2026-07-31 이후 신규 신청 경로를 사용한다."""
import hashlib
import html
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, unquote
import httpx
from .telemetry import observed_http
from .search_address_text import place_query,street_address

_lock=threading.Lock()
_image_slots=threading.BoundedSemaphore(3)
# Shared provider slots are waited for briefly; a busy slot returns 'unavailable'
# instead of parking request threads (and exhausting the thread pool) behind it.
LOCK_WAIT_SECONDS=2.5

def search_enabled():
    return bool(os.getenv('NAVER_SEARCH_CLIENT_ID') and os.getenv('NAVER_SEARCH_CLIENT_SECRET'))

def safe_https(url):
    try:
        parsed=urlsplit(url)
        return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError,ValueError):return False

def safe_web_url(url):
    try:
        p=urlsplit(url)
        return p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password
    except (TypeError,ValueError):return False

def usable_image(item):
    thumb=item.get('thumbnail','');original=item.get('link','')
    if safe_https(thumb):return thumb
    if (not thumb or safe_web_url(thumb)) and safe_https(original):return original
    return None

def plain(value):return html.unescape(re.sub(r'<[^>]*>',' ',str(value))).strip()[:300]

def image_aliases(place):
    aliases=list(place.get('image_aliases') or [])
    wiki=urlsplit(place.get('wikipedia') or '')
    if wiki.hostname=='ko.wikipedia.org':
        name=unquote(wiki.path.rsplit('/',1)[-1]).replace('_',' ')
        name=re.sub(r'\s*\([^)]*\)$','',name).strip()
        if name and name!=place['name']:aliases.append(name)
    return list(dict.fromkeys(aliases))

def title_matches(place,title,aliases):
    def compact(s):return re.sub(r'[\W_]+','',s).casefold()
    value=compact(title)
    keys=place.get('image_keywords')
    if keys:return all(compact(w) in value for w in keys)
    for name in [place['name'],*aliases]:
        if compact(name) and compact(name) in value:return True
        words=[compact(w) for w in name.split() if compact(w)]
        # Keep every name/branch token; tolerate intervening words and punctuation.
        if len(words)>1 and all(w in value for w in words):return True
    return False

def _search_place_images(place):
    if place.get('demo'):return {'status':'demo','photos':[]}
    if not search_enabled():return {'status':'key_missing','photos':[]}
    # Local listing uses 'SAAN 2'; published photos use SAAN / 산 을지로점.
    # Scope the alias by its verified street address to avoid other SAAN branches.
    if re.sub(r'\s+','',place['name']).casefold()=='saan2' and re.search(r'충무로4길\s*3(?:\s|$)',(place.get('address') or '')):
        place=dict(place,image_aliases=['SAAN 을지로 카페','산 을지로점','SAAN2'],image_keywords=['SAAN','을지로'],image_queries=['SAAN 을지로 카페 서울','SAAN2 카페'])
    aliases=image_aliases(place)
    from .regions import normalize_region, region_from_address
    region=normalize_region(place.get('region')) or region_from_address(place.get('address')) or ''
    query=f'{aliases[0] if aliases else place["name"]} {region}'.strip()
    if not _image_slots.acquire(timeout=LOCK_WAIT_SECONDS):return {'status':'unavailable','photos':[],'busy':True}
    try:
        with httpx.Client(timeout=7) as client:
            items=[]
            district=re.search(r'\s([가-힣]+(?:구|시|군))(?=\s|$)',(place.get('address') or ''))
            queries=place.get('image_queries') or list(dict.fromkeys([query,*([place_query(place)] if street_address(place.get('address')) else []),*([place['name']+' '+district[1]+' 사진'] if district else [])]))
            for search_query in queries[:3]:
                response=observed_http(client.get,'https://naverapihub.apigw.ntruss.com/search/v1/image',params={'query':search_query,'display':30,'start':1,'sort':'sim','filter':'all','format':'json'},
                    headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
                response.raise_for_status();batch=response.json()
                if not isinstance(batch,dict) or not isinstance(batch.get('items',[]),list):raise ValueError('invalid_response')
                items.extend(batch.get('items',[]))
                if not place.get('image_queries') and any(isinstance(i,dict) and title_matches(place,plain(i.get('title','')),aliases) and usable_image(i) and safe_web_url(i.get('link','')) for i in items):break
            data={'items':items}
        if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):raise ValueError('invalid_response')
        photos=[];seen=set()
        for rank,item in enumerate(data.get('items',[]),1):
            if not isinstance(item,dict):continue
            title=plain(item.get('title',''));image=usable_image(item);original=item.get('link','')
            # 이름이 다른 이미지·중복·실행 가능한 URL을 제외한다. 제목 일치는 검수 완료와 다르다.
            matched=title_matches(place,title,aliases)
            if not matched or not image or not safe_web_url(original) or original in seen:continue
            seen.add(original)
            photos.append(dict(id=f'naver-{rank}',kind='search_result',provider='네이버 이미지 검색',rank=rank,sort='sim',
                title=title,image_url=image,url=image,source=original,search_url='https://search.naver.com/search.naver?'+urlencode({'where':'image','query':query}),
                caption=f'{place["name"]} {region} 검색 결과의 참고 이미지입니다. 장소 일치 여부와 이용 조건은 원본에서 확인해 주세요.',
                author=None,license=None,license_url=None,taken_at=None,checked_at=datetime.now(timezone.utc).isoformat(),
                association=f'장소명+{region} 검색 및 제목 문자 일치 · 별도 실물 검수 아님'))
            if len(photos)==5:break
        def role(photo):
            title=photo['title']
            if re.search(r'내부|인테리어|전경|공간|외관',title):return '공간 관련 제목'
            if re.search(r'메뉴|음식|디저트|커피|파스타|요리',title):return '음식·메뉴 관련 제목'
            return '장소 관련 검색 사진'
        for photo in photos:photo['image_role']=role(photo)
        photos.sort(key=lambda p:0 if p['image_role']=='공간 관련 제목' else 1)
        return {'status':'available' if photos else 'not_found','photos':photos}
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return {'status':'unavailable','photos':[]}
    finally:_image_slots.release()


# ---------------------------------------------------------------- 엄격한 가게 사진 검색(2026-11-19 사용자 결정)
# 왜: 네이버 화면 자동 조회를 끈 뒤(app/naver_pages.py) 음식점 사진이 거의 없어졌다. 관광공사(app/tour_places.py)에는 음식점 사진이 드물다.
#   전에는 '제목만 맞는 이미지 검색 결과'를 쓰지 않았는데(다른 가게 사진이 섞임), 사용자가 이번에 엄격하게 거른다는 조건으로 바꿨다.
# 쓰는 곳: app/media.py 가 등록·관광공사 사진으로 2장이 안 되는 '카페·미식' 장소에만 부른다(strict_place_images).
# 거르는 규칙(strict_title_match). 공식 API 는 사진이 실린 글의 제목만 주므로(글 주소·주소 필드 없음) 제목으로만 판단한다. 애매하면 쓰지 않는다.
#   1) 가게 이름(지점 낱말을 뗀 이름)이 낱말 경계로 나온다. 앞에 글자가 붙으면('레드어니언') 다른 가게, 뒤에 붙는 것은 조사·'맛집' 같은 말만 허용.
#   2) 이름 바로 뒤의 지점('○○점')은 우리 지점과 같아야 한다. 우리 이름에 지점이 있으면 제목에도 그 지점이 있어야 한다.
#   3) 이름(과 지점) 밖에 우리 동네·주소 낱말(구·동·도로명, 지점 동네)이 하나 이상 있다. 이름 속 글자('명동교자'의 명동)는 세지 않는다.
#   4) 여러 가게를 모은 글(○곳·BEST·TOP·모음·총정리·순위 등)과 다른 시·도 이름이 나온 제목은 뺀다.
#   5) 이름이 두 글자 이하(공백·기호 제외)면 흔한 낱말과 겹쳐 아예 찾지 않는다.
STRICT_CACHE_SECONDS=3600
STRICT_MAX_PHOTOS=3
STRICT_MIN_NAME=3
_LETTER=re.compile(r'[가-힣A-Za-z0-9]')
# 이름 바로 뒤에 붙어도 되는 말. 조사는 그 뒤가 끊겨야 하고('어니언이야기'는 다른 가게), 아래 낱말은 해시태그처럼 이어 써도 된다('#금돼지식당웨이팅').
_PARTICLES=('에서','으로','이랑','에','의','은','는','이','가','을','를','와','과','도','만','로','랑')
_SUFFIX_WORDS=('맛집','후기','방문','웨이팅','메뉴','내부','외관')
_BRANCH_AFTER=re.compile(r'\s*([가-힣A-Za-z0-9]{1,8}?)점(?![가-힣A-Za-z0-9])')
_LISTING=re.compile(r'\d+\s*(?:곳|선|군데|개\s*(?:맛집|가게|매장))|(?<![A-Za-z])(?:best|top)(?![A-Za-z])|베스트|모음|총정리|리스트|순위|(?<![A-Za-z])vs(?![A-Za-z])',re.I)
_NOT_LOCALITY={'서울','부산','대구','인천','광주','대전','울산','세종','경기','강원','충북','충남','전북','전남','경북','경남','제주','특별','광역'}


def _strict_compact(value):return re.sub(r'[\W_]+','',str(value or '')).casefold()


def split_branch(name):
    """('명동교자','본점') / ('능동미나리','용산점') / ('어니언',''). app/course_search.without_branch 와 같은 기준."""
    from .course_search import without_branch
    base=without_branch(name or '').strip()
    branch=(name or '').strip()[len(base):].strip() if base!=(name or '').strip() else ''
    return base,branch


def branch_place(branch):
    """지점 낱말의 동네 부분: '용산점'→'용산', '합정본점'→'합정', '본점'·'2호점'→''."""
    stem=re.sub(r'(?:본점|직영점|\d+호점|점)$','',branch or '').strip()
    return stem if len(stem)>=2 and not re.search(r'\d',stem) else ''


def locality_words(place):
    """주소(도로명·지번)에서 뽑은 동네 낱말. '서울 마포구 독막로8길 16' → {'마포구','마포','독막로','독막'}."""
    words=set()
    for address in (place.get('address'),place.get('lot_address')):
        for word in re.split(r'[\s,()]+',str(address or '')):
            word=word.strip()
            if not word or word in _NOT_LOCALITY:continue
            m=re.fullmatch(r'([가-힣]+)(구|군|시)',word)
            if m and not re.search(r'(특별|광역|자치)',word):
                words.add(word)
                if len(m[1])>=2:words.add(m[1])
                continue
            m=re.fullmatch(r'([가-힣]+?)\d*(동|읍|면|리)(?:\d+가)?',word)
            if m:
                words.add(m[1]+m[2])
                if len(m[1])>=2:words.add(m[1])
                continue
            road=re.sub(r'\d+(?:번)?길$','',word)
            if road!=word or re.search(r'(?:대로|로|길)$',road):
                if len(road)>=2 and not road.isdigit():words.add(road)
                stem=re.sub(r'(?:대로|로|길)$','',road)
                if len(stem)>=2:words.add(stem)
    return {w for w in words if len(w)>=2 and w not in _NOT_LOCALITY}


def _attached_ok(rest):
    if rest.startswith(_SUFFIX_WORDS):return True
    return any(rest.startswith(p) and not _LETTER.match(rest[len(p):len(p)+1] or ' ') for p in _PARTICLES)


def _region_mentioned(alias,text):
    """다른 시·도 이름이 낱말로 나오는지('부산 중구', '#부산맛집'). '세종대로'·'대구탕'처럼 다른 낱말의 일부는 세지 않는다."""
    return bool(re.search(r'(?<![가-힣A-Za-z])'+re.escape(alias)+r'(?:(?![가-힣A-Za-z])|(?=맛집|여행|핫플|데이트|카페))',text))


def _name_pattern(base):
    tokens=[re.escape(t) for t in base.split() if t]
    return re.compile(r'(?<![가-힣A-Za-z0-9])'+r'[\s·_\-]*'.join(tokens),re.I) if tokens else None


def strict_title_match(place,title):
    """제목이 우리 가게(지점 포함)와 동네를 함께 말하면 근거 낱말(dict), 아니면 None. 규칙은 위 머리 주석."""
    from .regions import ALIASES,normalize_region,region_from_address
    text=plain(title)
    base,branch=split_branch(place.get('name'))
    if len(_strict_compact(base))<STRICT_MIN_NAME:return None
    if _LISTING.search(text):return None
    region=normalize_region(place.get('region')) or region_from_address(place.get('address'))
    if region and any(found!=region and _region_mentioned(alias,text) for alias,found in ALIASES.items()):return None
    pattern=_name_pattern(base)
    if pattern is None:return None
    localities=locality_words(place)
    ours=_strict_compact(branch);loc=branch_place(branch)
    spans=[];branch_seen=False
    for m in pattern.finditer(text):
        end=m.end();rest=text[end:]
        tail=_BRANCH_AFTER.match(rest)
        if tail:
            found=_strict_compact(tail[1]+'점')
            stem=branch_place(tail[1]+'점')
            if ours:
                if found!=ours:return None
                branch_seen=True
            elif not (stem and stem in localities):return None
            spans.append((m.start(),end+tail.end()))
            continue
        if rest and _LETTER.match(rest[0]) and not _attached_ok(rest):continue
        spans.append((m.start(),end))
    if not spans:return None
    outside=text
    for s,e in sorted(spans,reverse=True):outside=outside[:s]+' '+outside[e:]
    if ours and not branch_seen:
        # 지점이 이름에 붙어 나오지 않았으면, 이름 밖에 우리 지점 낱말('본점')이나 지점 동네('용산')가 있어야 한다.
        compact_outside=_strict_compact(outside)
        if ours in compact_outside:branch_seen=True
        elif loc and loc in outside:branch_seen=True
        if not branch_seen:return None
    near=next((w for w in sorted(localities,key=len,reverse=True) if w in outside),None)
    if near is None and branch_seen and loc:near=loc
    if near is None:return None
    return dict(name=base,branch=branch or None,locality=near)


def _strict_search(place):
    """(상태, 사진 목록). 검색어 최대 2개(이름+도로명 주소, 이름+동네 낱말), 결과마다 strict_title_match."""
    base,branch=split_branch(place.get('name'))
    if len(_strict_compact(base))<STRICT_MIN_NAME:return 'not_applicable',[]
    localities=sorted(locality_words(place),key=lambda w:(-len(w),w))
    near=branch_place(branch) or next((w for w in localities if not re.search(r'(?:구|군|시)$',w)),None) or (localities[0] if localities else '')
    queries=list(dict.fromkeys(q for q in (place_query(place),f'{place["name"]} {near}'.strip()) if q))[:2]
    if not _image_slots.acquire(timeout=LOCK_WAIT_SECONDS):return 'busy',[]
    try:
        photos=[];seen=set()
        with httpx.Client(timeout=7) as client:
            for query in queries:
                response=observed_http(client.get,'https://naverapihub.apigw.ntruss.com/search/v1/image',params={'query':query,'display':30,'start':1,'sort':'sim','filter':'all','format':'json'},
                    headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
                response.raise_for_status();batch=response.json()
                if not isinstance(batch,dict) or not isinstance(batch.get('items',[]),list):raise ValueError('invalid_response')
                for item in batch.get('items',[]):
                    if not isinstance(item,dict):continue
                    original=str(item.get('link') or '');thumb=str(item.get('thumbnail') or '')
                    image=original if safe_https(original) else thumb if safe_https(thumb) else None
                    # 원본 주소가 웹 주소가 아니면(실행 가능한 주소 등) 출처를 보여 줄 수 없으므로 쓰지 않는다.
                    if not image or not safe_web_url(original) or original in seen:continue
                    match=strict_title_match(place,item.get('title',''))
                    if not match:continue
                    seen.add(original)
                    search_url='https://search.naver.com/search.naver?'+urlencode({'where':'image','query':query})
                    photos.append(dict(id='image-search-'+hashlib.sha256(original.encode()).hexdigest()[:16],kind='image_search',provider='네이버 이미지 검색 API',
                        source_label='검색 사진',source_type='image_search',title=' '.join(plain(item.get('title','')).split())[:160],
                        image_url=image,url=thumb if safe_https(thumb) else image,source=original,search_url=search_url,
                        caption='네이버 이미지 검색에서 제목에 가게 이름'+('(지점 포함)' if match['branch'] else '')+'과 동네('+match['locality']+')가 함께 나온 사진이에요. 다른 곳 사진일 수 있으니 원본에서 확인해 주세요.',
                        author=None,license=None,license_url=None,taken_at=None,checked_at=datetime.now(timezone.utc).isoformat(),
                        association='이미지 검색 제목의 가게 이름·지점·동네 일치(엄격) · 실물 검수 아님',image_role='검색 사진',match=match))
                    if len(photos)>=STRICT_MAX_PHOTOS:break
                if len(photos)>=STRICT_MAX_PHOTOS:break
        return ('available' if photos else 'not_found'),photos
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return 'unavailable',[]
    finally:_image_slots.release()


def strict_place_images(place,force=False):
    """media.py 가 쓰는 엄격한 가게 사진 검색. dict(status, photos). 성공(찾음·없음)은 1시간 캐시, 실패·바쁨은 캐시하지 않는다."""
    if place.get('demo'):return {'status':'demo','photos':[]}
    if not search_enabled():return {'status':'key_missing','photos':[]}
    from . import store
    import json
    key='image-strict-v1:'+hashlib.sha256(json.dumps([place.get(k) for k in ('id','name','address','lot_address','region')],ensure_ascii=False).encode()).hexdigest()
    if not force:
        cached=store.cached(key)
        if cached:return cached
    status,photos=_strict_search(place)
    result={'status':status,'photos':photos}
    if status in ('available','not_found','not_applicable'):store.cache(key,result,STRICT_CACHE_SECONDS)
    return result


def search_place_images(place,force=False):
    if not place.get('id') or place.get('demo') or not search_enabled():
        result=_search_place_images(place);result.pop('busy',None);return result
    from . import store
    import hashlib,json
    key='image-search-v4:'+hashlib.sha256(json.dumps([place.get(k) for k in ('id','name','address','image_aliases','image_keywords','image_queries','wikipedia')],ensure_ascii=False).encode()).hexdigest()
    if not force:
        cached=store.cached(key)
        if cached:return cached
    result=_search_place_images(place)
    if result.pop('busy',False):return result
    store.cache(key,result,3600 if result['photos'] else 60)
    return result
