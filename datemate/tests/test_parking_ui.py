"""자동차로 도착하는 장소 아래 근처 주차장: 실제 브라우저, 로컬 서버. 주차장 응답은 가짜."""
from test_functional_audit import audit_page, generate  # noqa: F401

REAL = "selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';p.places.forEach(x=>x.demo=false)});renderResults();renderDetail()"
SNAPSHOT = 'JSON.stringify([selected.total,selected.finish,selected.places.map(p=>p.id),selected.timeline])'


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def car_leg(page, index):
    original = page.evaluate('selected.id')
    page.locator('#plan-detail .route-line').nth(index).locator('.route-mode-toggle').click()
    page.locator('#transport-chooser-%d' % index).get_by_role('button', name='자동차', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    return original


def lots_for(place):
    return [
        dict(id='parking:naver-a', name='삼청 공영주차장', category='교통,수송>주차장', address='서울특별시 종로구 삼청로 9',
             lat=place['lat'] + 0.001, lon=place['lon'], distance_m=320, walk_minutes=7, public_by_name=True),
        dict(id='parking:naver-b', name='한옥마을 주차장', category='교통,수송>주차장', address='서울특별시 종로구 북촌로 3',
             lat=place['lat'], lon=place['lon'] + 0.001, distance_m=90, walk_minutes=2, public_by_name=False),
    ]


def test_parking_panel_under_the_car_stop_map_and_walk_back(audit_page):
    page, base, errors = audit_page
    generate(page)
    index = 1
    original = car_leg(page, index)
    plan = page.evaluate('({id:selected.id,place:selected.places[%d],modes:selected.legs.map(l=>l.mode)})' % index)
    assert plan['modes'][index] == 'car' and plan['modes'].count('car') == 1
    place = plan['place']
    body = dict(status='available', note='주차 시간·요금은 일정과 비용에 포함하지 않았어요.', source_type='네이버 지역 검색', message='',
                stops=[dict(index=index, place_id=place['id'], place_name=place['name'], status='available', message='',
                            lots=lots_for(place))],
                diagnostics=dict(queries=2, lookups=2, cache_hit=False, received=2, rejected={}))
    requests = []

    def handle(route):
        requests.append(route.request.url)
        if len(requests) == 1:
            return route.fulfill(status=503, json={'detail': '점검용 중단'})
        return route.fulfill(json=body)

    page.route('**/api/plans/*/parking', handle)
    page.evaluate(REAL)
    snapshot = page.evaluate(SNAPSHOT)
    panels = page.locator('#plan-detail .parking-panel')
    assert panels.count() == 1
    # 자동차로 도착한 2번 장소 카드 바로 뒤, 주변 식당 앞.
    assert page.evaluate("""()=>{const p=document.querySelector('#plan-detail .parking-panel');
      const stops=[...document.querySelectorAll('#plan-detail .detail > .stop')];
      return p.previousElementSibling===stops[%d]&&p.nextElementSibling.classList.contains('meal-suggestions')}""" % index)
    panel = panels.first
    assert panel.locator('h4').inner_text() == f"{index + 1}번 · {place['name']} 근처 주차장"
    panel.scroll_into_view_if_needed()
    retry = panel.get_by_role('button', name='다시 찾기')
    retry.wait_for()
    assert '주차장 검색에 연결하지 못했어요.' in panel.inner_text()
    retry.click()
    page.wait_for_function("document.querySelectorAll('#plan-detail .parking-lot').length===2")
    assert len(requests) == 2 and all(f"/api/plans/{plan['id']}/parking" in url for url in requests)
    first, second = panel.locator('.parking-lot').all()
    text = first.inner_text()
    assert '삼청 공영주차장' in text and '공영(이름 기준)' in text
    assert '직선 320m · 걸어서 약 7분(추정)' in text and '서울특별시 종로구 삼청로 9' in text
    assert '요금·운영시간·만차 여부 미확인' in text
    assert '공영(이름 기준)' not in second.inner_text()
    anchor = first.locator('a')
    assert anchor.inner_text().endswith('↗') and anchor.get_attribute('href').startswith('https://map.naver.com/')
    assert anchor.get_attribute('target') == '_blank'
    assert panel.locator('.parking-note').inner_text() == '주차 시간·요금은 일정과 비용에 포함하지 않았어요. 출처: 네이버 지역 검색'
    # 지도(키가 없어 공개 대체 지도)에 같은 응답으로 P 표시 2개, 지도 아래 설명. 지도는 따로 요청하지 않는다.
    page.wait_for_function("document.querySelectorAll('.plan-map .parking-marker').length===2")
    assert page.locator('.plan-map .parking-marker').first.inner_text() == 'P'
    assert page.locator('.map-parking-note').inner_text() == 'P: 주차장 2곳(일정 미포함)'
    assert len(requests) == 2
    # 일정·비용은 그대로다(주차 시간·요금 미포함).
    assert page.evaluate(SNAPSHOT) == snapshot
    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        panel.scroll_into_view_if_needed()
        assert no_overflow(page), width
        short = panel.locator('a, button').evaluate_all(
            'els=>els.filter(el=>el.getClientRects().length&&el.getBoundingClientRect().height<43.5).map(el=>el.textContent)')
        assert not short, (width, short)
        small = panel.evaluate(
            "p=>[...p.querySelectorAll('*')].filter(el=>el.childNodes.length&&[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))"
            ".filter(el=>parseFloat(getComputedStyle(el).fontSize)<14).map(el=>el.textContent)")
        assert not small, (width, small)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    # 도보로 되돌리면 패널과 지도 P 표시가 사라진다.
    page.get_by_role('button', name='수단 변경 되돌리기', exact=True).click()
    page.wait_for_function('(id)=>selected.id===id', arg=original)
    page.evaluate(REAL)
    assert page.evaluate('selected.legs.every(l=>l.mode==="walk")')
    assert page.locator('.parking-panel').count() == 0
    assert page.locator('.plan-map .parking-marker').count() == 0
    assert page.locator('.map-parking-note').is_hidden()
    assert len(requests) == 2


def test_not_found_and_demo_course(audit_page):
    page, base, errors = audit_page
    generate(page)
    # 가상 장소 데모에서는 자동차 구간이 있어도 패널을 그리지 않는다.
    car_leg(page, 0)
    assert page.locator('.parking-panel').count() == 0
    place = page.evaluate('selected.places[0]')
    page.route('**/api/plans/*/parking', lambda route: route.fulfill(json=dict(
        status='not_found', note='', source_type='네이버 지역 검색', message='', diagnostics={},
        stops=[dict(index=0, place_id=place['id'], place_name=place['name'], status='not_found',
                    message='이 장소 800m 안에서 주차장을 찾지 못했어요.', lots=[])])))
    page.evaluate(REAL)
    panel = page.locator('#plan-detail .parking-panel')
    panel.scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#plan-detail .parking-panel a')")
    assert '이 장소 800m 안에서 주차장을 찾지 못했어요.' in panel.inner_text()
    anchor = panel.locator('a')
    assert anchor.inner_text() == f"지도에서 '{place['name']} 주차장' 찾기 ↗"
    assert anchor.get_attribute('href').startswith('https://map.naver.com/p/search/')
    assert page.locator('.plan-map .parking-marker').count() == 0
