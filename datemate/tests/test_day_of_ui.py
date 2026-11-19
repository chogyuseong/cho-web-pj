"""약속 당일 도구(static/day-of.js): 마지막 출발 시각(24), 한 곳씩 크게 보기(39), 현장용 일정 복사(43)."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_last_departure_note_cases(audit_page):
    page, _, _ = audit_page
    notes = page.evaluate("""()=>{
      const base=(extra)=>Object.assign({conditions:{end:'21:00',return_home:true},places:[{name:'a'},{name:'b'}],
        legs:[{minutes:10},{minutes:12},{minutes:30,status:'estimated'}],timeline:[{departure:'18:00'},{departure:'20:00'}]},extra);
      return [
        lastDepartureNote(base({})),
        lastDepartureNote(base({timeline:[{departure:'18:00'},{departure:'20:45'}]})),
        lastDepartureNote(base({legs:[{minutes:10},{minutes:12},{minutes:null}]})),
        lastDepartureNote(base({conditions:{end:'21:00',return_home:false},legs:[{minutes:10},{minutes:12}]})),
      ];
    }""")
    assert notes[0] == '종료 21:00에 맞추려면 마지막 장소에서 늦어도 20:30에 출발해야 해요(귀가 30분 · 추정). 지금 계획은 20:00 출발 · 여유 30분.'
    assert notes[1].endswith('지금 계획(20:45 출발)은 15분 늦어요.')
    assert '귀가 시간을 몰라' in notes[2]
    assert notes[3] == '종료 21:00 기준 · 귀가를 정하지 않아 마지막 장소를 21:00까지 마치면 돼요(지금 계획은 20:00에 마침).'


def test_step_view_and_field_itinerary_work_offline_on_a_phone(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.set_viewport_size({'width': 390, 'height': 844})
    tools = page.locator('#plan-detail .day-of-tools')
    assert '종료' in tools.locator('.last-departure').inner_text()
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.fieldText=text;}}})")
    page.context.set_offline(True)
    try:
        tools.get_by_role('button', name='현장용 일정 복사').click()
        page.wait_for_function('!!window.fieldText')
    finally:
        page.context.set_offline(False)
    text = page.evaluate('window.fieldText')
    names = page.evaluate('selected.places.map(p=>p.name)')
    times = page.evaluate("selected.timeline.map(t=>t.arrival+'~'+t.departure)")
    assert all(f'{i + 1}. {t} {n}' in text for i, (t, n) in enumerate(zip(times, names)))
    assert '/shared#' not in text, '링크를 만들지 않는다(서버 요청 없음)'
    tools.get_by_role('button', name='한 곳씩 크게 보기').click()
    dialog = page.locator('#dialog')
    assert dialog.locator('.step-name').inner_text() == names[0] and '1 / ' in dialog.locator('.step-count').inner_text()
    assert dialog.get_by_role('button', name='← 이전').is_disabled()
    dialog.get_by_role('button', name='다음 →').click()
    assert dialog.locator('.step-name').inner_text() == names[1]
    assert dialog.get_by_role('link', name='지도에서 열기 ↗').count() == 1
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')
