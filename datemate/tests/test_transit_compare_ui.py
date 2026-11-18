"""대중교통 지하철·버스 비교 화면(static/transit-compare.js): 실제 브라우저, 로컬 서버. 비교 응답은 가짜.

데모 코스의 모든 구간을 대중교통으로 바꾼 뒤 실제 장소 모드처럼 다시 그리고(test_parking_ui.REAL), TMAP 키가 있는 것처럼
statusData.transit_compare_available 을 켠다. 지도는 테스트에 네이버 키가 없어 공개 대체 지도(Leaflet)로 그려지므로,
고른 경로는 Leaflet 선의 class(transit-route-*)로 확인한다."""
from test_functional_audit import audit_page, generate  # noqa: F401
from test_parking_ui import REAL, SNAPSHOT, no_overflow

ENABLE = 'statusData.transit_compare_available=true;' + REAL


def to_transit(page):
    original = page.evaluate('selected.id')
    bulk = page.locator('#plan-detail .transport-bulk')
    bulk.locator('summary').click()
    bulk.get_by_role('button', name='대중교통', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)


def option(minutes, walk, transfers, fare, lines, kind, a, b):
    return dict(minutes=minutes, walk_minutes=walk, transfers=transfers, fare_per_person=fare,
                lines=[dict(mode=kind, name=n) for n in lines],
                path=[dict(kind='walk', points=[[a['lon'], a['lat']], [a['lon'] + 0.0005, a['lat']]]),
                      dict(kind=kind, points=[[a['lon'] + 0.0005, a['lat']], [b['lon'], b['lat']]])])


def answer(page):
    """선택된 코스의 대중교통 구간마다: 지하철(빠름) · 버스(덜 걸음, 환승 적음). 첫 구간은 버스만으로 가는 경로가 없음."""
    plan = page.evaluate('({legs:selected.legs.map(l=>({origin:l.origin,destination:l.destination,minutes:l.minutes})),'
                         'points:[selected.conditions.origin,...selected.places,selected.conditions.home]})')
    legs = []
    for i, leg in enumerate(plan['legs']):
        a, b = plan['points'][i], plan['points'][i + 1]
        subway = option(leg['minutes'] - 3, 9, 1, 1550, ['수도권2호선', '수도권분당선'], 'subway', a, b)
        bus = None if i == 0 else option(leg['minutes'] + 4, 3, 0, 1500, ['간선:741'], 'bus', a, b)
        legs.append(dict(index=i, origin=leg['origin'], destination=leg['destination'], estimate_minutes=leg['minutes'], status='available',
                         options=dict(subway=subway, bus=bus, mixed=None),
                         best=dict(fastest='subway', least_walk='subway' if bus is None else 'bus', fewest_transfers='subway' if bus is None else 'bus')))
    return dict(status='available', legs=legs, message='', expires_in=61200, checked_at='2026-11-18 14:00',
                source='TMAP 대중교통 · 조회 시점 기준이며 방문일 시간표·배차 대기·좌석은 보장하지 않아요.')


