"""검수된 장소별 웹 사진을 원문·저작자·라이선스와 함께 제공한다."""
import json
import re
from urllib.parse import urlsplit,urlencode
from .search_address_text import place_query
from .config import ROOT
from .image_search import search_place_images,search_enabled

def validated_photo(photo):
    required=('id','url','source','title','author','license','license_url','checked_at','association')
    if not all(isinstance(photo.get(k),str) and photo[k].strip() for k in required):return False
    # 서버에서 임의 URL/사설망을 다운로드하지 않는다. 등록부는 운영자가 검수한다.
    image=urlsplit(photo['url']);source=urlsplit(photo['source']);license=urlsplit(photo['license_url'])
    return (image.scheme=='https' and image.netloc=='upload.wikimedia.org' and image.path.startswith('/wikipedia/commons/')
        and image.path.lower().endswith(('.jpg','.jpeg','.png')) and not image.query
        and source.scheme=='https' and source.netloc=='commons.wikimedia.org'
        and license.scheme=='https' and license.netloc=='creativecommons.org'
        and bool(re.fullmatch(r'CC BY(?:-SA)? [1-4]\.0|CC0|Public domain',photo['license'])))

def photos_for(place):
    if place.get('demo'):return []
    registry=ROOT/'data'/'place_photos.json'
    rows=json.loads(registry.read_text(encoding='utf-8')).get(place['id'],[]) if registry.exists() else []
    # 검수되지 않은 장소 사진이나 가상 장소와 실제 사진을 섞지 않는다.
    result=[];seen=set()
    for photo in rows:
        if not validated_photo(photo) or photo['url'] in seen:continue
        seen.add(photo['url']);result.append(photo)
        if len(result)==5:break
    return result

def media_info(place,prefer_public=False,force=False):
    from .public_place_photos import public_place_photos
    searched=public_place_photos(place,force) if prefer_public else search_place_images(place,force)
    if not searched['photos'] and not place.get('demo') and not prefer_public and search_enabled() and not photos_for(place):
        searched=public_place_photos(place,force)
    if prefer_public or searched.get('photo_source')=='naver_public_place':
        if searched['photos']:return dict(searched,place_id=place['id'],wikidata_id=None,description=place.get('description'),message='해당 업체에 연결된 공개 사진 · 개별 이용 조건 미검증')
    if searched['photos']:
        return dict(place_id=place['id'],photos=searched['photos'],wikidata_id=None,status='available',
            search_status=searched['status'],description=place.get('description'),message='네이버 이미지 검색 결과 · 저작자 및 개별 이용 조건 미검증')
    photos=photos_for(place)
    return dict(place_id=place['id'],photos=[dict(p,image_url=p['url']) for p in photos],
        wikidata_id=place['id'] if not place.get('demo') and re.fullmatch(r'Q[1-9][0-9]*',place['id']) else None,
        status='available' if photos else 'demo' if place.get('demo') else 'not_found',search_status=searched['status'],
        description=place.get('description'),search_url='https://search.naver.com/search.naver?'+urlencode({'where':'image','query':place_query(place)}),
        message='가상 장소이므로 실제 장소 사진을 제공하지 않습니다.' if place.get('demo') else
                '' if photos else {'key_missing':'네이버 이미지 검색 키가 설정되지 않았어요.','unavailable':'이미지 검색에 일시적으로 연결하지 못했어요. 잠시 후 다시 불러와 주세요.','not_found':'장소명과 지점이 맞는 검색 사진을 찾지 못했어요. 네이버 사진 검색에서 확인할 수 있어요.'}.get(searched['status'],'장소 사진을 찾지 못했어요.'))
