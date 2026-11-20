"""사진 칸 정렬 캡처(390px·1280px): 코스 미리보기 3칸, 일정 카드, 식당 카드, 둘러보기 카드, 장소 정보 창의 사진 있음·없음·연결 실패.

외부 호출 없음(/media·블로그·사진은 가짜 응답). PHOTO_CAPTURE_OUT 폴더에 PNG 와 measurements.json 을 남긴다. 이름이 test_*.py 가 아니라
일반 pytest 실행에는 수집되지 않는다(tests/css_snapshot.py 와 같은 방식). datemate 폴더에서:
    PHOTO_CAPTURE_OUT=runtime/photo-layout python -m pytest tests/photo_layout_capture.py -q   (Docker 는 DATEMATE_BROWSER_CHANNEL=chromium)
2026-11-20 전/후 캡처는 docs/screenshots/photo-layout-2026-11-20/ 에 있다(전 = main 0410365 의 static 에 이 파일만 끼워 찍음)."""
import json
import os
from pathlib import Path

import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401
from test_results_extras_ui import wide_png

OUT = Path(os.getenv('PHOTO_CAPTURE_OUT', '/out'))
NAMES = ['제주카약올레', '놀맨', '한담해변']
ADDRESS = '제주특별자치도 제주시 애월읍 애월로1길 26-4'
NO_PHOTO = '등록 사진이나 한국관광공사 사진이 없는 곳이에요. 네이버 검색 결과에서 사진을 골라 쓰지 않아요. 네이버 지도에서 사진을 확인해 주세요.'
FAILED = '한국관광공사 사진 자료에 지금 연결하지 못했어요. 잠시 뒤 다시 불러오거나 네이버 지도에서 사진을 확인해 주세요.'
MAP_URL = 'https://map.naver.com/p/search/x'
FOOD = {'id': 'meal-capture', 'name': '고이정', 'cuisine': '관광식당', 'address': '제주특별자치도 제주시 애월읍 애월로 6', 'lat': 33.46, 'lon': 126.31}
FOOD2 = dict(FOOD, id='meal-capture-none', name='사진 없는 식당')


def tour_photo(base, name, index=0):
    url = f'{base}/cap-{index}.png'
    return {'id': f'tourapi-{name}-{index}', 'kind': 'tourapi', 'title': name + ' 장소 사진', 'image_url': url, 'url': url,
            'source': 'https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=1', 'author': '한국관광공사',
            'license': '공공누리 제3유형(변경 금지)', 'license_url': 'https://www.kogl.or.kr/info/licenseType3.do',
            'caption': '한국관광공사 제공 사진 · 공공누리 제3유형(변경 금지) · 한국관광공사 관광정보 항목의 사진이에요.',
            'source_label': '한국관광공사 제공 사진 · 공공누리 제3유형(변경 금지)', 'checked_at': '2026-11-20', 'image_role': '장소 연결 사진'}


def mount(page, base, state):
    png = wide_png(800, 600)
    page.route('**/cap-*.png', lambda route: route.fulfill(body=png, content_type='image/png'))

    def media(route):
        url = route.request.url
        if 'fallback=reviews' in url:
            return route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL})
        pid = url.split('/api/places/')[1].split('/media')[0]
        kind = state['kinds'].get(pid, state['default'])
        if kind == 'none':
            return route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL, 'message': NO_PHOTO, 'photo_retry': False})
        if kind == 'failed':
            return route.fulfill(json={'photos': [], 'status': 'not_found', 'map_url': MAP_URL, 'message': FAILED, 'photo_retry': True})
        if kind == 'error':
            return route.fulfill(status=500, json={'detail': 'x'})
        count = 5 if kind == 'many' else 1
        route.fulfill(json={'photos': [tour_photo(base, pid, i) for i in range(count)], 'status': 'available', 'map_url': MAP_URL, 'photo_retry': False})

    page.route('**/api/places/*/media?*', media)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    page.route('**/api/places/*/menu?*', lambda route: route.fulfill(json={'status': 'not_found', 'items': [], 'reason': 'not_collected',
                                                                          'message': '이 식당의 메뉴·가격 자료는 모아 두지 않았어요. 네이버 지도에서 확인해 주세요.',
                                                                          'source_kind': 'map_link', 'source_url': MAP_URL}))


