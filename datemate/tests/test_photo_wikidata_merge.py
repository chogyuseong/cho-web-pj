"""사진이 2장보다 적은 위키데이터 장소는 Wikidata 대표 사진(P18)을 덧붙인다 (2026-11-24 사용자 신고: '가게 사진이 올라가 있는데 못 가져온다').

예전: 관광공사 사진이 1장이라도 있으면 Wikidata 사진을 찾지 않았다(app/media.py only_registry, static/wikimedia-photos.js photos.length).
지금: 서버는 사진이 2장 미만이면 wikidata_id 를 주고, 화면은 이미 있는 사진 뒤에 P18 사진을 덧붙인다(같은 사진은 한 번만).
외부 API 는 부르지 않는다(가로채 흉내 낸다).
"""
from test_functional_audit import audit_page  # noqa: F401  (fixture)

CLAIMS = {'claims': {'P18': [{'rank': 'normal', 'mainsnak': {'datavalue': {'value': 'Gallery.jpg'}}}]}}
PAGES = {'query': {'pages': {'7': {'pageid': 7, 'imageinfo': [{
    'mime': 'image/jpeg', 'url': 'https://upload.wikimedia.org/a/Gallery.jpg', 'thumburl': 'https://upload.wikimedia.org/a/1280px-Gallery.jpg',
    'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Gallery.jpg',
    'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}, 'Artist': {'value': '찍은 사람'},
                    'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0'}}}]}}}}


def mock_wikimedia(page, calls):
    def wikidata(route):
        calls.append('wikidata')
        route.fulfill(json=CLAIMS, headers={'access-control-allow-origin': '*'})

    def commons(route):
        calls.append('commons')
        route.fulfill(json=PAGES, headers={'access-control-allow-origin': '*'})
    page.route('https://www.wikidata.org/**', wikidata)
    page.route('https://commons.wikimedia.org/**', commons)


DISCOVER = """async (photos)=>{
  try{localStorage.clear();}catch{}
  const data={wikidata_id:'Q123',status:photos.length?'available':'not_found',photos:photos.map((u,i)=>({id:'t'+i,image_url:u}))};
  const got=await discoverPlacePhotos({id:'Q123',name:'어느 미술관'},data);
  return got.photos.map(p=>p.image_url);
}"""


def test_one_tour_photo_gets_the_wikidata_photo_after_it(audit_page):  # noqa: F811
    page, _, _ = audit_page
    calls = []
    mock_wikimedia(page, calls)
    got = page.evaluate(f"({DISCOVER})(['https://tong.visitkorea.or.kr/a.jpg'])")
    assert got == ['https://tong.visitkorea.or.kr/a.jpg', 'https://upload.wikimedia.org/a/1280px-Gallery.jpg']
    assert calls == ['wikidata', 'commons']


def test_two_photos_do_not_ask_and_no_photo_still_works(audit_page):  # noqa: F811
    page, _, _ = audit_page
    calls = []
    mock_wikimedia(page, calls)
    two = page.evaluate(f"({DISCOVER})(['https://x/a.jpg','https://x/b.jpg'])")
    assert two == ['https://x/a.jpg', 'https://x/b.jpg'] and calls == []
    none = page.evaluate(f"({DISCOVER})([])")
    assert none == ['https://upload.wikimedia.org/a/1280px-Gallery.jpg']


def test_media_gives_the_wikidata_id_when_photos_are_few(monkeypatch):
    from fastapi.testclient import TestClient
    from app import media, tour_places
    from app.main import app
    one = dict(status='available', photos=[dict(id='tour-1', kind='official_public', image_url='https://tong.visitkorea.or.kr/a.jpg',
                                                url='https://tong.visitkorea.or.kr/a.jpg', source='https://korean.visitkorea.or.kr/x',
                                                license='공공누리 제1유형', title='사진')])
    monkeypatch.setattr(tour_places, 'tour_photo_result', lambda place, force=False: one)
    place = dict(id='Q4999999', name='위키 미술관', category='전시', region='서울', lat=37.5, lon=127.0, address='서울 종로구 어딘가로 1')
    result = media.media_info(place, prefer_public=True)
    assert len(result['photos']) == 1 and result['wikidata_id'] == 'Q4999999'
    # 위키데이터 번호가 아닌 장소는 그대로 None.
    assert media.media_info(dict(place, id='public:tour-1'), prefer_public=True)['wikidata_id'] is None