def test_compare_choose_bus_preview_and_map(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    generate(page)
    to_transit(page)
    # 키가 없으면(기본) 단추도 패널도 없다.
    page.evaluate(REAL)
    assert page.locator('.transit-compare-intro').count() == 0 and page.locator('.transit-compare-panel').count() == 0
    requests = []
    body = answer(page)

    def handle(route):
        requests.append(route.request.url)
        if len(requests) == 1:
            return route.fulfill(status=503, json={'detail': '점검용 중단'})
        return route.fulfill(json=body)

    page.route('**/api/plans/*/transit-compare', handle)
    page.evaluate(ENABLE)
    snapshot = page.evaluate(SNAPSHOT)
    intro = page.locator('#plan-detail .transit-compare-intro')
    start = intro.get_by_role('button', name='지하철·버스 비교하기', exact=True)
    assert 'TMAP(티맵모빌리티)에 보내' in intro.inner_text()
    # 누르기 전에는 요청하지 않고 패널도 보이지 않는다.
    assert requests == [] and page.locator('.transit-compare-panel:visible').count() == 0
    start.click()
    page.wait_for_function("document.querySelector('.transit-compare-status').textContent.includes('연결하지 못했어요')")
    intro.get_by_role('button', name='다시 비교', exact=True).click()
    page.wait_for_function("document.querySelectorAll('#plan-detail .transit-option').length>=3")
    assert len(requests) == 2 and all('/transit-compare' in url for url in requests)
    assert 'TMAP 대중교통 · 조회 시점 기준' in intro.locator('.transit-compare-status').inner_text()
    panels = page.locator('#plan-detail .transit-compare-panel')
    legs = page.evaluate('selected.legs.length')
    assert panels.count() == legs
    # 패널은 그 구간 줄 바로 아래.
    assert page.evaluate("[...document.querySelectorAll('#plan-detail .transit-compare-panel')].every(p=>p.previousElementSibling.classList.contains('route-line-block'))")
    first, second = panels.nth(0), panels.nth(1)
    assert '버스만으로 가는 경로가 없어요.' in first.inner_text()
    cards = second.locator('.transit-option')
    assert cards.count() == 2
    subway, bus = cards.nth(0), cards.nth(1)
    leg = body['legs'][1]
    # 기본은 가장 빠른 지하철. 꼬리표·환승·도보·요금·노선.
    assert subway.get_attribute('aria-pressed') == 'true' and bus.get_attribute('aria-pressed') == 'false'
    text = subway.inner_text()
    assert f"지하철 {leg['options']['subway']['minutes']}분" in text and '가장 빠름' in text
    assert '환승 1회 · 도보 9분 · 1인 1,550원' in text and '수도권2호선 → 수도권분당선' in text
    assert '덜 걸음' in bus.inner_text() and '환승 적음' in bus.inner_text()
    # 미리보기: 앞 장소를 떠나는 시각 + 고른 경로 분(+여유시간). 일정의 추정과 차이.
    preview = second.locator('.transit-preview')
    assert preview.inner_text().endswith('(일정의 추정보다 3분 빠름). 저장된 일정·비용은 바뀌지 않아요.')
    bus.click()
    assert bus.get_attribute('aria-pressed') == 'true' and subway.get_attribute('aria-pressed') == 'false'
    expected = page.evaluate("""m=>{const d=selected.timeline[0].departure.split(':').map(Number),b=selected.conditions.transition_buffer_minutes||0;
      const t=(d[0]*60+d[1]+m+b)%1440;return String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0');}""", leg['options']['bus']['minutes'])
    assert preview.inner_text() == (f"이 경로로 가면 {leg['destination']} 도착 약 {expected} (일정의 추정보다 4분 늦음). "
                                    '저장된 일정·비용은 바뀌지 않아요.')
    # 지도: 고른 경로를 구간마다 도보 점선 + 탈것 실선으로. 둘째 구간은 버스로 바뀌었다.
    page.wait_for_function("document.querySelectorAll('.plan-map path.transit-route-bus').length===1")
    assert page.locator('.plan-map path.transit-route-subway').count() == legs - 1
    assert page.locator('.plan-map path.transit-route-walk').count() == legs
    assert page.locator('.map-transit-note').inner_text().startswith(f'대중교통: 고른 경로 {legs}구간을 실선으로 표시')
    # 일정·비용·저장된 코스는 그대로(미리보기 전용).
    assert page.evaluate(SNAPSHOT) == snapshot and len(requests) == 2
    assert no_overflow(page)
    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        second.scroll_into_view_if_needed()
        assert no_overflow(page), width
        short = page.locator('.transit-compare-intro button, .transit-option').evaluate_all(
            'els=>els.filter(el=>el.getClientRects().length&&el.getBoundingClientRect().height<43.5).map(el=>el.textContent)')
        assert not short, (width, short)
        small = second.evaluate(
            "p=>[...p.querySelectorAll('*')].filter(el=>el.childNodes.length&&[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))"
            ".filter(el=>parseFloat(getComputedStyle(el).fontSize)<13).map(el=>el.textContent)")
        assert not small, (width, small)
    # 다시 그려도(코스 다시 그리기) 받은 응답과 선택을 그대로 쓰고 다시 요청하지 않는다.
    page.evaluate('renderDetail()')
    assert page.locator('#plan-detail .transit-compare-panel').nth(1).locator('.transit-option[aria-pressed=true]').inner_text().startswith('버스')
    assert len(requests) == 2
    # 인쇄에는 단추·패널·지도 안내를 넣지 않는다.
    page.emulate_media(media='print')
    assert page.locator('.transit-compare-intro').is_hidden() and page.locator('.transit-compare-panel').first.is_hidden()
    page.emulate_media(media='screen')


def test_not_shown_for_walking_or_demo_courses(audit_page):
    page, base, errors = audit_page
    generate(page)
    page.evaluate('statusData.transit_compare_available=true;renderDetail()')
    # 가상 장소 데모, 도보 코스: 단추 없음.
    assert page.locator('.transit-compare-intro').count() == 0
    page.evaluate(ENABLE)
    assert page.locator('.transit-compare-intro').count() == 0  # 실제 모드여도 대중교통 구간이 없으면 없음
    to_transit(page)
    page.evaluate(ENABLE)
    assert page.locator('.transit-compare-intro').count() == 1
