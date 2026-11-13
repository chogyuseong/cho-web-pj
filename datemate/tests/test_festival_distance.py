"""축제 구역이 출발지에서 가까운 축제부터 보여 주고, 각 축제의 직선거리를 적는지."""
from fastapi.testclient import TestClient
from app.main import app
from test_festival_restore import saved_plan
from test_feedback_ui import route_festivals
from test_functional_audit import audit_page  # noqa: F401  (pytest 픽스처)

ORIGIN = dict(name='충북 청주시 상당구 · 청주시청', lat=36.6424, lon=127.4890)


def row(id, title, lat=None, lon=None):
    return dict(id=id, title=title, start='2026-10-01', end='2026-10-31', region='충북', address='충청북도 ' + title,
                source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=' + id, image_url=None, image_license=None, lat=lat, lon=lon)


# 서버는 기간이 짧은 순으로 주므로 먼 축제가 앞에 올 수 있다.
ROWS = [row('1', '단양 축제', 36.9845, 128.3655), row('2', '충주 축제', 36.9910, 127.9260), row('3', '좌표 없는 축제'),
        row('4', '청주 북쪽 축제', 36.6712, 127.4890), row('5', '청주 남쪽 축제', 36.6350, 127.4890), row('6', '시청 앞 축제', 36.6430, 127.4895)]


def route_rows(page, rows=ROWS):
    details = []
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=rows, total_matches=len(rows), truncated=False,
                                                                        message='한국관광공사 행사정보 자료입니다.')))
    page.route('**/api/festivals/*/detail', lambda route: (details.append(route.request.url.rsplit('/', 2)[-2]),
                                                           route.fulfill(json=dict(status='available', fee='무료', hours=None, place=None, checked_at='2026-10-24', message=''))))
    return details


def load(page, conditions, count):
    page.evaluate('c=>FestivalPanel.load(c)', conditions)
    page.wait_for_function(f'document.querySelectorAll("#festival-results .festival-card").length==={count}')
    cards = page.locator('#festival-results .festival-card')
    return cards, [cards.nth(i).locator('strong').first.inner_text() for i in range(count)]


def distances(page):
    return page.evaluate('[...document.querySelectorAll("#festival-results .festival-card")].map(c=>c.querySelector(".festival-distance")?.textContent??null)')


def test_real_origin_sorts_nearest_first_and_shows_straight_distance(audit_page):
    page, base, errors = audit_page
    details = route_rows(page)
    cards, titles = load(page, dict(mode='real', region='충북', visit_date='2026-10-24', origin=ORIGIN), 6)
    assert titles == ['시청 앞 축제', '청주 남쪽 축제', '청주 북쪽 축제', '충주 축제', '단양 축제', '좌표 없는 축제']
    assert distances(page) == ['출발지에서 직선거리 약 100m', '출발지에서 직선거리 약 800m', '출발지에서 직선거리 약 3.2km',
                               '출발지에서 직선거리 약 55km', '출발지에서 직선거리 약 87km', None]
    status = page.locator('#festival-status').inner_text()
    assert '충북 전체 축제를 출발지에서 가까운 순(직선거리)으로 보여드려요.' in status
    assert '위치 정보가 없는 축제는 맨 뒤에 있어요.' in status and '한국관광공사 행사정보 자료입니다.' in status
    assert '방문 전 공식 안내를 확인' in page.locator('#festival-section').inner_text()
    # 지도 표시와 요금·시간 조회도 가까운 순서를 따른다.
    assert page.evaluate('FestivalPanel.mapItems.map(f=>f.id)') == ['6', '5', '4', '2', '1']
    page.wait_for_function('![...document.querySelectorAll(".festival-fee")].some(p=>p.textContent.includes("확인 중"))')
    assert set(details[:3]) == {'6', '5', '4'}


def test_coordinate_less_festivals_keep_their_order_at_the_end(audit_page):
    page, base, errors = audit_page
    rows = [row('1', '좌표 없는 첫 축제'), row('2', '먼 축제', 36.9910, 127.9260), row('3', '좌표 없는 둘째 축제'), row('4', '가까운 축제', 36.6430, 127.4895)]
    route_rows(page, rows)
    cards, titles = load(page, dict(mode='real', region='충북', visit_date='2026-10-24', origin=ORIGIN), 4)
    assert titles == ['가까운 축제', '먼 축제', '좌표 없는 첫 축제', '좌표 없는 둘째 축제']
    assert distances(page)[2:] == [None, None]


def test_without_a_chosen_origin_keeps_server_order_without_distance(audit_page):
    page, base, errors = audit_page
    route_rows(page)
    expected = [r['title'] for r in ROWS]
    # 공유 화면처럼 출발지가 없거나, 사용자가 고르지 않은 데모 출발점이면 기준이 없다.
    for conditions in (dict(region='충북', visit_date='2026-10-24'),
                       dict(mode='demo', region='충북', visit_date='2026-10-24', origin=dict(name='데모 출발점', lat=37.575, lon=126.985)),
                       dict(mode='real', region='충북', visit_date='2026-10-24', origin=dict(name='좌표 없음', lat=None, lon=None))):
        cards, titles = load(page, conditions, 6)
        assert titles == expected, conditions
        assert distances(page) == [None] * 6
        assert '가까운 순' not in page.locator('#festival-status').inner_text()


def test_chosen_festival_stays_first_without_its_own_distance(audit_page):
    page, base, errors = audit_page
    route_rows(page)
    chosen = ROWS[1]  # 충주 축제를 골라 그 장소를 출발지로 다시 추천한 경우
    origin = dict(name='충북 충주시 · 충주 축제 행사장 주변', lat=chosen['lat'], lon=chosen['lon'])
    page.evaluate('([festival,name])=>{FestivalPanel.chosen={festival,originName:name}}', [chosen, origin['name']])
    cards, titles = load(page, dict(mode='real', region='충북', visit_date='2026-10-24', origin=origin), 6)
    assert titles[0] == '충주 축제' and '선택한 축제' in cards.nth(0).inner_text()
    assert titles[1:] == ['단양 축제', '청주 북쪽 축제', '시청 앞 축제', '청주 남쪽 축제', '좌표 없는 축제']
    shown = distances(page)
    assert shown[0] is None and all(text and text.startswith('출발지에서 직선거리 약 ') for text in shown[1:5]) and shown[5] is None
    assert '선택한 축제를 맨 위에 두고, 나머지는 축제 장소에서 가까운 순(직선거리)으로 보여드려요.' in page.locator('#festival-status').inner_text()


def test_shared_page_shows_no_distance_or_origin_order(audit_page):
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan = saved_plan(client, festival=True)
        token = client.post('/api/plans/' + plan['id'] + '/shares').json()['url']
    route_festivals(page)
    page.goto(base + token)
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert page.locator('.festival-distance').count() == 0
    assert '가까운 순' not in page.locator('#festival-section').inner_text() and '출발지' not in page.locator('#festival-results').inner_text()
    assert [page.locator('#festival-results .festival-card strong').nth(i).inner_text() for i in range(3)][0] == '점검 등불축제'
