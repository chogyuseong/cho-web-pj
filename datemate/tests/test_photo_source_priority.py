import pytest
"""Business photos first. An image search result enters the gallery only when its title names the shop
(with its branch) and the shop's neighbourhood together (2026-11-19, app/image_search.strict_title_match);
a title that only matches the name is still rejected."""
import json
from app.media import media_info
from app.public_place_photos import extract_photo_records
from app.blog_photos import extract_blog_images
from test_public_place_photos import fixture


PLACE={'id':'source-priority-venue','name':'검증카페','lat':37.56,'lon':126.99,'category':'카페·미식','address':'서울 중구 검증로 1'}


def test_explicit_owner_photos_sorted_before_reviews_without_cdn_guess():
    state=fixture();scope=state['ROOT_QUERY']['detail']
    scope['visitorReviewPhotos']=[{'origin':'https://ldb-phinf.pstatic.net/review.jpg'}]
    scope['ownerPhotos']=[{'origin':'https://ldb-phinf.pstatic.net/owner.jpg'}]
    state['unrelated']['ownerPhotos']=[{'origin':'https://ldb-phinf.pstatic.net/other-owner.jpg'}]
    records,pid=extract_photo_records('window.__APOLLO_STATE__ = '+json.dumps(state),PLACE)
    assert pid=='123' and records[0]=={'url':'https://ldb-phinf.pstatic.net/owner.jpg','owner_verified':True,'review_verified':False}
    assert not next(row for row in records if row['url'].endswith('/place.jpg'))['owner_verified']
    assert next(row for row in records if row['url'].endswith('/review.jpg'))['review_verified']
    assert not any('other-owner' in row['url'] for row in records)


def test_owner_first_then_same_business_review_without_blog_call(monkeypatch):
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setattr('app.image_search.search_place_images',lambda *a:(_ for _ in ()).throw(AssertionError('loose image search must not run')))
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *a:(_ for _ in ()).throw(AssertionError('owner exists')))
    owner={'id':'owner','owner_verified':True,'source_label':'업체 등록 사진'}
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *a:{'photos':[{'id':'review'},owner],'photo_source':'naver_public_place'})
    result=media_info(PLACE)
    assert [p['id'] for p in result['photos']]==['owner','review']


def test_no_business_photo_uses_caption_matched_blog(monkeypatch):
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *a:{'photos':[],'status':'unavailable'})
    monkeypatch.setattr('app.media.photos_for',lambda *a:[])
    photo={'id':'caption-matched','source_type':'blog_review','source_label':'블로그 후기 사진'}
    calls=[]
    def blog(*a):calls.append('blog');return {'photos':[photo],'photo_source':'matched_blog_photos'}
    monkeypatch.setattr('app.blog_photos.blog_photos',blog)
    assert media_info(PLACE)['photos'][0]['id']==photo['id'] and calls==['blog']
    assert media_info(PLACE,prefer_public=True)['photos']==[]
    assert calls==['blog']


def test_matching_place_title_does_not_admit_unrelated_images_from_same_blog():
    place=PLACE|{'name':'종로 클라이밍','category':'레저·활동'}
    html='''<img src="https://blogfiles.pstatic.net/logo.jpg" alt="종로 클라이밍 내부">
    <div class="se-main-container">
      <div class="se-component"><p>종로 클라이밍 내부 시설</p></div>
      <div class="se-component"><img data-lazy-src="https://blogfiles.pstatic.net/gym.jpg"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/random.jpg"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/lunch.jpg" alt="종로 클라이밍 후 점심 맛집"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/other.jpg" alt="다른 지점 내부"></div>
      <div class="se-component"><img src="https://unrelated.example/unknown.jpg" alt="종로 클라이밍 내부"></div>
    </div>'''
    rows=extract_blog_images(html,place)
    assert [row['url'] for row in rows]==['https://blogfiles.pstatic.net/gym.jpg']


def test_explicit_image_caption_name_and_branch_required():
    place=PLACE|{'name':'클라이밍 파크 종로점','category':'레저·활동'}
    html='''<div class="se-main-container">
      <div class="se-component"><img src="https://blogfiles.pstatic.net/one.jpg" alt="클라이밍 파크 강남점 시설"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/two.jpg" alt="클라이밍 파크 종로점 내부"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/two.jpg" alt="클라이밍 파크 종로점 내부"></div>
    </div>'''
    assert len(extract_blog_images(html,place))==1


