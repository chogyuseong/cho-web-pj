"""결과 화면 축제 카드의 「+ 내 코스에 추가」 화면 흐름(static/festivals.js addSlot → experience.js showDraft → draft-apply).

실제 장소로 만든 코스를 저장해 두고 링크(?plan=)로 연 뒤, 축제 카드의 단추 → 미리보기 → 확정까지 간다.
확정 뒤 타임라인·지도·오른쪽 요약·코스 카드·카톡 일정 글이 새 코스(축제 포함)로 바뀌는지, 390/1440 폭에서 가로로 넘치지 않는지 본다.
외부 축제 API 는 부르지 않는다: 화면 쪽 /api/festivals 는 가짜 응답, 서버 쪽은 같은 내용을 캐시에 넣어 둔다(test_festival_add.listed).
"""
from test_festival_add import FESTIVAL_ID, VENUE, base_conditions, base_plan, festival_row, listed  # noqa: F401
from test_functional_audit import audit_page, wait_for_selected_detail  # noqa: F401
from app import store

ROWS = [festival_row(),
        festival_row(id='점검 이름만 축제:2026-10-01', title='점검 이름만 축제'),
        festival_row(id='880300', title='점검 좌표 없는 축제', lat=None, lon=None)]


def route_festivals(page):
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=ROWS, total_matches=3,
                                                                          truncated=False, message='점검 자료')))
    page.route('**/api/festivals/*/detail', lambda route: route.fulfill(json=dict(status='available', fee='무료', hours='14:00~20:00',
                                                                                 place=None, checked_at='2026-10-24', message='')))


def open_saved(page, base, plan):
    session = next(c['value'] for c in page.context.cookies() if c['name'] == 'dm_session')
    saved = store.save_plan(plan, store.owner_of(session))
    page.goto(f"{base}/?plan={saved['id']}", wait_until='networkidle')
    page.wait_for_function('selected?.id&&document.querySelectorAll("#festival-results .festival-card").length===3')
    wait_for_selected_detail(page)
    return saved


def card(page, title):
    return page.locator('#festival-results .festival-card', has_text=title)


