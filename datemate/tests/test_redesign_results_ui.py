"""리디자인 3단계(2026-11-24, 사용자 가이드 datemate_2026.md §2.5 스플릿 뷰 코스 결과)를 실제 화면에서 눌러 본다.

1. 코스 탭: 이름 '안 N · {서버 option_purpose}', 1안 대비 델타 배지(도보·예산·이동). 배지 값은 코스 JSON 에서 따로 계산한 값과 같아야 하고,
   차이가 0 이거나 값을 모르면 배지가 없다(static/plan-results.js optionDeltas).
2. '혹시 늦어지셨나요?' 알약(정시·+15·+30·+60, 2026-11-25 시안): 고르면 GET /api/plans/{id}/delay-check?index=0&minutes=N 결과를 장소 칸에 겹치고, 끄면 원래대로.
   코스 탭을 바꾸면 새 코스로 다시 계산한다(static/delay-check.js delaySim*).
3. 일정 카드 → 지도: 「코스 지도에서 보기」가 지도 표시를 강조하고 그 위치로 옮긴다(공개 지도 Leaflet·가짜 네이버 SDK 모두, static/maps.js).
4. 오른쪽 패널 요약·공유: 데스크톱만, 값은 선택한 코스 그대로, 공유 단추는 공유 구역과 같은 함수(static/plan-results.js planRailSummary).
"""
import os
from pathlib import Path

import pytest

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401
from test_popup_map_ui import NAVER_STUB

SMALL_BUTTONS = '''()=>[...document.querySelectorAll('.results-area button, #plan-map-rail button')].filter(el=>el.getClientRects().length&&!el.closest('.leaflet-container'))
  .filter(el=>el.getBoundingClientRect().height<43.5).map(el=>({text:el.textContent.trim().slice(0,30),height:el.getBoundingClientRect().height}))'''

# 새 배지·요약 글자의 크기와 대비(바탕을 부모까지 겹쳐 계산, tests/test_readability_ui.py 와 같은 방식).
NEW_TEXT = '''sel=>{const rgba=v=>(v.match(/[\\d.]+/g)||[]).map(Number);
  const bg=el=>{let out=[255,255,255];const ps=[];for(let p=el;p;p=p.parentElement)ps.unshift(p);
    for(const p of ps){const c=rgba(getComputedStyle(p).backgroundColor);const a=c[3]??1;out=out.map((v,i)=>(c[i]??255)*a+v*(1-a));}return out;};
  const lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
  return [...document.querySelectorAll(sel)].filter(el=>el.getClientRects().length&&el.textContent.trim()).map(el=>{const s=getComputedStyle(el),b=bg(el),f=rgba(s.color);
    const l1=lum(f),l2=lum(b);return {text:el.textContent.trim(),size:parseFloat(s.fontSize),contrast:(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05)};});}'''


def save(page, name):
    folder = os.getenv('DATEMATE_UI_ARTIFACT_DIR')
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name))


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def known_walking(p):
    legs = list(p.get('legs') or [])
    if (p.get('festival_visit') or {}).get('leg'):
        legs.append(p['festival_visit']['leg'])
    return p['walking'] if number(p.get('walking')) and all(number(leg.get('walking')) for leg in legs) else None


def known_travel(p):
    legs = p.get('legs') or []
    summary = (p.get('decision_summary') or {}).get('travel_minutes')
    if number(summary):
        return summary
    return sum(leg['minutes'] for leg in legs) if legs and all(number(leg.get('minutes')) for leg in legs) else None


def known_budget(p):
    total = p.get('total')
    return total if total and all(number(v) for v in total) and not p.get('unknown') else None


def sign(value):
    return '+' if value > 0 else '−'


def won_delta(value):
    amount = abs(value)
    text = f'{amount / 10000:.1f}'.removesuffix('.0') + '만원' if amount >= 1000 else f'{amount:,}원'
    return sign(value) + text


def expected_deltas(p, base):
    out = {}
    walk = known_walking(p), known_walking(base)
    if None not in walk and walk[0] != walk[1]:
        out['walk'] = f'도보 {sign(walk[0] - walk[1])}{abs(walk[0] - walk[1])}분'
    a, b = known_budget(p), known_budget(base)
    if a and b:
        high, low = a[1] - b[1], a[0] - b[0]
        if high and not (low and (low > 0) != (high > 0)):
            out['budget'] = '예산 ' + won_delta(high)
    travel = known_travel(p), known_travel(base)
    if None not in travel and travel[0] != travel[1]:
        out['travel'] = f'이동 {sign(travel[0] - travel[1])}{abs(travel[0] - travel[1])}분'
    return out


