import copy
from fastapi.testclient import TestClient
from app.main import app
from app.catalog import get_place
from app.media import photos_for,media_info,validated_photo

def test_verified_photo_identity_and_attribution():
    photos=photos_for(get_place('Q482485','real'))
    assert len(photos)>=1
    assert all(p['author'] and p['license_url'] and p['source'] and p['association'] for p in photos)
    assert all(validated_photo(p) for p in photos)
    assert 'Geunjeongjeon' in photos[0]['source']

def test_demo_never_receives_real_place_photo():
    p=copy.deepcopy(get_place('demo-01','demo'));p['id']='Q482485'
    assert not photos_for(p)
    assert media_info(p)['status']=='demo'

def test_unverified_links_and_missing_license_rejected():
    photo=photos_for(get_place('Q482485','real'))[0]
    for patch in [{'url':'http://127.0.0.1/private'},{'url':'javascript:alert(1)'},{'source':'https://fake.example/photo'},
                  {'license':''},{'author':''},{'license':'CC BY fake'},{'url':photo['url']+'?redirect=1'}]:
        assert not validated_photo(photo|patch)

def test_photo_api_and_unknown_empty_states():
    with TestClient(app) as client:
        r=client.get('/api/places/Q482485/media?mode=real')
        assert r.status_code==200
        data=r.json();assert data['photos'] and data['wikidata_id']=='Q482485'
        assert data['photos'][0]['image_url'].startswith('https://upload.wikimedia.org/')
        assert client.get('/api/places/demo-01/media?mode=demo').json()['photos']==[]
        assert client.get('/api/places/not-found/media?mode=real').status_code==404
        assert media_info({'id':'Q111111111','demo':False})['photos']==[]
        assert media_info({'id':'custom:invalid','demo':False})['wikidata_id'] is None
