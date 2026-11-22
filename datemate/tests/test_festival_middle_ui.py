"""코스 중간에 둔 축제(festival_visit.position 'middle')의 화면: 지도 구간, 코스 상세 축제 칸, 현장 일정, 실행 카드, 공유 화면, 지각 확인 복구 줄."""
from fastapi.testclient import TestClient

from app import store
from app.main import app
from test_festival_leg import segments
from test_festival_middle import cond, planned
from test_festival_fixed_time import HOME
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)


def test_segments_go_through_the_venue_between_the_places(audit_page):  # noqa: F811
    page, _, _ = audit_page
    got = segments(page, "{festival_visit:{position:'middle',after:0,leg:{tag:'lf'}}}")
    assert got == [['O', 'A', 'l0'], ['A', 'O', 'lf'], ['O', 'B', 'l1'], ['B', 'H', 'l2']]
    # 자리가 잘못 저장된 기록(마지막 장소 뒤 등)은 무시하고 예전 구간 그대로.
    assert segments(page, "{festival_visit:{position:'middle',after:1,leg:{tag:'lf'}}}") == [['O', 'A', 'l0'], ['A', 'B', 'l1'], ['B', 'H', 'l2']]


ACTION = """(extra)=>Object.assign({
  id:'p1',
  conditions:{start:'10:00',end:'19:00',return_home:false,festival:{title:'빛축제'}},
  places:[{id:'a',name:'A'},{id:'b',name:'B'}],
  timeline:[{arrival:'10:10',departure:'11:40'},{arrival:'12:55',departure:'14:25'}],
  legs:[{minutes:10,mode:'walk'},{minutes:7,mode:'car'}],
  festival_visit:{position:'middle',after:0,title:'빛축제',arrival:'11:50',departure:'12:50',leg:{minutes:9,mode:'car'}}
},extra)"""


def test_action_card_arrives_at_the_festival_between_the_places(audit_page):  # noqa: F811
    page, _, _ = audit_page
    found = page.evaluate(f'()=>actionCardItems(({ACTION})({{}}))')
    texts = [i['text'] for i in found]
    # 코스 시작은 첫 장소(맨 앞 축제가 아님).
    assert '10:00 출발 · 1. A 10:10 도착 예정' in texts
    assert not any('코스 시작' in t for t in texts)
    arrive = [i['text'] for i in found if i['when'] == 'arrive']
    assert arrive == ['빛축제 행사장 도착(11:50) 전 주차장 확인 · 주차비는 계산에 없어요',
                      '11:50까지 빛축제 행사장 도착 (1. A 다음 · 축제 11:50~12:50)',
                      '2. B 도착(12:55) 전 주차장 확인 · 주차비는 계산에 없어요']
    assert found[-1]['text'] == '19:00까지 2. B 마치기'
    assert len({i['id'] for i in found}) == len(found)


def owner_plan(client, plan):
    client.get('/api/places?mode=demo')
    return store.save_plan(plan, store.owner_of(client.cookies['dm_session'])), client.cookies['dm_session']


def test_course_screen_shows_the_festival_between_the_places(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan, owner = owner_plan(client, planned(c=cond(return_home=True, home=HOME)))
    visit = plan['festival_visit']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.context.add_cookies([{'name': 'dm_session', 'value': owner, 'url': base}])
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(base + '/?plan=' + plan['id'])
    page.wait_for_function('(id)=>selected?.id===id', arg=plan['id'])
    block = page.locator('#plan-detail .festival-visit')
    assert block.count() == 1 and f"{visit['arrival']}~{visit['departure']}" in block.inner_text()
    assert '중간' in block.get_attribute('aria-label')
    assert page.locator('#plan-detail .stop').count() == 2
    # 첫 장소 칸 뒤, 둘째 장소 칸 앞.
    assert page.evaluate("""()=>{const f=document.querySelector('#plan-detail .festival-visit'),[a,b]=document.querySelectorAll('#plan-detail .stop');
        return !!(a.compareDocumentPosition(f)&Node.DOCUMENT_POSITION_FOLLOWING)&&!!(f.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING);}""")
    leg = page.locator('#plan-detail .festival-visit-leg')
    assert leg.inner_text().startswith(f"{plan['places'][0]['name']} → 축제 행사장")
    # 둘째 장소로 가는 구간 줄은 행사장에서 출발한다.
    assert page.locator('#plan-detail .route-line-text').filter(has_text='점검 빛축제 행사장 → ' + plan['places'][1]['name']).count() == 1
    text = page.evaluate('fieldItineraryText(selected)')
    assert text.index('1. ') < text.index('축제 · 점검 빛축제') < text.index('2. ')
    assert '행사장으로' in text
    tag = page.locator('.festival-course-tag')
    assert tag.count() == 1 and '사이' in tag.inner_text()
    # 휴대폰 폭에서 옆으로 넘치지 않는다.
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    # 들어가는 구간의 수단 바꾸기.
    toggle = block.locator('[data-transport-toggle="festival"]')
    toggle.click()
    block.locator('.transport-chooser button[data-mode="transit"]').click()
    page.wait_for_function("selected?.festival_visit?.leg?.mode==='transit'&&selected.festival_visit.position==='middle'")
    assert '대중교통' in page.locator('#plan-detail .festival-visit-leg').inner_text()
    assert not errors


def test_shared_link_shows_the_festival_between_the_places(audit_page):  # noqa: F811
    page, base, errors = audit_page
    with TestClient(app) as client:
        plan, _ = owner_plan(client, planned())
        token = client.post('/api/plans/' + plan['id'] + '/shares').json()['url']
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=[], message='')))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(base + token)
    page.wait_for_function('document.querySelectorAll("#shared-places article").length===2')
    block = page.locator('#shared-places .shared-festival-visit')
    visit = plan['festival_visit']
    assert block.count() == 1 and block.locator('h2').inner_text() == f"점검 빛축제 · {visit['arrival']}~{visit['departure']}"
    assert plan['places'][0]['name'] in block.inner_text()
    assert page.evaluate("""()=>{const f=document.querySelector('.shared-festival-visit'),[a,b]=document.querySelectorAll('#shared-places article');
        return !!(a.compareDocumentPosition(f)&Node.DOCUMENT_POSITION_FOLLOWING)&&!!(f.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING);}""")
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not errors


def test_delay_check_recovery_sits_on_the_place_row_not_the_festival_row(audit_page):  # noqa: F811
    page, _, _ = audit_page
    got = page.evaluate("""()=>{
      delayRecoveryBlock=()=>node('div','REC','rec-marker');
      const plan={id:'p1',can_edit:true,places:[{name:'A'},{name:'B'}]};
      const row=(name,extra)=>Object.assign({name,arrival:'11:00',start:'11:00',departure:'12:00',wait:0,shift:0,stay:60,stay_assumed:false,state:'ok',missing:[]},extra);
      const data={basis:'',status:'problem',delay:10,index:0,rows:[row('A'),row('축제 · 빛축제',{festival:true}),row('B',{state:'problem'})],
        first_problem:{place:'B',time:'13:00',kind:'closing',limit:'14:30',over:5},pending:[],estimated_legs:[],no_last_entry:[],recovery:{index:1}};
      const list=delayCheckView(data,plan).find(n=>n.tagName==='OL');
      return [...list.children].map(li=>!!li.querySelector('.rec-marker'));
    }""")
    assert got == [False, False, True]
