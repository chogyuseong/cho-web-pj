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