TAB_BADGES = '''()=>[...document.querySelectorAll('#results .plan-option-tabs > button')].map(tab=>({
  label:tab.querySelector('.option-label').firstChild.textContent,purpose:tab.querySelector('.option-purpose')?.textContent||'',
  base:!!tab.querySelector('.delta-base'),hidden:tab.querySelector('.option-deltas .visually-hidden')?.textContent||'',
  badges:Object.fromEntries([...tab.querySelectorAll('.delta-badge[data-delta]')].map(b=>[b.dataset.delta,b.firstChild.textContent])),
  difference:tab.querySelector('.option-difference')?.textContent||null}))'''


def test_tab_names_and_delta_badges_follow_the_course_json(audit_page):
    page, base, errors = audit_page
    generate(page)
    plans = page.evaluate('plans')
    tabs = page.evaluate(TAB_BADGES)
    assert len(tabs) == len(plans) >= 2
    for i, (tab, plan) in enumerate(zip(tabs, plans)):
        assert tab['label'] == f'안 {i + 1}', tab
        assert tab['purpose'] == ('· ' + plan['option_purpose'] if plan.get('option_purpose') else ''), tab
        if i == 0:
            # 1안은 '비교 기준' 배지 하나, 차이 설명 줄은 없다.
            assert tab['base'] and tab['badges'] == {} and tab['difference'] is None, tab
        else:
            assert not tab['base'] and tab['badges'] == expected_deltas(plan, plans[0]), (tab, plan.get('walking'), plan.get('total'))
            assert tab['difference'] and '이동 +' not in tab['difference'] and '이동 −' not in tab['difference'], tab
            if tab['badges']:
                assert tab['hidden'] == '안 1 대비 ', tab
    assert any(tab['badges'] for tab in tabs[1:]), '데모 코스는 1안과 수치가 달라 배지가 하나 이상 있어야 한다'

    # 경계: 값을 모르거나 같으면 배지가 없다. 예산은 상한끼리, 범위가 서로를 감싸면 없다.
    cases = page.evaluate('''()=>{const b=structuredClone(plans[0]);const legs=b.legs.map(l=>({...l,walking:5,minutes:10}));
      Object.assign(b,{walking:5*legs.length,total:[20000,40000],unknown:[],legs,decision_summary:{travel_minutes:10*legs.length}});
      delete b.festival_visit;
      const v=patch=>Object.assign(structuredClone(b),patch),out={};
      const d=p=>Object.fromEntries(optionDeltas(p,b).map(x=>[x.kind,x.text]));
      out.same=d(v({}));
      out.cheaper=d(v({total:[10000,26000]}));
      out.small=d(v({total:[20500,40500]}));
      out.wraps=d(v({total:[10000,50000]}));
      out.unknownCost=d(v({total:[10000,20000],unknown:['통행료']}));
      const noWalk=v({walking:0,total:[10000,20000]});noWalk.legs[0].walking=null;out.unknownWalk=d(noWalk);
      const noTravel=v({decision_summary:{}});noTravel.legs[0].minutes=null;noTravel.walking=1;out.unknownTravel=d(noTravel);
      out.more=d(v({walking:b.walking+7,decision_summary:{travel_minutes:b.decision_summary.travel_minutes+12}}));
      return out;}''')
    assert cases['same'] == {}
    assert cases['cheaper'] == {'budget': '예산 −1.4만원'}
    assert cases['small'] == {'budget': '예산 +500원'}
    assert cases['wraps'] == {}
    assert cases['unknownCost'] == {}
    assert cases['unknownWalk'] == {'budget': '예산 −2만원'}
    legs = page.evaluate('plans[0].legs.length')
    assert cases['unknownTravel'] == {'walk': f'도보 −{legs * 5 - 1}분'}
    assert cases['more'] == {'walk': '도보 +7분', 'travel': '이동 +12분'}

    # 탭을 바꿔도(선택 표시만 다시 그림) 배지는 그대로다.
    page.locator('#results .plan-option-tabs > button').nth(1).click()
    wait_for_selected_detail(page)
    assert page.evaluate(TAB_BADGES) == tabs
    for row in page.evaluate(NEW_TEXT, '#results .delta-badge'):
        assert row['size'] >= 14 and row['contrast'] >= 4.5, row
    save(page, 'redesign-tabs-desktop.png')


