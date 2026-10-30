import pytest
"""Continue past representative photos while keeping identity and source order."""
import json
from app.public_place_photos import extract_photo_records,public_place_photos
from app.media import media_info
from test_public_place_photos import fixture
from test_photo_source_priority import PLACE


def test_single_representative_does_not_stop_next_query(monkeypatch):
    from app import public_place_photos as module
    cache={};queries=[]
    monkeypatch.setattr(module.store,'cached',lambda key:cache.get(key))
    monkeypatch.setattr(module.store,'cache',lambda key,value,ttl:cache.update({key:value}))
    def page(client,query):
        queries.append(query);state=fixture()
        if len(queries)>1:state['ROOT_QUERY']['detail']['visitorImages']=[{'origin':'https://ldb-phinf.pstatic.net/second.jpg'}]
        return 'window.__APOLLO_STATE__ = '+json.dumps(state)
    monkeypatch.setattr(module,'fetch_page',page)
    monkeypatch.setattr(module,'owner_page_photos',lambda *args:[])
    data=public_place_photos(PLACE)
    assert len(queries)==2
    assert len(data['photos'])==2
    assert data['naver_place_id']=='123' and data['naver_place_id_verified'] is True
    assert any(photo['source_type']=='place_review' for photo in data['photos'])


def test_thumbnail_and_original_are_one_photo_and_visitor_images_are_read():
    state=fixture();scope=state['ROOT_QUERY']['detail']
    scope['images']={'items':[{'origin':'https://ldb-phinf.pstatic.net/same.jpg?type=w1200','thumbUrl':'https://ldb-phinf.pstatic.net/same.jpg?type=w200'}]}
    scope['visitorImages']=[{'origin':'https://ldb-phinf.pstatic.net/same.jpg?type=w300'},{'origin':'https://ldb-phinf.pstatic.net/second.jpg'}]
    records,pid=extract_photo_records('window.__APOLLO_STATE__ = '+json.dumps(state),PLACE)
    assert pid=='123' and len(records)==2


def test_one_owner_photo_is_supplemented_with_matched_blog(monkeypatch):
    owner={'id':'owner','owner_verified':True,'image_url':'https://ldb-phinf.pstatic.net/owner.jpg'}
    blog={'id':'blog','source_type':'blog_review','image_url':'https://blogfiles.pstatic.net/blog.jpg'}
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setattr('app.media.photos_for',lambda place:[])
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *args:{'photos':[owner]})
    calls=[]
    def fallback(*args):calls.append(True);return {'photos':[blog],'status':'available'}
    monkeypatch.setattr('app.blog_photos.blog_photos',fallback)
    data=media_info(PLACE)
    assert [p['id'] for p in data['photos']]==['owner','blog'] and calls==[True]
    assert data['photo_lookup_incomplete'] is False


def test_do_not_call_one_failed_source_a_place_without_photos(monkeypatch):
    monkeypatch.setattr('app.media.search_enabled',lambda:True)
    monkeypatch.setattr('app.media.photos_for',lambda place:[])
    monkeypatch.setattr('app.public_place_photos.public_place_photos',lambda *args:{'photos':[{'image_url':'https://ldb-phinf.pstatic.net/one.jpg'}]})
    monkeypatch.setattr('app.blog_photos.blog_photos',lambda *args:{'photos':[],'status':'unavailable'})
    result=media_info(PLACE)
    assert result['photo_lookup_incomplete'] is True
    assert '자동으로 확보하지 못했어요' in result['message']


@pytest.fixture(autouse=True)
def approved_visual_service(monkeypatch):
    monkeypatch.setattr('app.photo_relevance.classify',lambda *args:{'status':'approved','category':'interior','confidence':0.99})
