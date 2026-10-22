"""NAVER API HUB 이미지 검색. 2026-07-31 이후 신규 신청 경로를 사용한다."""
import html
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
import httpx

_lock=threading.Lock()

def search_enabled():
    return bool(os.getenv('NAVER_SEARCH_CLIENT_ID') and os.getenv('NAVER_SEARCH_CLIENT_SECRET'))

def safe_https(url):
    try:
        parsed=urlsplit(url)
        return parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError,ValueError):return False

def plain(value):return html.unescape(re.sub(r'<[^>]*>',' ',str(value))).strip()[:300]

def search_place_images(place):
    if place.get('demo'):return {'status':'demo','photos':[]}
    if not search_enabled():return {'status':'key_missing','photos':[]}
    aliases=place.get('image_aliases') or []
    query=f'{aliases[0] if aliases else place["name"]} 서울'
    try:
        with _lock, httpx.Client(timeout=10) as client:
            response=client.get('https://naverapihub.apigw.ntruss.com/search/v1/image',params={'query':query,'display':10,'start':1,'sort':'sim','filter':'all','format':'json'},
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']})
            response.raise_for_status();data=response.json()
        if not isinstance(data,dict) or not isinstance(data.get('items',[]),list):raise ValueError('invalid_response')
        photos=[];seen=set();name=re.sub(r'\s+','',place['name']).casefold()
        keywords=place.get('image_keywords') or [place['name']]
        for rank,item in enumerate(data.get('items',[]),1):
            if not isinstance(item,dict):continue
            title=plain(item.get('title',''));image=item.get('thumbnail','');original=item.get('link','')
            # 이름이 다른 이미지·중복·실행 가능한 URL을 제외한다. 제목 일치는 검수 완료와 다르다.
            compact=re.sub(r'\s+','',title).casefold()
            matched=all(re.sub(r'\s+','',word).casefold() in compact for word in keywords) or any(re.sub(r'\s+','',alias).casefold() in compact for alias in aliases)
            if not matched or not safe_https(image) or not safe_https(original) or original in seen:continue
            seen.add(original)
            photos.append(dict(id=f'naver-{rank}',kind='search_result',provider='네이버 이미지 검색',rank=rank,sort='sim',
                title=title,image_url=image,url=image,source=original,search_url='https://search.naver.com/search.naver?'+urlencode({'where':'image','query':query}),
                caption=f'{place["name"]} 서울 검색 결과의 참고 이미지입니다. 장소 일치 여부와 이용 조건은 원본에서 확인해 주세요.',
                author=None,license=None,license_url=None,taken_at=None,checked_at=datetime.now(timezone.utc).isoformat(),
                association='장소명+서울 검색 및 제목 문자 일치 · 별도 실물 검수 아님'))
            if len(photos)==5:break
        return {'status':'available' if photos else 'not_found','photos':photos}
    except (httpx.HTTPError,ValueError,TypeError,KeyError):return {'status':'unavailable','photos':[]}