def test_add_a_festival_to_the_course(audit_page, listed):  # noqa: F811
    page, base, errors = audit_page
    listed('14:00~20:00', rows=ROWS)
    route_festivals(page)
    original = open_saved(page, base, base_plan(base_conditions()))
    target = card(page, '점검 등축제')
    add = target.get_by_role('button', name='점검 등축제 내 코스에 추가')
    assert add.inner_text() == '+ 내 코스에 추가' and add.is_enabled()
    # 「이 축제 주변 코스 추천받기」는 그대로 있다.
    assert target.get_by_role('button', name='이 축제 주변 코스 추천받기', exact=True).count() == 1
    # 운영 시간을 받을 수 없는 축제(관광공사 번호 없음)·좌표 없는 축제는 단추 대신 까닭.
    assert card(page, '점검 이름만 축제').locator('.festival-add-button').count() == 0
    assert '운영 시간 정보를 받을 수 없는 축제라 내 코스에 넣을 수 없어요.' in card(page, '점검 이름만 축제').inner_text()
    assert '내 코스에 추가를 할 수 없어요' in card(page, '점검 좌표 없는 축제').inner_text()
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
    add.click()
    dialog = page.locator('#dialog')
    dialog.get_by_role('button', name='이 변경안으로 확정').wait_for()
    text = dialog.inner_text()
    assert '변경 전후를 확인해 주세요' in text and '‘점검 등축제’ 축제를 넣고' in text and '축제 요금은 비용에 넣지 않았어요' in text
    note = dialog.locator('.festival-change-note')
    assert note.inner_text() == '‘점검 등축제’ 축제를 일정에 넣을 수 있게 됐어요(코스 끝, 14:00~15:00).'
    rows = {r.locator('th').inner_text(): r.locator('td').all_inner_texts() for r in dialog.locator('tr').all()}
    assert rows['축제 방문'] == ['없음', '→ 코스 끝 14:00~15:00']
    assert rows['종료 시간'] == [original['finish'], '→ 15:00'] and '총 도보' in rows
    assert dialog.locator('.path-text').inner_text().endswith('→ 축제 · 점검 등축제')
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
    dialog.get_by_role('button', name='이 변경안으로 확정').click()
    page.wait_for_function(f"selected?.id&&selected.id!=='{original['id']}'&&selected.festival_visit?.position==='last'")
    wait_for_selected_detail(page)
    # 타임라인: 마지막 장소 뒤 축제 칸, 행사장으로 '가서'(돌아오지 않는다).
    visit = page.locator('#plan-detail .festival-visit')
    assert visit.count() == 1
    assert '14:00~15:00 축제 · 점검 등축제' in visit.inner_text() and '행사장으로 가서 축제로' in visit.inner_text()
    assert page.locator('#plan-detail .undo-actions button').inner_text() == '교체 되돌리기'
    # 지도: 행사장(축제 좌표)으로 가는 선과 진한 축제 표시.
    assert page.evaluate(f"planSegments(selected).some(s=>s.to.lat==={VENUE['lat']}&&s.to.lon==={VENUE['lon']})")
    assert page.evaluate("festivalMapItems(selected).filter(f=>festivalInCourse(selected,f)).length") == 1
    # 코스 카드·오른쪽 요약·코스 탭이 새 코스를 가리킨다.
    assert '‘점검 등축제’ 14:00~15:00 축제로 마무리하는 코스' in page.locator('#results .plan-card').inner_text()
    assert page.evaluate('plans.length===1&&plans[0].id===selected.id')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.wait_for_function("document.querySelector('.plan-rail-summary [data-stat=time] .rail-stat-note')?.textContent.includes(selected.finish)")
    assert page.evaluate("selected.finish") == '15:00'
    # 카톡 일정 글과 현장 일정에도 축제 줄.
    assert '14:00 축제 · 점검 등축제' in page.evaluate("kakaoItineraryText(selected,'')")
    assert '14:00~15:00 축제 · 점검 등축제 (운영 시간에 맞춰 마무리)' in page.evaluate('fieldItineraryText(selected)')
    # 같은 코스에는 더 넣을 수 없다 — 단추는 비활성, 까닭을 적는다.
    page.wait_for_function("document.querySelector('.festival-add-button')?.disabled")
    assert '이미 지금 코스에 들어 있는 축제예요.' in target.inner_text()
    for width in (390, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
    # 되돌리면 원래 코스로 돌아가고 단추가 다시 켜진다.
    page.locator('#plan-detail .undo-actions button').click()
    page.wait_for_function(f"selected?.id==='{original['id']}'")
    wait_for_selected_detail(page)
    assert page.locator('#plan-detail .festival-visit').count() == 0
    page.wait_for_function("!document.querySelector('.festival-add-button')?.disabled")


def test_refusal_is_shown_in_plain_words(audit_page, listed):  # noqa: F811
    page, base, errors = audit_page
    listed('20:00~22:00', rows=ROWS)
    route_festivals(page)
    open_saved(page, base, base_plan(base_conditions()))
    card(page, '점검 등축제').get_by_role('button', name='점검 등축제 내 코스에 추가').click()
    page.wait_for_function("[...document.querySelectorAll('.toast,[role=status],[role=alert]')].some(n=>n.textContent.includes('넣을 자리가 없어요'))")
    assert not page.locator('#dialog').evaluate('d=>d.open')


def test_button_is_off_without_a_real_course(audit_page):  # noqa: F811
    page, base, errors = audit_page
    route_festivals(page)
    from test_functional_audit import generate
    generate(page)
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    add = card(page, '점검 등축제').locator('.festival-add-button')
    assert add.is_disabled() and '가상 장소 시연 코스에는 실제 축제를 넣을 수 없어요.' in card(page, '점검 등축제').inner_text()
    # 코스가 없으면(조건 화면으로 돌아가 결과를 비운 경우) 단추는 꺼지고 까닭을 적는다.
    page.evaluate('selected=null;renderDetail()')
    assert add.is_disabled() and '코스를 먼저 만들면' in card(page, '점검 등축제').inner_text()
