"""Bounded, cached nationwide festival lookup from Korea Tourism Organization."""

import html
import os
import re
from datetime import date, timedelta
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Path, Query

from . import store
from .regions import korean_coordinates, normalize_region, region_from_address
from .telemetry import observed_http

router = APIRouter()
ENDPOINT = 'https://apis.data.go.kr/B551011/KorService2/searchFestival2'
DETAIL_ENDPOINT = 'https://apis.data.go.kr/B551011/KorService2/detailIntro2'
REGION_CODES = {
    '서울': '11', '부산': '26', '대구': '27', '인천': '28', '광주': '29',
    '대전': '30', '울산': '31', '세종': '36', '경기': '41', '강원': '51',
    '충북': '43', '충남': '44', '전북': '52', '전남': '46', '경북': '47',
    '경남': '48', '제주': '50',
}
IMAGE_HOST = 'tong.visitkorea.or.kr'
IMAGE_LICENSES = ('Type1', 'Type3')


def plain(value):
    return re.sub(r'<[^>]*>', ' ', html.unescape(str(value or ''))).strip()[:200]


def detail_text(value):
    """Provider free text (fee, hours) as one tidy line: HTML removed, <br> kept as a space, max 300 chars."""
    text = re.sub(r'<[^>]*>', ' ', html.unescape(str(value or '')))
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300] or None


def coordinates(item):
    """(lat, lon) from mapy/mapx, or (None, None) when missing or outside Korea."""
    try:
        lat, lon = float(item.get('mapy')), float(item.get('mapx'))
    except (TypeError, ValueError):
        return None, None
    if not (lat == lat and lon == lon) or not korean_coordinates(lat, lon):
        return None, None
    return lat, lon


def parse_day(value):
    try:
        return date.fromisoformat(f'{value[:4]}-{value[4:6]}-{value[6:8]}') if len(value) == 8 and value.isdigit() else None
    except ValueError:
        return None


def festival_image(item):
    """Provider photo URL only when its public-use license (KOGL Type1/Type3) is explicit."""
    license_type = str(item.get('cpyrhtDivCd') or '').strip()
    if license_type not in IMAGE_LICENSES:
        return None, None
    # 썸네일(firstimage2)은 가로 300px 이하라 카드에서 깨져 보인다. 원본을 먼저 쓴다.
    for field in ('firstimage', 'firstimage2'):
        url = str(item.get(field) or '').strip()
        try:
            parsed = urlsplit(url)
            allowed = (parsed.scheme == 'https' and parsed.hostname == IMAGE_HOST and parsed.netloc == IMAGE_HOST
                       and len(url) <= 500)
        except ValueError:
            continue
        if allowed:
            return url, license_type
    return None, None


def normalize_item(item, start, end, region):
    if not isinstance(item, dict):
        return None
    first = parse_day(str(item.get('eventstartdate', '')))
    last = parse_day(str(item.get('eventenddate', '')))
    address = plain(item.get('addr1'))
    title = plain(item.get('title'))
    place_region = region_from_address(address)
    if not title or not first or not last or first > last or first > end or last < start:
        return None
    if not place_region or (region and place_region != region):
        return None
    content_id = str(item.get('contentid', ''))
    image_url, image_license = festival_image(item)
    lat, lon = coordinates(item)
    return dict(
        id=content_id if content_id.isdigit() else title + ':' + first.isoformat(),
        title=title, start=first.isoformat(), end=last.isoformat(),
        region=place_region, address=address,
        source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=' + quote(title),
        image_url=image_url, image_license=image_license, lat=lat, lon=lon,
    )


def festival_order(item):
    """Short events first so year-round programs do not bury this week's festivals."""
    days = (date.fromisoformat(item['end']) - date.fromisoformat(item['start'])).days
    return days, item['start'], item['title']


