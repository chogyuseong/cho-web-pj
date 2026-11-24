"""지각 확인 결론 문장(static/delay-check.js delayCheckView) — 2026-11-24 사용자: '답변이 너무 딱딱해'.

말하듯이 쓰고, 문제마다 맞는 다음 행동을 권한다(점검 보고서 F10: 일정 종료·축제 종료에 '이 장소에 연락하라'고 하지 않는다)."""
from test_functional_audit import audit_page  # noqa: F401  (fixture)

VIEW = """(extra)=>{
  const data=Object.assign({basis:'근거',status:'ok',delay:20,index:0,rows:[],first_problem:null,pending:[],finish:'18:20',original_finish:'18:00',
    estimated_legs:[],no_last_entry:[],recovery:null},extra);
  return delayCheckView(data,{id:'p1',can_edit:false,places:[{name:'A'}]}).map(n=>n.textContent).join(' | ');
}"""


def view(page, extra):
    return page.evaluate(f'()=>({VIEW})({extra})')


def test_conclusions_read_like_speech(audit_page):  # noqa: F811
    page, _, _ = audit_page
    ok = view(page, '{}')
    assert '20분 늦어도 괜찮아요. 그대로 가면 돼요.' in ok and '끝나는 시간이 18:00에서 18:20로 늦어져요' in ok
    same = view(page, "{finish:'18:00'}")
    assert '끝나는 시간도 18:00 그대로예요.' in same
    unknown = view(page, "{status:'unknown',pending:[{place:'B',fields:['영업시간']}]}")
    assert '시간표로는 괜찮아 보여요' in unknown and '출발 전에 이곳부터 확인해 보세요' in unknown
    # 딱딱하던 표현은 없다.
    for old in ('처음 문제가 생기는 곳:', '끝나는 시각 18:00 → 18:20', '출발 전에 먼저 확인할 것:'):
        assert old not in ok + unknown


def test_each_problem_suggests_a_fitting_next_step(audit_page):  # noqa: F811
    page, _, _ = audit_page
    problem = lambda kind, place='B': view(page, "{status:'problem',first_problem:{place:'%s',time:'17:10',kind:'%s',limit:'17:30',over:15}}" % (place, kind))
    closing = problem('closing')
    assert '여기서 처음 문제가 생겨요' in closing and '17:30에 문을 닫기 전에' in closing and '15분 모자라요' in closing
    assert '대신 갈 곳' in closing
    entry = problem('last_entry')
    assert '마지막 입장(17:30)을 15분 넘겨요' in entry and '전화' in entry
    end = problem('end', '일정 종료')
    assert '정한 종료 시간(17:30)보다 15분 늦어요' in end and '연락' not in end and '전화' not in end
    festival = problem('festival', '축제 · 빛축제')
    assert '축제' in festival and '연락' not in festival and '전화' not in festival
