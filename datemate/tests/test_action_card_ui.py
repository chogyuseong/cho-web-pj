"""실행 카드(static/action-card.js): 확인 항목을 시점 순서(지금·전날 → 출발 전 → 도착 전 → 마무리)로 모은 체크리스트.
저장된 코스만 읽고 서버에 묻지 않는다. 체크 표시는 이 브라우저에만 남긴다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)

BASE = """(extra)=>Object.assign({
  id:'p1',
  conditions:{start:'11:00',end:'21:00',return_home:true},
  places:[{id:'a',name:'A'},{id:'b',name:'B',reservation:true}],
  timeline:[{arrival:'11:10',departure:'12:10'},{arrival:'12:30',departure:'13:30'}],
  legs:[{minutes:10,mode:'walk'},{minutes:20,mode:'car'},{minutes:30,mode:'car',status:'estimated'}],
  verification:{places:[{id:'a',coverage:{missing:['예약','가격']}},{id:'b',coverage:{missing:[]}}]}
},extra)"""


def items(page, extra='{}'):
    return page.evaluate(f'()=>actionCardItems(({BASE})({extra}))')


def test_items_follow_time_order(audit_page):
    page, _, _ = audit_page
    found = items(page)
    assert [i['when'] for i in found] == ['before', 'before', 'depart', 'arrive', 'finish']
    texts = [i['text'] for i in found]
    assert texts[0] == '1. A — 예약·가격 확인'
    assert texts[1] == '2. B 예약하기 (12:30 도착 기준)'
    assert texts[2] == '11:00 출발 · 1. A 11:10 도착 예정'
    assert texts[3] == '2. B 도착(12:30) 전 주차장 확인 · 주차비는 계산에 없어요'
    assert texts[4] == '늦어도 20:30에 2. B에서 귀가 출발 (종료 21:00)'
    assert len({i['id'] for i in found}) == len(found)


def test_items_without_verification(audit_page):
    page, _, _ = audit_page
    found = items(page, "{verification:undefined,places:[{id:'a',name:'A'},{id:'b',name:'B'}],conditions:{start:'11:00',end:'21:00',return_home:false},legs:[{minutes:10},{minutes:20}]}")
    assert [i['when'] for i in found] == ['depart', 'finish']
    assert found[-1]['text'] == '21:00까지 2. B 마치기'


def test_items_follow_the_festival(audit_page):
    page, _, _ = audit_page
    first = items(page, "{conditions:{start:'11:00',end:'21:00',return_home:false,festival:{title:'빛축제'}},festival_visit:{position:'first',title:'빛축제',arrival:'11:00',departure:'12:00'}}")
    texts = [i['text'] for i in first]
    assert '‘빛축제’ 개최·운영 시간 확인 (주최 측 안내)' in texts
    assert '11:00까지 빛축제 행사장 도착 (코스 시작)' in texts
    last = items(page, "{conditions:{start:'16:00',end:'22:00',return_home:true,festival:{title:'빛축제'}},festival_visit:{position:'last',title:'빛축제',arrival:'17:30',departure:'18:30'}}")
    assert last[-1]['text'] == '늦어도 21:30에 빛축제 행사장에서 귀가 출발 (종료 22:00)'
    assert any(i['text'] == '16:00 출발 · 1. A 11:10 도착 예정' for i in last)


def open_course(page, base):
    generate(page)
    wait_for_selected_detail(page)
    return page.evaluate('selected.id')


def test_course_screen_shows_the_card_and_remembers_checks(audit_page):
    page, base, errors = audit_page
    plan_id = open_course(page, base)
    card = page.locator('#plan-detail .action-card')
    assert card.count() == 1 and card.locator('h3').inner_text() == '할 일 순서'
    # '네 가지 확인'(execution-summary) 바로 위.
    assert page.evaluate("""()=>{const a=document.querySelector('#plan-detail .action-card'),e=document.querySelector('#plan-detail .execution-summary');
        return a.nextElementSibling===e;}""")
    boxes = card.locator('input[type=checkbox]')
    assert boxes.count() == len(page.evaluate('actionCardItems(selected)')) >= 2
    boxes.nth(0).check()
    page.goto(base + '/?plan=' + plan_id)
    wait_for_selected_detail(page)
    again = page.locator('#plan-detail .action-card input[type=checkbox]')
    assert again.nth(0).is_checked() and not again.nth(1).is_checked()
    assert not errors


def test_blocked_storage_still_works(audit_page):
    page, base, errors = audit_page
    page.add_init_script("Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new Error('blocked')}})")
    plan_id = open_course(page, base)
    page.goto(base + '/?plan=' + plan_id)
    wait_for_selected_detail(page)
    box = page.locator('#plan-detail .action-card input[type=checkbox]').first
    box.check()
    assert box.is_checked() and not errors


def test_checks_carry_over_to_an_edited_course(audit_page):
    """코스를 바꾸면(수단·장소 교체) 새 id 로 저장된다. 장소에 묶인 체크는 이어받고, 시각이 바뀔 수 있는 출발·마무리·축제 체크는 이어받지 않는다(검토 지적)."""
    page, _, _ = audit_page
    carried = page.evaluate(f"""()=>{{
      localStorage.setItem('datemate:action-card:p1',JSON.stringify(['reserve:b','check:a','depart','finish','check:gone']));
      const plan=({BASE})({{id:'p2',parent:'p1'}});
      const seen=[...actionCardChecked(plan)].sort();
      return [seen,JSON.parse(localStorage.getItem('datemate:action-card:p2')).sort()];
    }}""")
    assert carried == [['check:a', 'reserve:b'], ['check:a', 'reserve:b']]
    # 새 코스에 이미 저장된 체크가 있으면 그것을 쓴다.
    own = page.evaluate(f"""()=>{{
      localStorage.setItem('datemate:action-card:p3',JSON.stringify(['depart']));
      return [...actionCardChecked(({BASE})({{id:'p3',parent:'p1'}}))];
    }}""")
    assert own == ['depart']


def test_evening_festival_venue_by_car_gets_a_parking_line(audit_page):
    page, _, _ = audit_page
    found = items(page, "{conditions:{start:'16:00',end:'22:00',return_home:true,festival:{title:'빛축제'}},festival_visit:{position:'last',title:'빛축제',arrival:'17:30',departure:'18:30',leg:{minutes:7,mode:'car'}}}")
    parking = [i for i in found if i['id'] == 'parking:festival']
    assert len(parking) == 1 and parking[0]['when'] == 'arrive'
    assert parking[0]['text'] == '빛축제 행사장 도착(17:30) 전 주차장 확인 · 주차비는 계산에 없어요'
    assert [i['when'] for i in found].index('arrive') < [i['when'] for i in found].index('finish')


def test_reserve_line_replaces_the_reserve_check(audit_page):
    """예약이 필요한 곳은 '예약하기' 한 줄이면 된다. 같은 장소에 '예약 확인'을 또 쓰지 않는다."""
    page, _, _ = audit_page
    found = items(page, "{verification:{places:[{id:'a',coverage:{missing:[]}},{id:'b',coverage:{missing:['예약','가격']}}]}}")
    texts = [i['text'] for i in found if i['when'] == 'before']
    assert texts == ['2. B — 가격 확인', '2. B 예약하기 (12:30 도착 기준)']


def test_demo_course_has_no_check_lines_for_fictional_places(audit_page):
    page, _, _ = audit_page
    found = items(page, "{conditions:{mode:'demo',start:'11:00',end:'21:00',return_home:false}}")
    assert not [i for i in found if i['id'].startswith('check:')]


def test_blocked_storage_says_checks_are_not_kept(audit_page):
    page, _, _ = audit_page
    hint = f"()=>actionCard(({BASE})({{}})).querySelector('.hint').textContent"
    assert page.evaluate(hint).endswith('체크 표시는 이 브라우저에만 남아요.')
    page.evaluate("Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new Error('blocked')}})")
    assert page.evaluate(hint) == '확인할 것을 언제 할지 순서대로 모았어요. 이 브라우저에선 체크 표시가 저장되지 않아요.'