def settle(page):
    page.evaluate("""async()=>{const frames=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      for(let y=0;y<document.documentElement.scrollHeight;y+=600){scrollTo({top:y,behavior:'instant'});await frames();await new Promise(r=>setTimeout(r,120));}
      scrollTo({top:0,behavior:'instant'});await frames();}""")
    page.wait_for_timeout(1200)


def shot(page, selector, name, nth=0):
    target = page.locator(selector).nth(nth)
    target.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    target.screenshot(path=str(OUT / (name + '.png')))


MEASURE = """()=>{const box=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {left:Math.round(r.left*10)/10,right:Math.round(r.right*10)/10,top:Math.round((r.top+scrollY)*10)/10,bottom:Math.round((r.bottom+scrollY)*10)/10,width:Math.round(r.width*10)/10};};
  const preview=document.querySelector('.plan-card.selected .plan-photo-preview')||document.querySelector('.plan-photo-preview');
  const items=preview?[...preview.querySelectorAll('.plan-photo-item')].map(item=>({panel:box(item.querySelector('.place-photo-panel')),caption:box(item.querySelector('figcaption')),
    captionPad:item.querySelector('figcaption')?getComputedStyle(item.querySelector('figcaption')).paddingLeft:null,
    licenseRects:item.querySelector('.photo-license')?item.querySelector('.photo-license').getClientRects().length:null,
    fold:box(item.querySelector('.photo-copy-fold>summary')),status:box(item.querySelector('.photo-status')),map:box(item.querySelector('.photo-map-link')),
    retry:box(item.querySelector('.photo-retry')),blog:box(item.querySelector('.place-blogs'))})):[];
  const stops=[...document.querySelectorAll('#plan-detail .place-photo-panel')].map(panel=>({panel:box(panel),caption:box(panel.querySelector('figcaption')),
    status:box(panel.querySelector('.photo-status')),map:box(panel.querySelector('.photo-map-link')),retry:box(panel.querySelector('.photo-retry')),card:box(panel.querySelector('.photo-empty-card'))}));
  return {items,stops,overflow:document.documentElement.scrollWidth>innerWidth};}"""


