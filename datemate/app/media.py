"""검수된 장소별 웹 사진을 원문·저작자·라이선스와 함께 제공한다."""
import json
import re
from urllib.parse import urlsplit
from .config import ROOT
from .image_search import search_place_images

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

def media_info(place):
    searched=search_place_images(place)
    if searched['photos']:
        return dict(place_id=place['id'],photos=searched['photos'],wikidata_id=None,status='available',
            search_status=searched['status'],description=place.get('description'),message='네이버 이미지 검색 결과 · 저작자 및 개별 이용 조건 미검증')
    photos=photos_for(place)
    return dict(place_id=place['id'],photos=[dict(p,image_url=p['url']) for p in photos],
        wikidata_id=place['id'] if not place.get('demo') and re.fullmatch(r'Q[1-9][0-9]*',place['id']) else None,
        status='available' if photos else 'demo' if place.get('demo') else 'not_found',search_status=searched['status'],
        description=place.get('description'),
        message='가상 장소이므로 실제 장소 사진을 제공하지 않습니다.' if place.get('demo') else
                '' if photos else '이 장소와 일치하고 이용 조건이 확인된 사진을 아직 확보하지 못했습니다.')
