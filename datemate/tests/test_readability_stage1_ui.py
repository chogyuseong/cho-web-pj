"""가독성 정리 1단계(2026-11-17): 장소 카드는 이름 → 한 줄 요약 순서, 출처 문장·사진 정보는 접고,
구간 설명이 모두 같으면 한 번만, 네이버 지도 찾기는 한 줄 링크 묶음."""
from test_functional_audit import audit_page, generate  # noqa: F401


def test_stop_card_reads_name_then_one_summary_line(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    card = page.evaluate("""()=>{const c=document.querySelector('#plan-detail .timeline-card');
      const kids=[...c.children].map(e=>e.tagName+(e.className?'.'+e.className.split(' ')[0]:''));
      const meta=c.querySelector('.stop-meta');
      return {first:kids[0],second:kids[1],third:kids[2],fourth:kids[3],meta:meta.innerText,source:!!c.querySelector('details.stop-source:not([open]) p.hint'),
        nameSize:parseFloat(getComputedStyle(c.querySelector('h4')).fontSize),
        dupTime:[...c.querySelectorAll(':scope > .small')].length};}""")
    # 2026-11-25 시안(결과 화면 상세, 9535314): 장소 태그 줄(.stop-tags)이 이름 위에 오고, 이름 아래에 주소 줄(.stop-address)이 붙는다.
    # 순서는 태그 → 이름 → 주소 → 한 줄 요약. 상세 화면을 시안 카드 모양으로 다시 짜면 이 순서도 함께 고친다.
    assert (card['first'], card['second'], card['third'], card['fourth']) == ('DIV.stop-tags', 'H4', 'P.stop-address', 'P.stop-meta'), card
    assert '분 머묾' in card['meta'] and '2인' in card['meta'], card
    assert card['source'] and card['dupTime'] == 0, card
    assert card['nameSize'] >= 20, card
    # 비용·머무는 시간은 줄 중간에서 끊기지 않는다.
    assert page.evaluate("getComputedStyle(document.querySelector('#plan-detail .stop-meta .stop-cost')).whiteSpace") == 'nowrap'
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_same_leg_note_is_written_once_above_the_timeline(audit_page):
    page, base, errors = audit_page
    generate(page)
    state = page.evaluate("""()=>({shared:sharedLegSource(selected),
      perLeg:document.querySelectorAll('#plan-detail .route-line-source').length,
      once:document.querySelectorAll('#plan-detail .route-source-note').length})""")
    if state['shared']:
        assert state == {'shared': state['shared'], 'perLeg': 0, 'once': 1}, state
        # 계산 방식은 기본으로 접혀 있고, 누르면 펼쳐져 설명이 보인다(2026-11-24 사용자 요청).
        fold = page.locator('#plan-detail details.route-source-note')
        assert fold.count() == 1 and not fold.evaluate('e=>e.open')
        assert not fold.locator('.hint').is_visible()
        fold.locator('summary').click()
        assert fold.locator('.hint').is_visible()
        assert state['shared'] in fold.locator('.hint').inner_text()
    else:
        assert state['once'] == 0, state
    assert page.evaluate("sharedLegSource({legs:[{source:'a'},{source:'a'}]})") == 'a'
    assert page.evaluate("sharedLegSource({legs:[{source:'a'},{source:'b'}]})") is None
    assert page.evaluate("sharedLegSource({legs:[{source:'a'}]})") is None


def test_map_links_are_one_compact_row(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    links = page.locator('#plan-detail .map-link-list a')
    names = page.evaluate('selected.places.map(p=>p.name)')
    assert links.all_inner_texts() == [f'{i + 1}. {name}' for i, name in enumerate(names)]
    height = page.evaluate("document.querySelector('#plan-detail .map-link-list').getBoundingClientRect().height")
    assert height < 120, height  # 전에는 화면 폭 단추 3개(약 170px)


def test_phone_reads_timeline_before_the_map_and_compact_numbers(audit_page):
    """2단계: 휴대폰은 일정 뒤에 지도, 고른 코스 수치는 2×2 칸, 장소 단추는 높이 44px 로 글자 길이만큼."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map-card')")
    order = page.evaluate("""()=>{const last=[...document.querySelectorAll('#plan-detail .stop')].at(-1),slot=document.getElementById('plan-map-slot'),
      check=document.querySelector('#plan-detail .execution-summary');
      return {afterStops:!!(last.compareDocumentPosition(slot)&Node.DOCUMENT_POSITION_FOLLOWING),
        beforeChecks:!!(slot.compareDocumentPosition(check)&Node.DOCUMENT_POSITION_FOLLOWING),inDetail:!!slot.closest('#plan-detail')};}""")
    assert order == {'afterStops': True, 'beforeChecks': True, 'inDetail': True}, order
    stats = page.evaluate("""()=>{const boxes=[...document.querySelectorAll('#results .plan-card .stats > div')];
      return {cols:new Set(boxes.map(b=>Math.round(b.getBoundingClientRect().left))).size,rows:new Set(boxes.map(b=>Math.round(b.getBoundingClientRect().top))).size};}""")
    assert stats == {'cols': 2, 'rows': 2}, stats
    buttons = page.evaluate("""()=>[...document.querySelectorAll('#plan-detail .stop .actions > button')].filter(b=>b.getClientRects().length)
      .map(b=>({h:b.getBoundingClientRect().height,lines:Math.round(b.getBoundingClientRect().height/parseFloat(getComputedStyle(b).lineHeight||'20'))}))""")
    assert buttons and all(b['h'] >= 43.5 for b in buttons), buttons
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_desktop_keeps_the_map_in_the_side_rail(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 1000})
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-map-card')")
    assert page.locator('#plan-map-slot').is_hidden()


def test_selected_course_card_keeps_only_what_the_tabs_do_not_show(audit_page):
    """가독성 3단계: 코스 번호·목적 태그·차이 설명·조건 넓힘 태그·방문 장소 수는 탭에만 있다."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    card = page.evaluate("""()=>{const c=document.querySelector('#results .plan-card.selected');
      return {heading:!!c.querySelector('.option-heading,.number'),tags:[...c.querySelectorAll(':scope > .tag')].map(t=>t.textContent),
        stats:[...c.querySelectorAll('.stats small')].map(s=>s.textContent),title:!!c.querySelector('h3'),
        last:c.lastElementChild.textContent,purposeInTab:document.querySelector('.plan-option-tabs [aria-pressed=true] .option-purpose')?.textContent||''};}""")
    assert not card['heading'] and card['tags'] == [], card
    assert card['title'] and not any('방문 장소' in s for s in card['stats']) and len(card['stats']) == 3, card
    assert card['last'] == '일정 살펴보기 ↓', card
    page.get_by_role('button', name='일정 살펴보기 ↓').click()
    page.wait_for_function("document.querySelector('#plan-detail').getBoundingClientRect().top<innerHeight")


def test_phone_header_is_one_compact_block(audit_page):
    """가독성 3단계: 휴대폰 헤더는 여백을 줄이고 메뉴를 한 줄로 둬 120px 아래(전 390px 124px, 320px 172px). 보조 문구는 남긴다.
    2026-11-25 시안: 숨겨진 메뉴 칸(휴대폰의 피드백)은 줄 수에서 뺀다. 보조 문구는 .brand-sub(DATEMATE)."""
    page, base, errors = audit_page
    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 700})
        state = page.evaluate("""()=>{const h=document.querySelector('body > header'),n=h.querySelector('nav'),items=[...n.children].filter(i=>i.getClientRects().length);
          return {height:h.getBoundingClientRect().height,tagline:getComputedStyle(h.querySelector('.brand-name')).display,
            rows:new Set(items.map(i=>Math.round(i.getBoundingClientRect().top))).size,overflow:document.documentElement.scrollWidth>innerWidth};}""")
        assert state['height'] <= 120 and state['tagline'] != 'none' and state['rows'] == 1 and not state['overflow'], (width, state)


def test_toast_stays_long_enough_to_read_and_while_hovered(audit_page):
    page, base, errors = audit_page
    waits = page.evaluate("""()=>{toast('짧은 안내');const a=toast.wait;toast('가'.repeat(80));const b=toast.wait;toast('가'.repeat(400));return [a,b,toast.wait];}""")
    assert waits == [6500, 12000, 15000], waits
    # 나타나는 효과를 끄고, 먼저 마우스를 올린 다음 짧게 닫기를 걸어 본다.
    page.emulate_media(reduced_motion='reduce')
    page.evaluate("toast('마우스를 올린 안내')")
    page.hover('#toast')
    page.evaluate('toast.schedule(50)')
    page.wait_for_timeout(300)
    assert page.locator('#toast').is_visible()
    page.mouse.move(0, 0)
    page.evaluate('toast.schedule(50)')
    page.wait_for_function("getComputedStyle(document.querySelector('#toast')).display==='none'")