def test_capture(audit_page):
    if not os.getenv('PHOTO_CAPTURE_OUT'):
        pytest.skip('capture only')
    page, base, errors = audit_page
    OUT.mkdir(parents=True, exist_ok=True)
    measures = {}
    for width in (390, 1280):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base, wait_until='networkidle')
        page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
        state = {'kinds': {}, 'default': 'one'}
        mount(page, base, state)
        generate(page)
        ids = page.evaluate("selected.places.map(p=>p.id)")
        for variant, third in (('none', 'none'), ('failed', 'failed')):
            state['kinds'] = {ids[0]: 'one', ids[1]: 'one', ids[2]: third}
            page.evaluate("""([names,address])=>{selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';p.places.forEach((x,i)=>{x.demo=false;if(names[i]){x.name=names[i];x.address=address;x.category=i===2?'산책·풍경':x.category;}})});
              placePhotoRequests.clear();renderResults();renderDetail();}""", [NAMES, ADDRESS])
            wait_for_selected_detail(page)
            page.evaluate("document.querySelectorAll('details.plan-photo-details').forEach(d=>d.open=true)")
            settle(page)
            page.wait_for_function("document.querySelectorAll('.plan-card.selected .plan-photo-preview .photo-map-link').length>=1")
            page.wait_for_timeout(800)
            shot(page, '.plan-card.selected .plan-photo-details', f'{width}-preview-{variant}')
            measures[f'{width}-{variant}'] = page.evaluate(MEASURE)
            stops = page.locator('#plan-detail .place-photo-panel')
            for index in range(min(3, stops.count())):
                target = stops.nth(index)
                target.scroll_into_view_if_needed()
                page.wait_for_timeout(700)
            measures[f'{width}-{variant}-stops'] = page.evaluate(MEASURE)['stops']
            shot(page, '#plan-detail .place-photo-panel', f'{width}-stop-photo-{variant}', 0)
            shot(page, '#plan-detail .place-photo-panel', f'{width}-stop-third-{variant}', 2)
        # 식당 카드(사진 있음·없음)
        state['kinds'] = {FOOD['id']: 'one', FOOD2['id']: 'none'}
        page.evaluate("""foods=>{document.getElementById('cap-meals')?.remove();const holder=document.createElement('section');holder.id='cap-meals';holder.className='meal-suggestions';
          for(const food of foods)holder.append(restaurantCard(food,{badge:'2-3 · 지도 표시'}));document.querySelector('main').prepend(holder);holder.scrollIntoView({block:'start',behavior:'instant'});}""", [FOOD, FOOD2])
        for index in range(2):
            page.locator('#cap-meals .meal-photo').nth(index).scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        page.wait_for_function("document.querySelector('#cap-meals .meal-photo img')?.naturalWidth>0&&document.querySelector('#cap-meals .photo-map-link')")
        page.wait_for_timeout(600)
        shot(page, '#cap-meals .meal-card-with-photo', f'{width}-meal-photo', 0)
        shot(page, '#cap-meals .meal-card-with-photo', f'{width}-meal-none', 1)
        measures[f'{width}-meal'] = page.evaluate("""()=>[...document.querySelectorAll('#cap-meals .meal-photo')].map(m=>{const b=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {left:Math.round(r.left*10)/10,right:Math.round(r.right*10)/10,width:Math.round(r.width*10)/10};};
          return {photo:b(m),caption:b(m.querySelector('figcaption')),captionPad:m.querySelector('figcaption')?getComputedStyle(m.querySelector('figcaption')).paddingLeft:null,fold:b(m.querySelector('.photo-copy-fold>summary')),
            status:b(m.querySelector('.photo-status')),map:b(m.querySelector('.photo-map-link')),retry:b(m.querySelector('.photo-retry')),
            licenseRects:m.querySelector('.photo-license')?m.querySelector('.photo-license').getClientRects().length:null};})""")
        page.evaluate("document.getElementById('cap-meals')?.remove()")
        # 둘러보기 카드(사진 있음·없음·연결 실패)
        state['kinds'] = {'ex-1': 'one', 'ex-2': 'none', 'ex-3': 'failed', 'ex-4': 'many'}
        page.route('**/api/explore?*', lambda route: route.fulfill(json={
            'places': [{'id': f'ex-{i}', 'name': name, 'category': '산책·풍경', 'address': ADDRESS, 'region': '제주'}
                       for i, name in enumerate(['애월한담공원', '한담해변', '곽지해수욕장', '한담해안산책로'], 1)],
            'total': 4, 'has_more': False, 'region': '제주', 'activity': '', 'message': ''}))
        page.route('**/api/explore/naver?*', lambda route: route.fulfill(json={'status': 'empty', 'blocks': [], 'message': ''}))
        page.get_by_role('button', name='장소 둘러보기', exact=True).click()
        page.locator('#catalog .place-card').first.wait_for()
        page.wait_for_function("document.querySelectorAll('#catalog .photo-map-link').length>=2&&[...document.querySelectorAll('#catalog .place-photo img')].some(i=>!i.hidden&&i.naturalWidth>0)")
        page.wait_for_timeout(600)
        shot(page, '#catalog', f'{width}-explore')
        # 장소 정보 창(사진 5장, 사진 없음)
        for pid, label in (('ex-4', 'many'), ('ex-2', 'none')):
            page.route(f'**/api/places/{pid}?*', lambda route: route.fulfill(json={
                'id': route.request.url.split('/api/places/')[1].split('?')[0],'name': '한담해변', 'category': '산책·풍경', 'address': ADDRESS, 'region': '제주', 'lat': 33.46, 'lon': 126.31,
                'description': '', 'photos': [], 'videos': [], 'tags': [], 'themes': ['산책·풍경'], 'source': 'https://example.org', 'source_type': 'fixture',
                'checked_at': '2026-11-20', 'license': 'test', 'price': None, 'hours': None, 'closed_days': None, 'stay': None,
                'stay_basis': None, 'reservation': None, 'rating': None, 'demo': False, 'meal': False}))
            try:
                page.evaluate("id=>showPlace(id,'real')", pid)
                page.wait_for_function("document.querySelector('#dialog').open&&(document.querySelector('#dialog .photo-map-link')||[...document.querySelectorAll('#dialog .place-photo img')].some(i=>!i.hidden&&i.naturalWidth>0))", timeout=15000)
                page.wait_for_timeout(800)
                page.screenshot(path=str(OUT / f'{width}-dialog-{label}.png'))
                page.evaluate("document.querySelector('#dialog').close()")
            except Exception as error:  # 창 장면은 덤이다. 못 열어도 나머지 캡처는 남긴다.
                measures[f'{width}-dialog-{label}-error'] = str(error)[:300]
    (OUT / 'measurements.json').write_text(json.dumps(measures, ensure_ascii=False, indent=1), encoding='utf-8')
    assert not errors, errors
