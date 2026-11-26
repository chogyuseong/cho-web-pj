"""2026-11-26 요구 문서 Phase 1(datemate/docs/redesign-2026-11-26-plan.ko.md).

- 디자인 토큰(static/tokens.css)과 <html data-mode>: 데이트 ↔ 여행이면 포인트색이 #FF385C ↔ #2563EB 로 바뀐다(글자용 --brand-ink 는 진한 색).
- 머리글 '추천 결과' 탭: 코스를 만들면 데스크톱 메뉴에도 보이고 코스 개수 배지, 결과 화면에서는 이 탭만 현재 위치.
- 되돌리기 알림: 장소를 바꾸면 알림에 [되돌리기] 단추, 누르면 바꾸기 전 코스로 돌아간다(서버 /undo).
- 방문일 날씨(weather.js): 날씨 자료가 없으면 사용자가 고르고, 비·눈이면 실내 위주 제안 → 누르면 실내만.
- 서버 안내에 '키' 같은 개발자 말이 없다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)


def css_var(page, name):
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('{name}').trim()")


def test_tokens_follow_date_and_travel_mode(audit_page):
    page, _, _ = audit_page
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    assert page.evaluate('document.documentElement.dataset.mode') == 'date'
    assert css_var(page, '--brand-primary').upper() == '#FF385C' and css_var(page, '--cat-walk').upper() == '#059669'
    page.locator('#mode-switch [data-mode=travel]').click()
    page.wait_for_function("document.documentElement.dataset.mode==='travel'")
    assert css_var(page, '--brand-primary').upper() == '#2563EB' and css_var(page, '--brand-ink').upper() == '#1D4ED8'
    page.locator('#mode-switch [data-mode=date]').click()
    page.wait_for_function("document.documentElement.dataset.mode==='date'")
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")


def test_results_tab_shows_the_course_count_and_is_current_on_results(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    tab = page.locator('#nav-results')
    assert not tab.is_visible(), '코스를 만들기 전에는 데스크톱 메뉴에 없다'
    generate(page)
    wait_for_selected_detail(page)
    page.wait_for_function("document.querySelector('#nav-results .nav-count').textContent===String(plans.length)")
    count = page.evaluate('plans.length')
    assert tab.is_visible() and tab.get_attribute('aria-label') == f'추천 결과 · 코스 {count}개'
    assert tab.get_attribute('aria-current') == 'true' and page.locator('#nav-plan').get_attribute('aria-current') is None
    # 메뉴 순서: 코스 만들기 다음이 추천 결과.
    order = page.evaluate("""[...document.querySelectorAll('body > header nav > :is(a,button)')].filter(e=>e.getClientRects().length)
      .sort((a,b)=>a.getBoundingClientRect().left-b.getBoundingClientRect().left).map(e=>e.id||e.className)""")
    assert order[:2] == ['nav-plan', 'nav-results'], order


def test_replacing_a_place_offers_undo_in_the_toast(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    before = page.evaluate('selected.places.map(p=>p.name)')
    page.locator('#plan-detail .stop .actions button', has_text='다른 장소로 바꾸기').first.click()
    page.locator('#dialog select').first.select_option('distance')
    page.locator('#dialog button', has_text='이 장소로 교체').first.click()
    page.wait_for_function("!!document.querySelector('#toast .toast-action')", timeout=30000)
    assert page.locator('#toast .toast-text').inner_text() == '장소를 바꿨어요. 바로 되돌릴 수 있어요.'
    assert page.evaluate('selected.places.map(p=>p.name)') != before
    action = page.locator('#toast .toast-action')
    assert action.inner_text() == '되돌리기' and action.bounding_box()['height'] >= 44
    action.click()
    page.wait_for_function("b=>JSON.stringify(selected.places.map(p=>p.name))===JSON.stringify(b)", arg=before, timeout=20000)


def test_visit_day_weather_suggests_indoor_without_inventing_a_forecast(audit_page):
    page, _, _ = audit_page
    chips = page.locator('#weather-choice .weather-chip')
    assert chips.all_inner_texts() == ['맑음·흐림', '비·눈', '모름']
    # 날씨 자료가 없으니 '모름'으로 시작하고 출처 줄이 없다(예보를 지어내지 않는다).
    assert page.locator('#weather-choice [data-sky=unknown]').get_attribute('aria-pressed') == 'true'
    assert page.locator('#weather-choice .weather-source').is_hidden()
    page.evaluate("form.elements.setting.value='any'")
    page.locator('#weather-choice [data-sky=rain]').click()
    suggest = page.locator('#weather-choice .weather-suggest')
    assert '실내 위주 코스로 맞출까요?' in suggest.inner_text()
    suggest.get_by_role('button', name='실내 위주로').click()
    assert page.evaluate('form.elements.setting.value') == 'indoor'
    page.locator('#weather-choice [data-sky=clear]').click()
    assert suggest.is_hidden()


def test_server_messages_have_no_developer_words():
    from app.config import ROOT
    for name in ('festivals.py', 'blog_search.py', 'explore.py', 'popup_api.py', 'main.py'):
        text = (ROOT / 'app' / name).read_text(encoding='utf-8')
        for phrase in ('API 키를 설정하면', 'API 키가 설정되지', '키가 필요해요', '키가 설정되지 않아'):
            assert phrase not in text, (name, phrase)
