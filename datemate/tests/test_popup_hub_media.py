"""팝업 거점 사진 (2026-11-24, app/popup_hub_media.py · static/popups.js hubMedia).

관광공사 항목으로 좌표를 확인한 거점(entity)만 그 항목의 공공누리 사진 한 장. 입점 매장 주소로 잡은 거점(tenants)은 없음.
화면은 '거점 사진이지 팝업 사진이 아니다'와 출처·이용조건을 함께 적고, 사진이 없으면 자리를 지운다. 외부 API 는 부르지 않는다."""
from fastapi.testclient import TestClient

from app import tour_places
from app.main import app
from app.popup_hub_media import hub_content_id
from app.popup_hubs import HUBS
from test_functional_audit import audit_page  # noqa: F401  (fixture)

PHOTO = dict(id='tourapi-2708109', kind='tourapi', image_url='https://tong.visitkorea.or.kr/cms/a.jpg', url='https://tong.visitkorea.or.kr/cms/a.jpg',
             source='https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=2708109', author='한국관광공사', license='공공누리 제1유형',
             license_url='https://www.kogl.or.kr/info/licenseType1.do')


def test_only_entity_hubs_have_a_content_id():
    by_id = {h['id']: h for h in HUBS}
    assert hub_content_id(by_id['seoul-thehyundai']) == '2708109'
    assert hub_content_id(by_id['seoul-ipark-mall']) is None


def test_media_route(monkeypatch):
    seen = []

    def fake(place, force=False):
        seen.append(place)
        return dict(status='available', photos=[PHOTO, dict(PHOTO, id='second')])
    monkeypatch.setattr(tour_places, 'tour_photo_result', fake)
    with TestClient(app) as client:
        body = client.get('/api/popups/hubs/seoul-thehyundai/media').json()
        assert body['status'] == 'available' and [p['id'] for p in body['photos']] == ['tourapi-2708109'], '한 장만'
        assert seen[0]['tour_content_id'] == '2708109' and seen[0]['name'] == '더현대 서울'
        assert client.get('/api/popups/hubs/seoul-ipark-mall/media').json() == dict(hub_id='seoul-ipark-mall', status='not_applicable', photos=[])
        assert len(seen) == 1, 'tenants 거점은 관광공사를 부르지 않는다'
        assert client.get('/api/popups/hubs/no-such-hub/media').status_code == 404
        assert client.get('/api/popups/hubs/BAD_ID/media').status_code == 422


def test_hub_block_shows_one_credited_photo_or_nothing(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.route('**/api/popups/hubs/seoul-thehyundai/media', lambda route: route.fulfill(json=dict(status='available', photos=[PHOTO])))
    page.route('**/api/popups/hubs/seoul-ipark-mall/media', lambda route: route.fulfill(json=dict(status='not_applicable', photos=[])))
    page.route('https://tong.visitkorea.or.kr/**', lambda route: route.fulfill(body=b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;', content_type='image/gif'))
    got = page.evaluate("""async ()=>{
      const out=[];
      for(const hub_id of ['seoul-thehyundai','seoul-ipark-mall']){
        const block=PopupCourse.hubBlock({hub:{hub_id,name:hub_id,kind:'building',lat:37.5,lon:127},meters:null},null);
        document.body.append(block);block.scrollIntoView();
        const t=Date.now();
        while(Date.now()-t<5000){const f=block.querySelector('.popup-hub-media');if(!f||f.querySelector('img'))break;await new Promise(r=>setTimeout(r,50));}
        const f=block.querySelector('.popup-hub-media');
        out.push(f?[f.querySelector('img')?.getAttribute('src'),f.querySelector('figcaption')?.textContent,[...f.querySelectorAll('a')].map(a=>a.getAttribute('href'))]:null);
        block.remove();
      }
      return out;
    }""")
    src, caption, links = got[0]
    assert src == PHOTO['image_url']
    assert '거점 사진이에요. 지금 열리는 팝업의 사진은 아니에요.' in caption and '공공누리 제1유형' in caption
    assert links == [PHOTO['license_url'], PHOTO['source']]
    assert got[1] is None, '사진이 없는 거점은 사진 자리를 지운다'
