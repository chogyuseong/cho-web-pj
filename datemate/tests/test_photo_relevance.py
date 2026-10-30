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


def test_missing_or_failed_visual_service_never_approves_review(monkeypatch,visual_service):
    monkeypatch.delenv('GMS_KEY')
    assert not filter_photos(PLACE,[PHOTO])
    owned=PHOTO|{'owner_verified':True}
    assert filter_photos(PLACE,[owned])[0]['visual_verification']['status']=='unverified'


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
