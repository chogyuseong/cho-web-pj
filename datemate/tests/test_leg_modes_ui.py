"""구간별 이동 수단 바꾸기: 실제 브라우저, 로컬 서버, 가상 장소 데모."""
from test_functional_audit import audit_page, generate


def longest_place_leg(page):
    return page.evaluate('selected.places.map((_,i)=>i).sort((a,b)=>selected.legs[b].minutes-selected.legs[a].minutes)[0]')


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def short_buttons(page, selector):
    return page.locator(selector).evaluate_all(
        'els=>els.filter(el=>el.getClientRects().length).filter(el=>el.getBoundingClientRect().height<43.5).map(el=>el.textContent)')


def test_change_one_leg_updates_schedule_card_map_and_undo(audit_page):
    page, base, errors = audit_page
    generate(page)
    original = page.evaluate('selected.id')
    index = longest_place_leg(page)
    before = page.evaluate('({finish:selected.finish,minutes:selected.legs.map(l=>l.minutes)})')
    lines = page.locator('#plan-detail .route-line')
    assert lines.nth(index).locator('.route-line-text').inner_text().endswith('· 도보 %d분 · 가상 추정' % before['minutes'][index])
    toggle = lines.nth(index).locator('.route-mode-toggle')
    assert toggle.inner_text() == '수단 바꾸기' and toggle.get_attribute('aria-expanded') == 'false'
    toggle.click()
    chooser = page.locator('#transport-chooser-%d' % index)
    assert toggle.get_attribute('aria-expanded') == 'true'
    assert chooser.locator('legend').inner_text().endswith('이동 수단')
    assert chooser.locator('button').all_inner_texts() == ['도보', '대중교통', '자동차', '자전거']
    assert chooser.locator('[aria-pressed=true]').inner_text() == '도보'
    assert page.locator('#plan-detail input[type=radio], #plan-detail .route-line-block select').count() == 0
    assert not short_buttons(page, '#plan-detail .route-line button, #plan-detail .transport-chooser button')
    chooser.get_by_role('button', name='자동차', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    after = page.evaluate('({finish:selected.finish,modes:selected.legs.map(l=>l.mode),minutes:selected.legs.map(l=>l.minutes)})')
    assert after['modes'][index] == 'car' and all(m == 'walk' for i, m in enumerate(after['modes']) if i != index)
    assert after['finish'] < before['finish']
    # 구간 줄, 상세의 종료 시각, 코스 카드 요약, 지도 범례, 안내 문구가 모두 새 값이다.
    text = page.locator('#plan-detail .route-line').nth(index).locator('.route-line-text').inner_text()
    assert text.endswith('· 자동차 %d분 · 가상 추정' % after['minutes'][index])
    assert after['finish'] in page.locator('#plan-detail .detail > .hint').first.inner_text()
    facts = page.locator('.plan-option-tabs [aria-pressed=true] .option-facts').inner_text()
    assert '도보·자동차' in facts and after['finish'] in facts
    assert '자동차' in page.locator('.map-legend').inner_text() and '도보' in page.locator('.map-legend').inner_text()
    assert '도보·자동차' in page.locator('.map-travel-mode').inner_text()
    notice = page.locator('.transport-notice').inner_text()
    assert notice.startswith('이 구간을 자동차로 바꿨어요. 이후 도착이') and f"{before['finish']} → {after['finish']}" in notice
    page.wait_for_function("document.getElementById('transport-live').textContent.startsWith('이 구간을 자동차로 바꿨어요')")
    assert page.evaluate('document.activeElement?.dataset.transportToggle') == str(index)
    # 비교 표는 구간 수를 적는다.
    if not page.locator('.comparison-details').evaluate('d=>d.open'):
        page.locator('.comparison-details summary').click()
    cells = page.locator('.option-comparison td:nth-child(3)').all_inner_texts()
    assert any('도보 2구간·자동차 1구간' in cell for cell in cells)
    page.get_by_role('button', name='수단 변경 되돌리기', exact=True).click()
    page.wait_for_function('(id)=>selected.id===id', arg=original)
    assert page.evaluate('selected.legs.every(l=>l.mode==="walk")')
    assert page.locator('.transport-notice').count() == 0
    assert page.locator('#plan-detail .route-line').nth(index).locator('.route-line-text').inner_text().endswith('· 도보 %d분 · 가상 추정' % before['minutes'][index])


def test_bulk_change_mobile_layout_and_shared_view_has_no_buttons(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 900})
    generate(page)
    original = page.evaluate('selected.id')
    bulk = page.locator('#plan-detail .transport-bulk')
    bulk.locator('summary').click()
    for width in (360, 430):
        page.set_viewport_size({'width': width, 'height': 900})
        page.locator('#plan-detail .route-mode-toggle').first.click()
        assert no_overflow(page), width
        assert not short_buttons(page, '#plan-detail .route-line button, #plan-detail .transport-chooser button, #plan-detail .transport-bulk summary')
        # 수단 4개는 2열 균등 그리드다.
        boxes = page.locator('#transport-chooser-0 button').evaluate_all('els=>els.map(el=>el.getBoundingClientRect()).map(r=>[Math.round(r.left),Math.round(r.width)])')
        assert len({left for left, _ in boxes}) == 2 and max(w for _, w in boxes) - min(w for _, w in boxes) <= 1
        page.locator('#plan-detail .route-mode-toggle').first.click()
        assert page.locator('#transport-chooser-0').count() == 0
    bulk.get_by_role('button', name='대중교통', exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    assert page.evaluate('selected.legs.every(l=>l.mode==="transit") && selected.conditions.transport==="transit"')
    assert all('· 대중교통 ' in line for line in page.locator('#plan-detail .route-line-text').all_inner_texts())
    assert page.locator('.transport-notice').inner_text().startswith('모든 구간을 대중교통으로 바꿨어요.')
    assert no_overflow(page)
    # 공유 화면은 보기 전용: 수단 바꾸기 버튼이 없고 공유 응답에 구간 자료가 없다.
    url = page.evaluate("api('/plans/'+selected.id+'/shares',{}).then(r=>r.url)")
    page.goto(base + url)
    page.wait_for_function("document.querySelectorAll('#shared-places article').length>0")
    assert page.locator('.route-mode-toggle, .transport-chooser, .transport-bulk').count() == 0
    assert '수단 바꾸기' not in page.locator('body').inner_text()