def fetch_festivals(start, end, region):
    key = os.getenv('TOUR_API_KEY', '').strip()
    if not key:
        return dict(status='key_missing', festivals=[], message='한국관광공사 관광정보 API 키를 설정하면 실제 축제를 조회할 수 있어요.')
    cache_key = f'festivals:v5:{start}:{end}:{region or "all"}'
    cached = store.cached(cache_key)
    if cached:
        return cached
    items = []
    total = 0
    page_size = 500
    try:
        with httpx.Client(timeout=10) as client:
            for page in range(1, 11):
                params = dict(
                    serviceKey=key, MobileOS='ETC', MobileApp='DateMate', _type='json',
                    eventStartDate=(start - timedelta(days=366)).strftime('%Y%m%d'),
                    eventEndDate=end.strftime('%Y%m%d'),
                    numOfRows=page_size, pageNo=page,
                )
                if region:
                    params['lDongRegnCd'] = REGION_CODES[region]
                response = observed_http(client.get, ENDPOINT, params=params)
                response.raise_for_status()
                if len(response.content) > 5_000_000:
                    raise ValueError('oversized_response')
                body = response.json().get('response', {})
                header = body.get('header', {})
                if str(header.get('resultCode', '0000')) not in ('0000', '00'):
                    raise ValueError('provider_error')
                payload = body.get('body', {})
                total = int(payload.get('totalCount', 0))
                group = (payload.get('items') or {}).get('item') or []
                items.extend(group if isinstance(group, list) else [group])
                if page * page_size >= total or not group:
                    break
        rows = {}
        for item in items:
            row = normalize_item(item, start, end, region)
            if row:
                rows[row['id']] = row
        result = dict(
            status='available',
            festivals=sorted(rows.values(), key=festival_order)[:120],
            total_matches=len(rows), truncated=total > len(items) or len(rows) > 120,
            checked_at=date.today().isoformat(),
            message='한국관광공사 행사정보 자료입니다. 개최·취소·시간·요금은 방문 전 주최 측에서 다시 확인해 주세요.',
        )
        store.cache(cache_key, result, 3600)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return dict(status='unavailable', festivals=[], message='축제 자료에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.')


def fetch_festival_detail(content_id):
    """Fee and hours as the organizer wrote them. Shown as text only, never parsed into course costs."""
    key = os.getenv('TOUR_API_KEY', '').strip()
    if not key:
        return dict(status='key_missing', fee=None, hours=None, place=None, checked_at=None,
                    message='한국관광공사 관광정보 API 키를 설정하면 이용요금을 확인할 수 있어요.')
    cache_key = f'festival-detail:v1:{content_id}'
    cached = store.cached(cache_key)
    if cached:
        return cached
    try:
        with httpx.Client(timeout=10) as client:
            params = dict(serviceKey=key, MobileOS='ETC', MobileApp='DateMate', _type='json',
                          contentId=content_id, contentTypeId='15')
            response = observed_http(client.get, DETAIL_ENDPOINT, params=params)
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError('oversized_response')
            body = response.json().get('response', {})
            header = body.get('header', {})
            if str(header.get('resultCode', '0000')) not in ('0000', '00'):
                raise ValueError('provider_error')
            group = ((body.get('body') or {}).get('items') or {}).get('item') or []
            item = (group if isinstance(group, list) else [group])[:1]
            item = item[0] if item and isinstance(item[0], dict) else {}
        result = dict(
            status='available',
            fee=detail_text(item.get('usetimefestival')),
            hours=detail_text(item.get('playtime')),
            place=detail_text(item.get('eventplace')),
            checked_at=date.today().isoformat(),
            message='주최 측이 한국관광공사에 제공한 안내예요. 방문 전 다시 확인해 주세요.',
        )
        store.cache(cache_key, result, 86400)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return dict(status='unavailable', fee=None, hours=None, place=None, checked_at=None,
                    message='요금 정보를 불러오지 못했어요.')


@router.get('/api/festivals/{content_id}/detail')
def festival_detail(content_id: str = Path(pattern=r'^\d{1,12}$')):
    return fetch_festival_detail(content_id)


@router.get('/api/festivals')
def festivals(start: date, end: date, region: str = Query(default='전국', max_length=20)):
    if end < start or (end - start).days > 92:
        raise HTTPException(422, '조회 기간은 1일부터 최대 93일까지 선택해 주세요.')
    normalized = None if region == '전국' else normalize_region(region)
    if region != '전국' and not normalized:
        raise HTTPException(422, '지원하지 않는 지역입니다.')
    return fetch_festivals(start, end, normalized)
