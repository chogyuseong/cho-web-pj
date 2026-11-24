"""P0-1 개발자 언어 정리 (2026-11-24 사용자 요구 'UX 개선 P0').

- 첫 화면(HTML 원본 포함) 어디에도 'API 키', '접속 IP', '가상 장소 데모' 같은 개발자용 문구가 없다.
- 서비스 상태는 정상일 때 보이지 않고(빈 #status 는 hidden), 장애일 때만 배너처럼 보인다.
- 공공 장소 자료 키가 없으면(서버 public_places_available=false) 친절한 폴백 배너와 '서울 체험 코스 둘러보기'를 보여 준다.
- 데모(서울 체험 코스)는 ?demo=1 로 들어올 때와 폴백 단추로만 켜진다.
"""
from pathlib import Path

from test_functional_audit import audit_page  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
DEV_WORDS = ('API 키', 'API키', '접속 IP', '가상 장소 데모', '가상 데모', '데이터 모드', '임베딩', '메타데이터', 'GMS')


def test_home_html_has_no_developer_words():
    html = (ROOT / 'static/index.html').read_text('utf-8')
    for word in DEV_WORDS:
        assert word not in html, word


def test_ready_home_hides_the_status_and_shows_no_developer_words(audit_page):  # noqa: F811
    page, _, _ = audit_page
    page.wait_for_function('!!statusData')
    status = page.locator('#status')
    assert status.is_hidden() and status.text_content().strip() == ''
    visible = page.evaluate('document.body.innerText')
    for word in DEV_WORDS:
        assert word not in visible, word


def test_status_error_is_shown_as_a_banner(audit_page):  # noqa: F811
    page, base, _ = audit_page
    page.route('**/api/status', lambda route: route.fulfill(status=429, json={'detail': '요청이 많아요. 잠시 후 다시 시도해 주세요.'}))
    page.goto(base)
    page.wait_for_function('document.querySelector("#status").textContent.includes("요청이 많아요")')
    assert page.locator('#status').is_visible()


def test_missing_public_data_key_shows_a_friendly_fallback(audit_page):  # noqa: F811
    page, base, _ = audit_page

    def status(route):
        response = route.fetch()
        body = response.json()
        body['public_places_available'] = False
        route.fulfill(response=response, json=body)
    page.route('**/api/status', status)
    page.goto(base)
    page.wait_for_function('!!statusData')
    banner = page.locator('#status')
    assert banner.is_visible()
    text = banner.inner_text()
    assert '실시간 장소 검색을 점검 중이에요' in text and '서울 체험 코스' in text
    for word in DEV_WORDS:
        assert word not in text, word
    banner.get_by_role('button', name='서울 체험 코스 둘러보기').click()
    assert page.evaluate("form.elements.mode.value") == 'demo'


def test_demo_query_turns_on_the_tour_mode(audit_page):  # noqa: F811
    page, base, _ = audit_page
    page.goto(base + '/?demo=1')
    page.wait_for_function('!!statusData')
    assert page.evaluate("[form.elements.mode.value, mode, form.elements.region.value]") == ['demo', 'demo', '서울']
    page.goto(base + '/')
    page.wait_for_function('!!statusData')
    assert page.evaluate("form.elements.mode.value") == 'real', '쿼리가 없으면 실제 장소'


def test_feedback_page_keeps_the_data_note_folded(audit_page):  # noqa: F811
    page, base, _ = audit_page
    page.goto(base + '/feedback')
    note = page.locator('details.feedback-auto')
    assert note.count() == 1 and note.evaluate('d=>!d.open')
    assert '함께 보내는 것' in note.locator('summary').inner_text()
    text = note.text_content()
    assert '관리자가 확인해 지울 때까지 보관해요' in text and '접속 IP' in text, '이용 안내는 피드백 폼의 접은 안내 안으로 옮겼다'
