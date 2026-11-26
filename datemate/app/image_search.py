"""네이버 검색 API(NAVER API HUB) 공통 도우미: 키 확인, 주소·글자 정리, 제목 대조.

2026-11-20(특약 2단계, docs/naver-terms-stage2-design.ko.md 3.4(c)): 네이버 이미지 검색으로 장소 사진을 고르던 기능
(제목 규칙으로 거르고 다시 줄 세우던 search_place_images·strict_place_images)을 없앴다. 검색 결과를 골라 쓰는 것이
특약 1.2(가공 없이, 순위·내용 수정 금지)와 맞지 않기 때문이다. 장소 사진은 등록 사진과 한국관광공사 사진만 쓰고(app/media.py),
없으면 화면이 '네이버 지도에서 사진 보기' 링크를 보여 준다. 이 파일은 이름만 남았고 이미지 검색을 부르지 않는다.
"""
import html
import os
import re
import threading
from urllib.parse import urlsplit, unquote

_lock=threading.Lock()
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
