"""피드백 탭: 실제 브라우저(Edge)에서 헤더 한 줄, 작성→성공 안내, 관리자 목록과 스크립트 글의 문자 표시."""
import uuid

from test_functional_audit import audit_page  # noqa: F401

from app import store

FAKE_KEY = 'ui-test-only-' + uuid.uuid4().hex

NAV = """[...document.querySelectorAll('body>header nav>*')].filter(e=>e.getClientRects().length)
  .map(e=>{const r=e.getBoundingClientRect();return {text:e.textContent.trim(),top:Math.round(r.top),
  height:r.height,left:r.left,right:r.right}})"""


def header_fits(page, width):
    items = page.evaluate(NAV)
    assert [i['text'] for i in items] == ['코스 만들기', '장소 둘러보기', '테마별 추천', '피드백'], (width, items)
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
        header_fits(page, width)
        assert page.locator('header nav a[aria-current=page]').inner_text() == '피드백'
    page.goto(base + '/', wait_until='networkidle')
    page.locator('#nav-feedback').click()
    page.wait_for_url(base + '/feedback')
    assert page.locator('h1').inner_text() == '피드백'


def test_writing_feedback_shows_success_and_blocks_resend(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(base + '/feedback', wait_until='networkidle')
    assert page.locator('#feedback-width').inner_text() == '390px'
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
        # 키는 브라우저 저장소에 남지 않는다.
        assert page.evaluate('localStorage.length+sessionStorage.length') == 0
    page.locator('.admin-entry button', has_text='처리함으로 표시').click()
    page.wait_for_selector('.admin-entry.handled')
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('.admin-entry button', has_text='삭제').click()
    page.wait_for_selector('.admin-empty')
