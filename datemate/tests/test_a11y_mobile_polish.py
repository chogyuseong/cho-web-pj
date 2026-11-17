"""2026-11-17 접근성·모바일 정리의 회귀 검사.

메뉴의 현재 화면 표시, 휴대폰 키보드 힌트, 대화상자를 닫은 뒤 포커스, 입력칸 테두리 대비, 휴대폰 칩 크기,
인쇄에서 불러오는 중 문구 숨김, 사진 자리 미리 잡기, 구역 표시줄.
"""
from test_functional_audit import audit_page, generate  # noqa: F401


def contrast(rgb_a, rgb_b):
    def lum(rgb):
        out = []
        for c in rgb:
            c /= 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    a, b = sorted((lum(rgb_a), lum(rgb_b)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def rgb(text):
    return tuple(int(part) for part in text[text.index('(') + 1:text.index(')')].split(',')[:3])


def test_nav_announces_the_current_screen(audit_page):
    page, base, errors = audit_page
    assert page.get_attribute('header nav', 'aria-label') == '주요 메뉴'
    pressed = "[...document.querySelectorAll('#nav-plan,#nav-explore')].map(b=>b.getAttribute('aria-pressed'))"
    assert page.evaluate(pressed) == ['true', 'false']
    page.click('#nav-explore')
    assert page.evaluate(pressed) == ['false', 'true']
    page.click('#nav-plan')
    assert page.evaluate(pressed) == ['true', 'false']


def test_phone_keyboards_get_search_send_and_number_hints(audit_page):
    page, base, errors = audit_page
    hints = page.evaluate("""()=>({
      search:document.querySelector('#search').enterKeyHint,
      origin:document.querySelector('form [name=origin_name]').enterKeyHint,
      people:document.querySelector('[name=people]').inputMode,
      budget:document.querySelector('[name=budget]').inputMode})""")
    assert hints == {'search': 'search', 'origin': 'search', 'people': 'numeric', 'budget': 'numeric'}, hints


def test_focus_returns_to_the_same_place_after_the_plan_is_redrawn(audit_page):
    page, base, errors = audit_page
    generate(page)
    # 두 번째 장소 카드 안의 단추에서 대화상자를 열고, 열린 동안 결과를 다시 그린 뒤(장소 교체와 같은 경로) 닫는다.
    page.evaluate("""()=>{
      const stop=document.querySelectorAll('#plan-detail .stop')[1];
      const opener=stop.querySelector('button,a[href]');opener.focus();
      openDialog('장소 바꾸기');renderResults();renderDetail();
      document.querySelector('#dialog').close();}""")
    page.wait_for_function("document.activeElement&&document.activeElement!==document.body")
    where = page.evaluate("""()=>{const a=document.activeElement;const stops=[...document.querySelectorAll('#plan-detail .stop')];
      return {tag:a.tagName,stop:stops.indexOf(a.closest('.stop'))};}""")
    assert where == {'tag': 'H4', 'stop': 1}, where


def test_input_borders_have_3_to_1_contrast_and_focus_stays_dark(audit_page):
    page, base, errors = audit_page
    # 화면에 보이는 입력·선택 칸 전부(인원·예산 숫자 칸은 +/- 단추 뒤에 숨어 있어 빠진다).
    borders = page.evaluate("""()=>[...document.querySelectorAll(
      'main input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]),main select,main textarea')]
      .filter(el=>el.getClientRects().length).map(el=>[el.name||el.id,getComputedStyle(el).borderTopColor])""")
    assert borders
    for name, border in borders:
        assert contrast(rgb(border), (255, 255, 255)) >= 3, (name, border)
    # editorial.css 의 테두리 색 전환(0.18초) 중간값을 읽지 않도록 동작 줄이기로 전환을 끈다.
    page.emulate_media(reduced_motion='reduce')
    page.focus('form [name=origin_name]')
    focused = page.evaluate("getComputedStyle(document.querySelector('form [name=origin_name]')).borderTopColor")
    assert contrast(rgb(focused), (255, 255, 255)) > 10, focused


def test_condition_chips_are_44px_tall_on_phones(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    heights = page.evaluate("""()=>[...document.querySelectorAll('.chips label > span')]
      .filter(s=>s.getClientRects().length).map(s=>s.getBoundingClientRect().height)""")
    assert heights and min(heights) >= 44, heights
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_print_hides_loading_notes(audit_page):
    page, base, errors = audit_page
    generate(page)
    page.evaluate("""()=>{const p=document.createElement('p');p.className='hint loading-note';p.id='loading-probe';
      p.textContent='메뉴 가격을 확인하고 있어요…';document.querySelector('#plan-detail').append(p);}""")
    page.emulate_media(media='print')
    assert page.evaluate("getComputedStyle(document.getElementById('loading-probe')).display") == 'none'
    page.emulate_media(media='screen')
    assert page.evaluate("getComputedStyle(document.getElementById('loading-probe')).display") != 'none'


def test_photo_space_is_reserved_before_the_photo_arrives(audit_page):
    page, base, errors = audit_page
    sizes = page.evaluate("""()=>{
      const panel=document.createElement('section');panel.className='place-photo-panel';
      const status=document.createElement('p');status.className='photo-status';status.textContent='장소 사진을 불러오고 있어요…';
      panel.append(status);
      const figure=document.createElement('figure');figure.className='place-photo';
      const viewport=document.createElement('div');viewport.className='photo-viewport';figure.append(viewport);
      document.querySelector('main').append(panel,figure);
      const out=[panel.getBoundingClientRect().height,viewport.getBoundingClientRect().height];
      panel.remove();figure.remove();return out;}""")
    assert sizes[0] >= 220 and sizes[1] >= 195, sizes


def test_section_indicator_still_follows_headings_on_phones(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    page.evaluate("""()=>{const h=[...document.querySelectorAll('#plan-detail h3')][0];
      window.scrollTo(0,h.getBoundingClientRect().top+scrollY-40);}""")
    page.wait_for_function("document.querySelector('.section-indicator').classList.contains('is-visible')")
    top = page.evaluate("parseFloat(document.querySelector('.section-indicator').style.top)")
    header = page.evaluate("document.querySelector('body > header').getBoundingClientRect().bottom")
    assert abs(top - max(0, header)) < 1, (top, header)


def test_review_report_reason_is_asked_in_the_page_not_with_prompt(audit_page):
    page, base, errors = audit_page
    sent = []
    page.route('**/api/plans/review-probe/reviews', lambda route: route.fulfill(json={
        'average': 4, 'count': 1, 'label': '', 'verification': '', 'rows': [
            {'id': 'r1', 'nickname': '방문자', 'rating': 4, 'visited': '2026-11-16', 'created': 1794800000,
             'body': '좋았어요', 'mine': False}]}))
    page.route('**/api/reviews/r1/report', lambda route: (sent.append(route.request.post_data_json),
                                                          route.fulfill(json={'notice': '신고를 접수했어요.'})))
    opened = []
    page.on('dialog', lambda dialog: (opened.append(dialog.type), dialog.dismiss()))
    page.evaluate("""async()=>{const box=document.createElement('div');box.id='review-probe';document.querySelector('main').append(box);
      await loadReviews(box,{id:'review-probe',conditions:{mode:'real'}});}""")
    report = page.locator('#review-probe .review .actions').get_by_role('button', name='신고', exact=True)
    report.click()
    assert report.get_attribute('aria-expanded') == 'true'
    box = page.locator('#review-probe .review-report textarea')
    assert box.evaluate('el=>el.required&&el.maxLength===2000&&document.activeElement===el')
    page.locator('#review-probe .review-report button[type=submit]').click()
    assert sent == []  # 빈 사유는 보내지 않는다
    box.fill('광고성 후기예요')
    page.locator('#review-probe .review-report button[type=submit]').click()
    page.wait_for_function("!document.querySelector('#review-probe .review-report')")
    assert sent == [{'reason': '광고성 후기예요'}]
    assert page.locator('#toast').inner_text() == '신고를 접수했어요.'
    assert report.get_attribute('aria-expanded') == 'false'
    assert opened == [], opened
