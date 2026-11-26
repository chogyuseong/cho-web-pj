"""피드백 탭: 실제 브라우저(Edge)에서 헤더 한 줄, 작성→성공 안내, 관리자 목록과 스크립트 글의 문자 표시."""
import uuid

from test_functional_audit import audit_page  # noqa: F401

from app import store

FAKE_KEY = 'ui-test-only-' + uuid.uuid4().hex

NAV = """[...document.querySelectorAll('body>header nav>*')].filter(e=>e.getClientRects().length)
  .map(e=>{const r=e.getBoundingClientRect();return {text:e.textContent.trim(),top:Math.round(r.top),
  height:r.height,left:r.left,right:r.right}})"""


def header_fits(page, width, feedback_page=False):
    items = page.evaluate(NAV)
    # 2026-11-25 시안: 데스크톱 메뉴는 코스 만들기·테마 추천·장소 둘러보기·피드백. 휴대폰 하단 바(홈 화면)는 피드백 대신 코스 결과가
    # 있다(DOM 순서로는 마지막, CSS order 로 셋째 칸). 피드백 화면 메뉴는 폭과 관계없이 피드백까지 넷.
    expected = ['코스 만들기', '테마 추천', '장소 둘러보기', '추천 결과' if width <= 720 and not feedback_page else '피드백']
    assert [i['text'] for i in items] == expected, (width, items)
    assert len({i['top'] for i in items}) == 1, (width, items)  # 한 줄
    assert all(44 <= i['height'] < 60 for i in items), (width, items)  # 낱말이 두 줄로 깨지지 않음
    assert all(i['left'] >= 0 and i['right'] <= width for i in items), (width, items)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width


def test_feedback_tab_fits_the_header_on_home_and_feedback_page(audit_page):
    page, base, errors = audit_page
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base + '/', wait_until='networkidle')
        header_fits(page, width)
        page.goto(base + '/feedback', wait_until='networkidle')
        header_fits(page, width, feedback_page=True)
        assert page.locator('header nav a[aria-current=page]').inner_text() == '피드백'
    page.goto(base + '/', wait_until='networkidle')
    page.locator('footer .footer-feedback').click()
    page.wait_for_url(base + '/feedback')
    # 2026-11-26 시안: 제목 '피드백 보내기', 오른쪽에 '데이터 및 이용 안내' 질문 모음(유형·만족도 칩은 test_feedback_kind_and_mood_go_in_front).
    assert page.locator('h1').inner_text() == '피드백 보내기'
    assert page.locator('.feedback-faq h2').inner_text() == '데이터 및 이용 안내' and page.locator('.feedback-faq details').count() == 3


def test_writing_feedback_shows_success_and_blocks_resend(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(base + '/feedback', wait_until='networkidle')
    # 화면 폭 줄은 접힌 '함께 보내는 것' 안에 있다(2026-11-24 UX P0) — 보이는 글자가 아니라 내용으로 본다.
    assert page.locator('#feedback-width').text_content() == '390px'
    page.locator('#feedback-message').fill('짧아')
    page.locator('#feedback-submit').click()
    assert page.locator('[role=alert]').inner_text() == '내용을 5자 이상 적어 주세요.'
    text = 'UI 확인 ' + uuid.uuid4().hex
    page.locator('#feedback-message').fill(text)
    assert page.locator('#feedback-count').inner_text() == f'남은 글자 {1000 - len(text)}자'
    page.locator('#feedback-screen').select_option('explore')
    page.locator('#feedback-submit').click()
    page.wait_for_selector('#feedback-status:has-text("고마워요")')
    assert page.locator('#feedback-message').input_value() == ''
    assert page.locator('#feedback-submit').is_disabled()
    assert page.locator('#feedback-error').inner_text() == ''
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    with store.connect() as db:
        row = db.execute('SELECT screen,viewport_width FROM feedback_entries WHERE message=?', (text,)).fetchone()
    # 이름으로 읽는다: SQLite 의 sqlite3.Row 는 값을, PostgreSQL 의 Record(dict, app/database.py)는 tuple() 에 열 이름을 내준다.
    assert (row['screen'], row['viewport_width']) == ('explore', 390)


def test_admin_lists_script_text_as_plain_text(audit_page, monkeypatch):
    monkeypatch.setenv('FEEDBACK_ADMIN_KEY', FAKE_KEY)
    page, base, errors = audit_page
    text = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script> ' + uuid.uuid4().hex
    with store.connect() as db:
        db.execute('DELETE FROM feedback_entries')
        db.execute('INSERT INTO feedback_entries(id,created,message,screen,contact,viewport_width,browser,handled) '
                   'VALUES(?,?,?,?,?,?,?,0)', (uuid.uuid4().hex, 2e9, text, 'results', 'me@example.com', 390, 'Edge'))
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(base + '/feedback/admin', wait_until='networkidle')
        page.locator('#admin-key').fill('wrong-key')
        page.locator('#admin-key').press('Enter')
        page.wait_for_selector('#admin-error:has-text("키가 맞지 않거나")')
        page.locator('#admin-key').fill(FAKE_KEY)
        page.locator('#admin-open').click()
        page.wait_for_selector('.admin-entry')
        assert page.locator('#admin-key').input_value() == ''
        assert page.locator('.admin-message').first.text_content() == text
        assert page.evaluate('typeof window.__xss') == 'undefined'
        assert page.locator('#admin-entries img, #admin-entries script').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        # 키는 브라우저 저장소에 남지 않는다. 같은 주소의 첫 화면(audit_page 가 먼저 연 '/')이 남긴 접힘 기억
        # (datemate:plan-*, conftest PLAN_FOLDS_OPEN)만 있을 수 있고, 관리 화면이 넣은 것은 없어야 한다.
        stored = page.evaluate("[...Object.keys(localStorage),...Object.keys(sessionStorage)]")
        assert all(key.startswith('datemate:plan-') for key in stored), stored
        assert FAKE_KEY not in page.evaluate("JSON.stringify({...localStorage})+JSON.stringify({...sessionStorage})")
    page.locator('.admin-entry button', has_text='처리함으로 표시').click()
    page.wait_for_selector('.admin-entry.handled')
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('.admin-entry button', has_text='삭제').click()
    page.wait_for_selector('.admin-empty')


def test_feedback_kind_and_mood_go_in_front(audit_page):
    """문의 유형·이용 만족도(2026-11-26 시안, 선택): 고른 것만 글 앞머리 '[유형 · 만족도] '로 붙여 보낸다(DB 칸은 그대로, static/feedback.js prefix)."""
    page, base, _ = audit_page
    sent = []
    page.route('**/api/feedback', lambda route: (sent.append(route.request.post_data_json), route.fulfill(json={'received': True, 'message': '고마워요'}))[1])
    page.goto(base + '/feedback', wait_until='networkidle')
    page.get_by_text('장소 오류', exact=True).click()
    page.get_by_text('아쉬워요', exact=True).click()
    assert page.locator('[name=kind]:checked').input_value() == '장소 오류'
    page.locator('#feedback-message').fill('영업시간이 달라요. 확인 부탁해요.')
    page.locator('#feedback-submit').click()
    page.wait_for_function("document.getElementById('feedback-status').textContent.includes('고마워요')")
    assert sent[-1]['message'] == '[장소 오류 · 아쉬워요] 영업시간이 달라요. 확인 부탁해요.'
    # 칩은 진짜 라디오 단추라 키보드로 고를 수 있고, 누르기 쉬운 높이다.
    label = page.locator('.feedback-chip-row label').first
    assert label.bounding_box()['height'] >= 44