def test_no_matching_source_does_not_fall_back_to_arbitrary_image_api(monkeypatch):
    """이름만 맞는 이미지 검색 결과(다른 지점·다른 가게·동네 없음·모음 글)는 여전히 갤러리에 들어오지 않는다.
    엄격한 검색(strict_place_images)은 부르지만 그 안의 제목 거르기를 통과한 사진이 없다. 느슨한 search_place_images 는 부르지 않는다."""
    import httpx
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setenv('NAVER_SEARCH_CLIENT_ID','test');monkeypatch.setenv('NAVER_SEARCH_CLIENT_SECRET','test')
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *a:{'photos':[],'status':'not_found'})
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *a:{'photos':[],'status':'not_found'})
    monkeypatch.setattr('app.image_search.search_place_images',lambda *a:(_ for _ in ()).throw(AssertionError('title only image rejected')))
    titles=['검증카페 방문 후기','검증카페 강남점 중구','레드검증카페 중구','서울 중구 카페 BEST 5 검증카페','검증카페 부산 중구']
    def get(self,url,**kwargs):
        return httpx.Response(200,request=httpx.Request('GET',url),json={'items':[
            {'title':t,'thumbnail':f'https://search.pstatic.net/t{i}.jpg','link':f'https://postfiles.pstatic.net/o{i}.jpg'} for i,t in enumerate(titles)]})
    monkeypatch.setattr(httpx.Client,'get',get)
    result=media_info(PLACE|{'id':'source-priority-loose-'+str(id(titles))})
    assert not result['photos'] and result['image_search_status']=='not_found'
    # 사진이 끝내 없으면 빈칸 대신 네이버 지도 링크(이름 + 도로명 주소)를 준다.
    assert result['map_url'].startswith('https://map.naver.com/p/search/')


def test_strict_image_search_fills_a_short_food_gallery(monkeypatch):
    """등록·관광공사 사진으로 2장이 안 되는 카페·미식 장소만 엄격한 검색 사진('검색 사진')으로 채운다."""
    monkeypatch.setattr('app.media.search_enabled',lambda:False)
    monkeypatch.setattr('app.media.photos_for',lambda *a:[])
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *a:{'photos':[],'status':'not_found'})
    searched=dict(id='image-search-1',kind='image_search',source_label='검색 사진',title='검증카페 중구',image_url='https://postfiles.pstatic.net/a.jpg',
                  url='https://search.pstatic.net/a.jpg',source='https://postfiles.pstatic.net/a.jpg')
    calls=[]
    def strict(place,force=False):calls.append(place['id']);return {'status':'available','photos':[searched]}
    monkeypatch.setattr('app.image_search.strict_place_images',strict)
    result=media_info(PLACE)
    assert [p['id'] for p in result['photos']]==['image-search-1'] and "'검색 사진'" in result['message']
    assert result['photo_source']=='priority_place_photos' and result['map_url'].startswith('https://map.naver.com/p/search/')
    # 카페·미식이 아닌 장소, 등록 사진이 2장 이상인 장소, 업체 사진만 고르는 요청(fallback=place)은 부르지 않는다.
    assert media_info(PLACE|{'category':'레저·활동'})['photos']==[]
    two=[dict(id=f'r{i}',url=f'https://upload.wikimedia.org/wikipedia/commons/{i}.jpg') for i in range(2)]
    monkeypatch.setattr('app.media.photos_for',lambda *a:two)
    assert [p['id'] for p in media_info(PLACE)['photos']]==['r0','r1']
    monkeypatch.setattr('app.media.photos_for',lambda *a:[])
    assert media_info(PLACE,prefer_public=True)['photos']==[]
    assert calls==['source-priority-venue']


