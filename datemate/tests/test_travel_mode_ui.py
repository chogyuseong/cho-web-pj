"""데이트/여행 스위치가 조건 기본값도 바꾼다(2026-11-25 사용자 결정 '여행 기본 조건 적용', static/header-mode.js TRIP_DEFAULTS).

- 여행: 10:00~20:00 · 장소 5곳 · 구간 이동 60분 · 장소당 75분 · 식사 포함. 데이트로 돌아가면 처음 값으로.
- 사용자가 직접 바꾼 칸은 어느 쪽으로도 건드리지 않는다.
- 이 기본값 변경은 '사용자가 고른 조건'(FormState.edited, 자연어 해석보다 우선)으로 세지 않는다.
- 여행 모드로 만든 코스는 그 값으로 서버에 간다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)

FIELDS = "['start','end','count','max_leg','stay_minutes'].map(n=>form.elements[n].value).concat([form.elements.include_meal.checked])"


def switch(page, mode):
    page.locator(f'#mode-switch [data-mode={mode}]').click()
    page.wait_for_function(f"document.querySelector('#mode-switch [data-mode={mode}]').getAttribute('aria-pressed')==='true'")


def test_travel_sets_trip_defaults_and_date_restores_them(audit_page):
    page, base, errors = audit_page
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    page.goto(base + '/', wait_until='networkidle')
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
    # 내일 날짜로 둬 '오늘 10시 지남' 예외를 피한다.
    page.evaluate("""()=>{const d=new Date();d.setDate(d.getDate()+1);form.elements.visit_date.value=d.toISOString().slice(0,10);}""")
    date_values = page.evaluate(FIELDS)
    edited_before = page.evaluate('[...FormState.edited].sort()')
    switch(page, 'travel')
    assert page.evaluate(FIELDS) == ['10:00', '20:00', '5', '60', '75', True]
    assert page.evaluate('[...FormState.edited].sort()') == edited_before
    assert '하루 여행에 맞췄어요' in page.locator('#toast').inner_text()
    switch(page, 'date')
    assert page.evaluate(FIELDS) == date_values
    # 직접 바꾼 칸(장소 수)은 그대로 둔다.
    # (장소 수 칸은 '상세 조건' 접기 안이라, 사용자가 고를 때와 같은 change 이벤트를 직접 보낸다.)
    page.evaluate("form.elements.count.value='2';form.elements.count.dispatchEvent(new Event('change',{bubbles:true}))")
    switch(page, 'travel')
    values = page.evaluate(FIELDS)
    assert values[2] == '2' and values[0] == '10:00' and values[3] == '60', values
    switch(page, 'date')
    assert page.evaluate("form.elements.count.value") == '2'
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")


def test_travel_course_uses_the_trip_values(audit_page):
    page, base, errors = audit_page
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
    switch(page, 'travel')
    generate(page)
    wait_for_selected_detail(page)
    sent = page.evaluate('selected.conditions')
    assert sent['max_leg'] == 180 or sent['max_leg'] == 60  # generate() 는 max_leg 를 180 으로 직접 넣는다(테스트 도우미)
    assert sent['stay_minutes'] == 75 and sent['include_meal'] is True, sent
    assert '여행' in page.locator('#results-title').inner_text()
    page.evaluate("try{localStorage.removeItem('datemate-mode')}catch{}")
