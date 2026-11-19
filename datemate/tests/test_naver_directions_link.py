"""구간마다 「네이버 지도 길찾기」 링크(static/plan-actions.js naverDirectionsUrl). 2026-11-19 TMAP 지하철·버스 비교를 대신한다.

네이버 지도 API 에는 공개된 대중교통 길찾기가 없어, 출발·도착이 채워진 네이버 지도 길찾기 화면을 새 탭으로 연다.
주소 형식은 2026-11-19 실제 브라우저로 서울역→강남역 대중교통 경로가 열리는 것을 확인했다.
"""
from fastapi.testclient import TestClient

from app.main import app
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_directions_url_from_leg_link(audit_page):
    page, _, _ = audit_page
    urls = page.evaluate("""()=>{
      const link='nmap://route/public?slat=37.5547&slng=126.9706&sname=%EC%84%9C%EC%9A%B8%EC%97%AD&dlat=37.4979&dlng=127.0276&dname=%EA%B0%95%EB%82%A8%EC%97%AD&appname=datemate.local';
      const real={conditions:{mode:'real',transport:'transit'}};
      return [
        naverDirectionsUrl(real,{link}),
        naverDirectionsUrl(real,{link,mode:'car'}),
        naverDirectionsUrl({conditions:{mode:'demo',transport:'transit'}},{link}),
        naverDirectionsUrl(real,{link:'nmap://route/public?slat=x&slng=1'}),
        naverDirectionsUrl(real,{}),
      ];
    }""")
    assert urls[0] == ('https://map.naver.com/p/directions/126.9706,37.5547,%EC%84%9C%EC%9A%B8%EC%97%AD,,'
                       '/127.0276,37.4979,%EA%B0%95%EB%82%A8%EC%97%AD,,/-/transit')
    assert urls[1].endswith('/-/car')
    assert urls[2] is None, '가상 데모 좌표는 실제 장소가 아니라 링크를 달지 않는다'
    assert urls[3] is None and urls[4] is None


def test_real_course_route_lines_open_naver_transit_directions(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    # 데모 코스를 실제 코스처럼 다시 그린다(좌표는 그대로). 대중교통으로 바꿔 링크 문구를 본다.
    page.evaluate("selected.conditions.mode='real';selected.conditions.transport='transit';selected.legs.forEach(l=>l.mode='transit');renderDetail()")
    links = page.locator('#plan-detail .route-directions-link')
    assert links.count() == page.evaluate('selected.legs.length')
    first = links.first
    assert first.inner_text() == '네이버 지도 대중교통 길찾기 ↗'
    assert first.get_attribute('target') == '_blank' and 'noopener' in first.get_attribute('rel')
    assert first.get_attribute('href').startswith('https://map.naver.com/p/directions/') and first.get_attribute('href').endswith('/-/transit')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
    # TMAP 비교 단추는 더 이상 없다.
    assert page.locator('.transit-compare-intro, .transit-compare-panel').count() == 0


def test_tmap_compare_api_is_gone():
    with TestClient(app) as client:
        plan = client.post('/api/plans', json={'visit_date': '2026-10-24', 'max_leg': 180}).json()['plans'][0]
        assert client.get('/api/plans/' + plan['id'] + '/transit-compare').status_code == 404
        assert 'transit_compare_available' not in client.get('/api/status').json()