def test_business_tab_uses_only_explicit_owner_images_for_same_id(monkeypatch):
    import httpx
    from app.public_place_photos import owner_page_photos
    monkeypatch.setattr('app.store.cached',lambda key:None)
    state=fixture();state['ROOT_QUERY']['detail']['ownerImages']=[{'origin':'https://ldb-phinf.pstatic.net/business.jpg'}]
    def handle(request):
        assert request.url.host=='m.place.naver.com'
        assert request.url.params['type']=='business'
        return httpx.Response(200,text='window.__APOLLO_STATE__ = '+json.dumps(state))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        rows=owner_page_photos(client,'123',PLACE)
        assert len(rows)==1 and rows[0]['owner_verified']
        assert owner_page_photos(client,'456',PLACE)==[]


def test_business_tab_rate_limit_respected_without_retry(monkeypatch):
    import httpx
    from app.public_place_photos import owner_page_photos
    cached={};calls=[]
    monkeypatch.setattr('app.store.cached',lambda key:cached.get(key))
    monkeypatch.setattr('app.store.cache',lambda key,value,ttl:cached.update({key:value,'ttl':ttl}))
    def handle(request):
        calls.append(request)
        return httpx.Response(429,headers={'Retry-After':'120'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert owner_page_photos(client,'123',PLACE)==[]
        assert owner_page_photos(client,'123',PLACE)==[]
    assert len(calls)==1 and cached['ttl']==120


def test_venue_title_without_local_photo_description_is_rejected():
    place=PLACE|{'name':'클라이밍 파크 종로점','category':'레저·활동'}
    html='''<div class="se-main-container">
      <div class="se-component"><img src="https://blogfiles.pstatic.net/one.jpg"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/two.jpg"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/food.jpg" alt="점심 맛집"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/other.jpg" alt="강남점 내부"></div>
    </div>'''
    rows=extract_blog_images(html,place,'클라이밍 파크 종로점 방문 후기')
    assert rows==[]
    assert not extract_blog_images(html,place,'종로 데이트 코스 클라이밍 파크 종로점')


def test_review_only_lookup_never_retries_business_provider(monkeypatch):
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *args:(_ for _ in ()).throw(AssertionError('must bypass broken business images')))
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *args:{'photos':[{'id':'review-photo'}],'status':'available'})
    result=media_info(PLACE,review_only=True)
    assert [p['id'] for p in result['photos']]==['review-photo']
    assert result['photo_source']=='matched_review_photos'


def test_review_only_api_query_is_accepted_and_skips_owner(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *args:(_ for _ in ()).throw(AssertionError('review-only API must skip owner')))
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *args:{'photos':[{'id':'review-api-photo'}],'status':'available'})
    with TestClient(app) as client:
        result=client.get('/api/places/Q482485/media?mode=real&fallback=reviews')
        assert result.status_code==200
        assert result.json()['photos'][0]['id']=='review-api-photo'


@pytest.fixture(autouse=True)
def approved_visual_service(monkeypatch):
    monkeypatch.setattr('app.photo_relevance.classify',lambda *args:{'status':'approved','category':'interior','confidence':0.99})


def test_previous_venue_name_cannot_override_wrong_branch_caption():
    place=PLACE|{'name':'클라이밍 파크 종로점','category':'레저·활동'}
    html='''<div class="se-main-container"><div class="se-component">클라이밍 파크 종로점 내부</div><div class="se-component"><img src="https://blogfiles.pstatic.net/wrong.jpg" alt="강남점 내부"></div></div>'''
    assert extract_blog_images(html,place)==[]


def test_facility_description_in_exact_venue_review_is_candidate_not_blank_images():
    place=PLACE|{'name':'클라이밍파크 종로점','category':'레저·활동'}
    html='''<div class="se-main-container">
      <div class="se-component">내부 클라이밍 벽과 홀드</div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/interior.jpg"></div>
      <div class="se-component"><img src="https://blogfiles.pstatic.net/unknown.jpg"></div>
    </div>'''
    assert len(extract_blog_images(html,place,'클라이밍파크 종로점 방문 후기'))==1
    assert not extract_blog_images(html,place,'종로 데이트 코스 클라이밍파크 종로점')


def test_brand_branch_photo_terms_tolerate_generic_type_word_only():
    from app.blog_photos import photo_search_place
    from app.image_search import title_matches
    place=photo_search_place({'name':'오설록 티하우스 북촌점'})
    assert title_matches(place,'오설록 북촌 방문 후기',[])
    assert not title_matches(place,'오설록 제주점 방문 후기',[])
