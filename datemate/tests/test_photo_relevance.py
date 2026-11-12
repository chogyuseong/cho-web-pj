"""Content inspection is an exclusion filter, never a business identity verifier."""
import pytest
from app.photo_relevance import classify,filter_photos,Verdict

PLACE={'id':'gym','name':'종로 클라이밍','category':'레저·활동'}
PHOTO={'source_type':'blog_review','image_url':'https://blogfiles.pstatic.net/subject.jpg','caption':'종로 클라이밍 내부'}


@pytest.fixture
def visual_service(monkeypatch):
    cache={};calls=[]
    monkeypatch.setenv('GMS_KEY','test-secret')
    monkeypatch.setenv('PHOTO_VISUAL_CHECK','true')
    monkeypatch.setattr('app.store.cached',lambda key:cache.get(key))
    monkeypatch.setattr('app.store.cache',lambda key,value,ttl:cache.update({key:value}))
    class Model:
        def with_structured_output(self,schema):return self
    monkeypatch.setattr('app.config.llm',lambda **kwargs:Model())
    def answer(value):
        def invoke(model,messages):calls.append(messages);return value
        monkeypatch.setattr('app.photo_relevance.invoke_model',invoke)
    return answer,calls


@pytest.mark.parametrize('category',['food','portrait','receipt','map','advertisement','document','logo','unrelated','unknown'])
def test_unrelated_visual_content_rejected_even_with_matching_caption(visual_service,category):
    answer,calls=visual_service
    answer(Verdict(relevant=True,category=category,confidence=1))
    assert filter_photos(PLACE,[PHOTO])==[]
    assert len(calls)==1


def test_matching_space_approved_and_cached(visual_service):
    answer,calls=visual_service
    answer(Verdict(relevant=True,category='interior',confidence=.96))
    assert filter_photos(PLACE,[PHOTO])[0]['visual_verification']['status']=='approved'
    assert classify(PLACE,PHOTO)['status']=='approved' and len(calls)==1


def test_low_confidence_not_promoted(visual_service):
    answer,calls=visual_service;answer(Verdict(relevant=True,category='activity',confidence=.79))
    assert not filter_photos(PLACE,[PHOTO])


def test_food_only_allowed_for_dining_venue(visual_service):
    answer,calls=visual_service;answer(Verdict(relevant=True,category='food',confidence=.98))
    assert filter_photos(PLACE|{'id':'restaurant','category':'카페·미식'},[PHOTO])


@pytest.mark.parametrize('setting',[{'GMS_KEY':''},{'PHOTO_VISUAL_CHECK':'false'}])
def test_without_visual_checker_place_matched_photos_shown_as_unchecked(monkeypatch,visual_service,setting):
    answer,calls=visual_service
    for name,value in setting.items():monkeypatch.setenv(name,value)
    rows=filter_photos(PLACE,[PHOTO])
    assert len(rows)==1 and rows[0]['visual_verification']=={'status':'unverified','reason':'visual_check_unavailable'}
    assert not calls
    # Existing count limits still apply: at most five candidates, stop after two results.
    many=[PHOTO|{'id':str(i),'image_url':f'https://blogfiles.pstatic.net/{i}.jpg'} for i in range(6)]
    assert [row['id'] for row in filter_photos(PLACE,many)]==['0','1']


def test_failed_visual_service_never_approves_review(monkeypatch,visual_service):
    monkeypatch.setattr('app.photo_relevance.invoke_model',lambda *args:(_ for _ in ()).throw(RuntimeError('provider down')))
    assert not filter_photos(PLACE,[PHOTO])
    owned=PHOTO|{'owner_verified':True,'image_url':'https://ldb-phinf.pstatic.net/owner.jpg'}
    rows=filter_photos(PLACE,[owned])
    assert rows[0]['visual_verification']['status']=='unverified' and 'reason' not in rows[0]['visual_verification']


def test_model_failure_does_not_leak_secret(visual_service,monkeypatch):
    monkeypatch.setattr('app.photo_relevance.invoke_model',lambda *args:(_ for _ in ()).throw(RuntimeError('test-secret')))
    result=classify(PLACE,PHOTO)
    assert result=={'status':'unverified'} and 'test-secret' not in str(result)


def test_legitimate_exterior_at_clear_positive_confidence_is_kept(visual_service):
    answer,calls=visual_service;answer(Verdict(relevant=True,category='exterior',confidence=.86))
    assert filter_photos(PLACE,[PHOTO])


def test_concurrent_venues_wait_instead_of_losing_all_their_photos(visual_service,monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    def respond(*args):
        time.sleep(.05)
        return Verdict(relevant=True,category='interior',confidence=.96)
    monkeypatch.setattr('app.photo_relevance.invoke_model',respond)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda i:filter_photos(PLACE|{'id':'parallel-'+str(i)},[PHOTO]),range(4)))
    assert all(len(rows)==1 for rows in results)


def test_early_rejections_do_not_hide_later_valid_photos(monkeypatch):
    photos=[{'id':str(i)} for i in range(5)]
    monkeypatch.setattr('app.photo_relevance.classify',lambda place,photo:{'status':'approved' if int(photo['id'])>=3 else 'rejected'})
    assert [photo['id'] for photo in filter_photos(PLACE,photos)]==['3','4']


def test_area_words_and_queries_never_assume_seoul():
    from app.public_place_photos import area_words
    from app.search_address_text import street_address
    assert area_words({'address':'제주특별자치도 제주시 애월읍'})=='제주 제주시'
    assert area_words({'address':'강원특별자치도 강릉시 창해로'})=='강원 강릉시'
    assert area_words({'region':'부산','address':'부산광역시 해운대구 우동'})=='부산 해운대구'
    assert area_words({'address':'서울특별시 중구 세종대로'})=='서울 중구'
    assert '서울' not in area_words({'address':'경상남도 통영시'})
    assert street_address('강원특별자치도 강릉시')=='강원특별자치도 강릉시'
    assert street_address('미확인 주소')==''


def test_public_photo_queries_use_place_region(monkeypatch):
    import app.public_place_photos as module
    queries=[]
    monkeypatch.setattr(module.store,'cached',lambda key:None)
    monkeypatch.setattr(module.store,'cache',lambda *args:None)
    monkeypatch.setattr(module,'fetch_page',lambda client,query:queries.append(query) or '')
    place={'name':'바다카페','address':'제주특별자치도 제주시 애월읍','region':'제주','lat':33.46,'lon':126.31}
    module.public_place_photos(place,force=True)
    assert queries and all('서울' not in query for query in queries)
    assert '바다카페 제주 제주시' in queries


def test_detail_identity_requires_place_region_not_seoul():
    from app.menus import identified
    base={'name':'바다카페','id':'7','coordinate':{'x':'126.31','y':'33.46'},'roadAddress':'제주특별자치도 제주시 애월읍 1'}
    place={'name':'바다카페','lat':33.46,'lon':126.31,'region':'제주'}
    assert identified(base,place)
    assert not identified(base,place|{'region':'부산'})
    assert not identified(base|{'roadAddress':'서울 중구 1'},place)