def delay_rows(page):
    return page.evaluate('''()=>[...document.querySelectorAll('#plan-detail .stop')].map(stop=>({
      start:stop.querySelector('.delay-sim-start')?.textContent||null,shift:stop.querySelector('.delay-sim-shift')?.textContent||null,
      badges:[...stop.querySelectorAll('.delay-sim-badge')].map(b=>[b.dataset.kind,b.textContent])}))''')


def check(page, plan_id, minutes=30):
    return page.evaluate("([id,m])=>api(`/plans/${encodeURIComponent(id)}/delay-check?index=0&minutes=${m}`)", [plan_id, minutes])


def pill(page, minutes):
    # 2026-11-25 HTML 시안: '+30분 늦어지면?' 켜고 끄는 단추 → '혹시 늦어지셨나요?' 정시 · +15 · +30 · +60 알약(0 = 정시 = 끄기).
    return page.locator(f'#plan-detail .delay-sim-pill[data-minutes="{minutes}"]')


def test_delay_toggle_marks_each_stop_and_turns_off_cleanly(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    toggle = pill(page, 30)
    # 일정(첫 장소 칸) 바로 위, 접힌 상자 '늦어지면 어디서 문제가 생길까?'는 그대로 있다.
    assert page.evaluate("""()=>{const bar=document.querySelector('#plan-detail .delay-sim'),stop=document.querySelector('#plan-detail .stop');
      return !!(bar.compareDocumentPosition(stop)&Node.DOCUMENT_POSITION_FOLLOWING)}""")
    assert page.locator('#plan-detail details.delay-check').count() == 1
    assert page.locator('#plan-detail .delay-sim-title').inner_text() == '혹시 늦어지셨나요?'
    assert page.locator('#plan-detail .delay-sim-pill').all_inner_texts() == ['정시', '+15분', '+30분', '+60분']
    assert pill(page, 0).get_attribute('aria-pressed') == 'true' and toggle.get_attribute('aria-pressed') == 'false'
    assert all(b['height'] >= 44 for b in page.locator('#plan-detail .delay-sim-pill').evaluate_all('l=>l.map(e=>e.getBoundingClientRect().toJSON())'))
    original = page.evaluate("[...document.querySelectorAll('#plan-detail .timeline-stamp strong')].map(s=>s.textContent)")

    # 키보드로 켠다(Space).
    toggle.focus()
    page.keyboard.press('Space')
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-sim-start').length>0", timeout=20000)
    assert toggle.get_attribute('aria-pressed') == 'true'
    data = check(page, page.evaluate('selected.id'))
    rows = [row for row in data['rows'] if not row.get('festival')]
    shown = delay_rows(page)
    for i, row in enumerate(rows):
        assert shown[i]['start'] == row['start'], (i, shown[i], row)
        assert shown[i]['shift'] == (f"+{row['shift']}분" if row['shift'] > 0 else '그대로' if row['shift'] == 0 else f"{-row['shift']}분 일찍")
        kinds = [kind for kind, _ in shown[i]['badges']]
        assert ('problem' in kinds) == (row['state'] == 'problem'), (shown[i], row)
        assert bool({'caution', 'info'} & set(kinds)) == (row['wait'] > 0), (shown[i], row)
    # 서버가 첫 문제에서 멈추면 그 뒤 장소는 '계산하지 않았어요'.
    for extra in shown[len(rows):]:
        assert extra['start'] is None and extra['badges'] == [['skipped', '앞에서 문제가 생겨 계산하지 않았어요']], extra
    status = page.locator('#plan-detail .delay-sim-status').inner_text()
    assert status.startswith('30분 늦'), status
    assert page.locator('#plan-detail .delay-sim-help').is_hidden()
    assert page.locator('#plan-detail .delay-sim-basis').inner_text() == data['basis']
    # 원래 시각 도장은 그대로 남는다(지우지 않고 아래에 덧붙임).
    assert page.evaluate("[...document.querySelectorAll('#plan-detail .timeline-stamp strong')].map(s=>s.textContent)") == original
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    for row in page.evaluate(NEW_TEXT, '#plan-detail .delay-sim-badge, #plan-detail .delay-sim-start, #plan-detail .delay-sim-shift, #plan-detail .delay-sim-status'):
        assert row['size'] >= 14 and row['contrast'] >= 4.5, row
    page.locator('#plan-detail .delay-sim').scroll_into_view_if_needed()
    save(page, 'redesign-delay-mobile.png')

    # 코스 탭을 바꾸면 켜진 채로 새 코스로 다시 계산한다.
    page.locator('#results .plan-option-tabs > button').nth(1).click()
    wait_for_selected_detail(page)
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-sim-start').length>0", timeout=20000)
    assert pill(page, 30).get_attribute('aria-pressed') == 'true'
    second = check(page, page.evaluate('selected.id'))
    starts = [row['start'] for row in second['rows'] if not row.get('festival')]
    assert [row['start'] for row in delay_rows(page)][:len(starts)] == starts

    # 다른 분(+60분)을 고르면 그 분으로 다시 계산한다.
    pill(page, 60).click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-sim-status').textContent.startsWith('60분')", timeout=20000)
    sixty = check(page, page.evaluate('selected.id'), 60)
    assert [row['start'] for row in delay_rows(page)][:1] == [row['start'] for row in sixty['rows'] if not row.get('festival')][:1]
    assert pill(page, 60).get_attribute('aria-pressed') == 'true' and pill(page, 30).get_attribute('aria-pressed') == 'false'

    # 정시로 돌리면 겹친 것이 모두 사라지고 처음 모습으로 돌아간다.
    pill(page, 0).click()
    assert pill(page, 60).get_attribute('aria-pressed') == 'false' and pill(page, 0).get_attribute('aria-pressed') == 'true'
    assert page.locator('#plan-detail :is(.delay-sim-time,.delay-sim-badges)').count() == 0
    assert page.locator('#plan-detail .delay-sim-status').inner_text() == ''
    assert page.locator('#plan-detail .delay-sim-help').is_visible()
    # 꺼진 상태는 다른 코스로 가도 꺼진 채다.
    page.locator('#results .plan-option-tabs > button').nth(0).click()
    wait_for_selected_detail(page)
    assert pill(page, 0).get_attribute('aria-pressed') == 'true'
    assert page.locator('#plan-detail .delay-sim-time').count() == 0


def test_delay_badges_use_the_server_judgement(audit_page):
    """서버 응답을 정해 두고(문제·휴게·개점 대기·자료 없음·계산 안 함·축제) 배지 글자를 확인한다."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    generate(page)
    names = page.evaluate('selected.places.map(p=>p.name)')
    assert len(names) >= 3
    # 1번 장소: 휴게 시간 10:00~11:00 이 끝나기를 기다림. 2번: 마지막 입장 문제. 3번 이후: 서버가 계산하지 않음.
    page.evaluate("selected.places[0].breaks=[[600,660]];selected.places[1].hours=[540,1320];")
    row = lambda name, **kw: dict(dict(name=name, arrival='10:40', start='11:00', departure='12:00', wait=20, shift=30, stay=60,
                                       stay_assumed=False, state='ok', missing=[]), **kw)
    fake = dict(status='problem', index=0, delay=30, basis='테스트 근거 문장이에요.', pending=[], finish=None, original_finish='18:00',
                end='22:00', estimated_legs=[], no_last_entry=[], recovery=None,
                first_problem=dict(place=names[1], time='12:40', reason='마지막 입장 시간 초과', kind='last_entry', limit='12:30', over=10),
                rows=[row(names[0]),
                      row(names[1], arrival='12:30', start='12:40', departure='13:40', wait=10, shift=25, state='problem',
                          reason='마지막 입장 시간 초과', limit='12:30', over=10)])
    page.route('**/delay-check?index=0&minutes=30', lambda route: route.fulfill(json=fake))
    pill(page, 30).click()
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-sim-badge').length>=3")
    shown = delay_rows(page)
    assert shown[0]['badges'] == [['caution', '휴게 시간 10:00~11:00 · 20분 기다림']], shown[0]
    assert shown[1]['badges'] == [['problem', '마지막 입장 12:30 · 10분 넘김'], ['info', '개점·휴게 대기 10분']], shown[1]
    assert all(s['badges'] == [['skipped', '앞에서 문제가 생겨 계산하지 않았어요']] for s in shown[2:]), shown
    status = page.locator('#plan-detail .delay-sim-status')
    assert status.inner_text().startswith(f'30분 늦으면 {names[1]}에서 처음 문제가 생겨요(마지막 입장 시간 초과).')
    assert 'is-problem' in status.get_attribute('class')
    assert '라스트오더' not in page.locator('#plan-detail').inner_text()
    page.locator('#plan-detail .delay-sim').scroll_into_view_if_needed()
    save(page, 'redesign-delay-desktop.png')
    # 2026-11-25 Gemini Canvas 시안: 문제가 생기면 「대신 갈 곳 찾기」 → 접힌 '더 할 수 있는 것'과 지각 확인 상자를 같은 장소·같은 분으로 열고 확인한다.
    page.evaluate("document.querySelector('#plan-detail .plan-more').open=false")
    status.get_by_role('button', name='대신 갈 곳 찾기').click()
    page.wait_for_function("document.querySelector('#plan-detail .plan-more').open&&document.querySelector('#plan-detail details.delay-check').open")
    assert page.locator('#plan-detail .delay-check-form select').input_value() == '0'
    assert page.locator('#plan-detail .delay-check-form input').input_value() == '30'
    page.wait_for_function("document.querySelector('#plan-detail .delay-check-result').textContent.trim().length>0")
    assert names[1] in page.locator('#plan-detail .delay-check-result').inner_text()

    # 일정 종료 초과(kind 'end')·영업 종료·자료 없음.
    pill(page, 0).click()
    page.evaluate('delaySim.cache.clear()')
    fake.update(first_problem=dict(place='일정 종료', time='22:30', reason='정한 종료 시각을 넘겨요', kind='end', limit='22:00', over=30),
                rows=[row(names[0], wait=0, state='unchecked', missing=['영업시간', '휴무일']),
                      row(names[1], wait=0), row(names[2], wait=0, state='ok')])
    pill(page, 30).click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-sim-status').textContent.includes('종료 시간')")
    assert page.locator('#plan-detail .delay-sim-status').inner_text() == '30분 늦으면 일정이 22:30에 끝나 정한 종료 시간(22:00)보다 30분 늦어요.'
    # 종료 시각 문제는 바꿀 장소가 없어 「대신 갈 곳 찾기」가 없다.
    assert page.locator('#plan-detail .delay-sim-recover').count() == 0
    assert delay_rows(page)[0]['badges'] == [['unknown', '영업시간·휴무일 자료 없음 · 연다고 보고 계산']]
    pill(page, 0).click()
    page.evaluate('delaySim.cache.clear()')
    fake.update(first_problem=dict(place=names[0], time='11:00', reason='영업시간 밖 방문', kind='closing', limit='11:30', over=30),
                rows=[row(names[0], wait=0, state='problem', reason='영업시간 밖 방문', limit='11:30', over=30)])
    pill(page, 30).click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-sim-badge.is-problem')")
    assert delay_rows(page)[0]['badges'] == [['problem', '영업 종료 11:30 · 30분 모자람']]

    # 계산 실패: 켜진 채로 두지 않고 이유를 알린다.
    pill(page, 0).click()
    page.evaluate('delaySim.cache.clear()')
    page.unroute('**/delay-check?index=0&minutes=30')
    page.route('**/delay-check?index=0&minutes=30', lambda route: route.fulfill(status=400, json={'detail': '이 코스는 구간 이동 시간이 저장돼 있지 않아 다시 계산할 수 없어요.'}))
    pill(page, 30).click()
    page.wait_for_function("document.querySelector('#plan-detail .delay-sim-status').classList.contains('warning')")
    assert pill(page, 30).get_attribute('aria-pressed') == 'false' and pill(page, 0).get_attribute('aria-pressed') == 'true'
    assert '계산하지 못했어요' in page.locator('#plan-detail .delay-sim-status').inner_text()
    assert page.locator('#plan-detail .delay-sim-time').count() == 0


FOCUSED_CIRCLE = '''()=>{const c=document.querySelector('#plan-map-rail .route-stop-circle.is-focused, #plan-map-slot .route-stop-circle.is-focused');
  if(!c)return null;const box=c.getBoundingClientRect(),map=c.closest('.naver-plan-map').getBoundingClientRect();
  return {current:c.getAttribute('aria-current'),dx:Math.abs(box.x+box.width/2-(map.x+map.width/2)),dy:Math.abs(box.y+box.height/2-(map.y+map.height/2)),
    count:document.querySelectorAll('.route-stop-circle.is-focused').length};}'''


@pytest.mark.parametrize('width', [1440, 390])
def test_stop_card_moves_the_leaflet_map_to_its_pin(audit_page, width):
    page, base, errors = audit_page
    page.emulate_media(reduced_motion='reduce')
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    holder = '#plan-map-rail' if width > 800 else '#plan-map-slot'
    page.wait_for_function(f"document.querySelector('{holder} .plan-map')?.dataset.mapState==='leaflet'", timeout=20000)
    page.wait_for_timeout(300)
    stop = page.locator('#plan-detail .stop').nth(1)
    button = stop.get_by_role('button', name=page.evaluate("`2번 ${selected.places[1].name} 코스 지도에서 보기`"), exact=True)
    assert button.inner_text() == '코스 지도에서 보기'
    stop.scroll_into_view_if_needed()
    scroll_before = page.evaluate('scrollY')
    button.click()
    page.wait_for_function("!!document.querySelector('.route-stop-circle.is-focused')")
    page.wait_for_timeout(400)
    focused = page.evaluate(FOCUSED_CIRCLE)
    assert focused['current'] == 'true' and focused['count'] == 1, focused
    # 지도가 그 장소로 옮겨져 강조한 원이 지도 칸 가운데에 있다(합쳐진 원이면 확대 뒤 그 장소 원).
    assert focused['dx'] < 30 and focused['dy'] < 30, focused
    name = page.evaluate('selected.places[1].name')
    assert page.locator(f'{holder} .map-focus-status').inner_text() == f'2번 장소({name})를 지도 가운데에 표시했어요.'
    back = page.locator(f'{holder} .map-focus-back')
    if width > 800:
        # 데스크톱: 페이지는 그대로, 포커스는 누른 단추에 남고, 돌아가기 단추는 없다.
        assert page.evaluate('scrollY') == scroll_before
        assert page.evaluate("document.activeElement.classList.contains('stop-map-focus')")
        assert back.is_hidden()
        # 1440×900 패널에서는 지도가 이미 다 보여 패널을 넘기지 않는다(위의 코스 요약·탭이 그대로 보인다).
        assert page.evaluate("document.querySelector('#plan-map-rail .plan-map-card').scrollTop") == 0
        save(page, 'redesign-card-to-map-desktop.png')
    else:
        # 휴대폰: 지도(일정 뒤)로 내려가고 '2번 일정으로 돌아가기'에 포커스. 누르면 그 장소 제목으로 돌아온다.
        assert page.evaluate(f"""()=>{{const r=document.querySelector('{holder} .naver-plan-map').getBoundingClientRect();return r.top>=0&&r.top<innerHeight*0.6}}""")
        assert page.evaluate("document.activeElement.classList.contains('map-focus-back')")
        assert back.inner_text() == '2번 일정으로 돌아가기'
        save(page, 'redesign-card-to-map-mobile.png')
        back.click()
        page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
        assert page.evaluate("[...document.querySelectorAll('#plan-detail .stop')].indexOf(document.activeElement.closest('.stop'))") == 1
    # 다른 장소를 고르면 강조가 옮겨 간다(강조는 한 곳).
    page.locator('#plan-detail .stop').nth(0).locator('.stop-map-focus').click()
    page.wait_for_function("document.querySelectorAll('.route-stop-circle.is-focused').length===1")
    page.wait_for_timeout(300)
    assert page.evaluate(FOCUSED_CIRCLE)['dx'] < 30


NAVER_STUB_WITH_PAN = NAVER_STUB.replace(
    "Map:function(){this.fitBounds=()=>{window.__fits++;};this.destroy=()=>{};},",
    "Map:function(){this.fitBounds=()=>{window.__fits++;};this.destroy=()=>{};window.__pans=[];this.getZoom=()=>14;"
    "this.panTo=c=>window.__pans.push(['pan',c.lat(),c.lng()]);this.setCenter=c=>window.__pans.push(['center',c.lat(),c.lng()]);},")


@pytest.mark.parametrize('width', [1440, 390])
def test_stop_card_moves_the_naver_map_to_its_pin(audit_page, width):
    assert NAVER_STUB_WITH_PAN != NAVER_STUB
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.evaluate(NAVER_STUB_WITH_PAN)
    generate(page)
    holder = '#plan-map-rail' if width > 800 else '#plan-map-slot'
    page.wait_for_function(f"document.querySelector('{holder} .plan-map')?.dataset.mapState==='naver'", timeout=20000)
    markers = "window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes('route-stop-marker'))"
    assert page.evaluate(f"{markers}.every(m=>!m.options.icon.content.includes('is-focused'))")
    page.locator('#plan-detail .stop').nth(2).locator('.stop-map-focus').click()
    page.wait_for_function(f"{markers}.some(m=>m.options.icon.content.includes('is-focused'))")
    lit = page.evaluate(f"{markers}.filter(m=>m.options.icon.content.includes('is-focused')).map(m=>({{html:m.options.icon.content,z:m.options.zIndex}}))")
    assert len(lit) == 1 and '>3</span>' in lit[0]['html'] and 'aria-current="true"' in lit[0]['html'] and lit[0]['z'] == 140, lit
    place = page.evaluate('[selected.places[2].lat,selected.places[2].lon]')
    assert page.evaluate('window.__pans.at(-1)') == ['pan', *place]
    # 동작 줄이기면 움직임 없이 바로 가운데로.
    page.emulate_media(reduced_motion='reduce')
    page.locator('#plan-detail .stop').nth(0).locator('.stop-map-focus').click()
    page.wait_for_function("window.__pans.at(-1)[0]==='center'")
    assert page.evaluate('window.__pans.at(-1)') == ['center', *page.evaluate('[selected.places[0].lat,selected.places[0].lon]')]
    assert page.evaluate(f"{markers}.filter(m=>m.options.icon.content.includes('is-focused')).length") == 1


def rail_values(page):
    return page.evaluate('''()=>{const box=document.querySelector('#plan-map-rail .plan-rail-summary');if(!box)return null;
      const value=k=>box.querySelector(`[data-stat=${k}] dd`).textContent.replace(/\\s+/g,' ').trim();
      return {budget:value('budget'),walk:value('walk'),time:value('time'),label:box.getAttribute('aria-label'),
        buttons:[...box.querySelectorAll('.rail-share button')].map(b=>[b.textContent,b.getAttribute('aria-label')])};}''')


def expected_rail(page):
    return page.evaluate('''()=>{const p=selected,n=plans.findIndex(x=>x.id===p.id)+1,w=knownWalking(p);
      return {budget:rangeLines(p.total).textContent.replace(/\\s+/g,' ').trim(),walk:w===null?'모름':w+'분',time:durationText(p.minutes),
        label:`코스 ${n} 요약과 공유`,buttons:[['공유 티켓 보기',`공유 티켓 보기 · 코스 ${n}`],['카톡용 일정 복사',`카톡용 일정 복사 · 코스 ${n}`]]};}''')


def test_rail_summary_and_share_on_desktop_only(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1440, 'height': 900})
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-rail-summary')")
    assert rail_values(page) == expected_rail(page)
    assert page.evaluate('durationText(250)') == '4시간 10분' and page.evaluate('durationText(45)') == '45분' and page.evaluate('durationText(120)') == '2시간'
    # 공유 구역과 같은 함수를 부른다(바꿔 끼운 함수가 불리면 같은 이름의 전역 함수를 부르는 것).
    page.evaluate("""()=>{window.__calls=[];const k=copyKakaoItinerary,s=copyPlanShare;
      window.copyKakaoItinerary=p=>{__calls.push(['kakao',p.id]);};window.copyPlanShare=p=>{__calls.push(['share',p.id]);};
      window.__restore=()=>{window.copyKakaoItinerary=k;window.copyPlanShare=s;};}""")
    rail = page.locator('#plan-map-rail .plan-rail-summary')
    rail.get_by_role('button', name='카톡용 일정 복사 · 코스 1', exact=True).click()
    # 2026-11-25 HTML 시안: 패널의 둘째 단추는 '공유 티켓 보기' — 티켓 창의 [공유 링크 복사]가 같은 함수(copyPlanShare)를 부른다.
    rail.get_by_role('button', name='공유 티켓 보기 · 코스 1', exact=True).click()
    ticket = page.locator('#dialog .plan-ticket')
    ticket.wait_for()
    assert ticket.locator('.ticket-badge').inner_text() == 'DATEMATE PASS'
    assert ticket.locator('.ticket-stops li').count() == page.evaluate('selected.places.length')
    ticket.get_by_role('button', name='공유 링크 복사', exact=True).click()
    page.wait_for_function('window.__calls.length===2')
    assert page.evaluate('__calls') == [['kakao', page.evaluate('selected.id')], ['share', page.evaluate('selected.id')]]
    page.evaluate('__restore()')
    # 실제 함수로 한 번: 공유 링크가 만들어져 일정 아래 공유 현황 줄이 바뀐다(같은 함수라 같은 결과).
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async t=>{window.copied=t;}}})")
    ticket.get_by_role('button', name='공유 링크 복사', exact=True).click()
    page.wait_for_function("window.copied?.includes('/shared')||window.copied?.includes('/s/')", timeout=10000)
    page.locator('#close-dialog').click()
    page.wait_for_function("document.querySelector('#plan-detail .share-status').textContent.includes('공유 링크 1개')", timeout=10000)
    # 공유 구역의 같은 이름 단추는 그대로 하나씩(이름이 겹치지 않는다).
    assert page.get_by_role('button', name='공유 링크 복사', exact=True).count() == 1
    assert page.get_by_role('button', name='카톡용 일정 복사', exact=True).count() == 1
    # 패널 카드 안에 가로 넘침이 없다.
    assert page.evaluate("(c=>c.scrollWidth<=c.clientWidth)(document.querySelector('#plan-map-rail .plan-map-card'))")
    for row in page.evaluate(NEW_TEXT, '#plan-map-rail .plan-rail-summary :is(dt,dd)'):
        assert row['size'] >= 14 and row['contrast'] >= 4.5, row
    save(page, 'redesign-rail-desktop.png')

    # 코스 탭을 바꾸면 요약이 그 코스 값으로 바뀐다.
    page.locator('#results .plan-option-tabs > button').nth(1).click()
    wait_for_selected_detail(page)
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-rail-summary')?.getAttribute('aria-label')==='코스 2 요약과 공유'")
    assert rail_values(page) == expected_rail(page)

    # 장소를 바꾸면(새 코스) 요약도 새 코스 값.
    original = page.evaluate('selected.id')
    page.locator('#plan-detail .stop').nth(1).get_by_role('button', name='↻ 다른 장소로 바꾸기', exact=True).click()
    dialog = page.locator('#dialog')
    dialog.locator('[name=replacement_reason]').select_option('taste')
    dialog.get_by_role('button', name='이 장소로 교체', exact=True).first.click()
    page.wait_for_function('(id)=>selected.id!==id', arg=original)
    page.wait_for_function("document.querySelector('#plan-detail')?.dataset.planId===selected.id")
    assert rail_values(page) == expected_rail(page)

    # 휴대폰 폭: 오른쪽 패널이 숨고 요약은 어디에도 다시 만들지 않는다(중복 없음).
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map-card')")
    assert page.locator('.plan-rail-summary').count() == 0 and page.locator('#plan-map-rail').is_hidden()
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-rail-summary')")
    assert page.locator('.plan-rail-summary').count() == 1


@pytest.mark.parametrize('width', [375, 390, 1440])
def test_no_horizontal_overflow_and_touch_targets_with_everything_on(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    pill(page, 30).click()
    page.wait_for_function("document.querySelectorAll('#plan-detail .delay-sim-start').length>0", timeout=20000)
    page.locator('#plan-detail .stop').nth(1).scroll_into_view_if_needed()
    save(page, f'redesign-stop-{width}.png')
    page.locator('#plan-detail .stop').nth(1).locator('.stop-map-focus').click()
    page.wait_for_timeout(500)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
    assert not page.evaluate(SMALL_BUTTONS), page.evaluate(SMALL_BUTTONS)
    if width > 800:
        # 1440: 일정(왼쪽)과 지도 패널(오른쪽)이 나란히 선다.
        rail = page.locator('#plan-map-rail').bounding_box()
        results = page.locator('#results').bounding_box()
        assert rail['x'] >= results['x'] + results['width'] - 1
    else:
        assert page.locator('#plan-map-rail').is_hidden() and page.locator('.plan-rail-summary').count() == 0
    save(page, f'redesign-all-on-{width}.png')
