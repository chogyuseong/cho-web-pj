"""2026-11-24 전체 점검 F1·F2·F3.
F1: 코스를 바꾼 뒤 공유하고 되돌려도, 같은 변경 계열(같은 처음 코스에서 나온 버전)의 열린 공유 링크가 보이고 취소할 수 있다.
F2: 실행 카드에서 이어받은 체크를 모두 풀면 빈 상태로 저장되어, 다시 그려도 바꾸기 전 코스의 체크를 또 이어받지 않는다.
F3: 코스를 새 버전으로 바꾸는 동작(되돌리기 포함)은 잠금 하나를 같이 쓰고, 늦게 온 새 코스를 화면에 못 열면 알린다."""
import json

from fastapi.testclient import TestClient

from app.main import app
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)
from test_together import PAYLOAD, share

NO_OVERFLOW = 'document.documentElement.scrollWidth<=document.documentElement.clientWidth'


def change(client, plan_id, mode):
    response = client.post(f'/api/plans/{plan_id}/transport', json={'default': mode})
    assert response.status_code == 200, response.text
    return response.json()


def status(client, plan_id):
    response = client.get(f'/api/plans/{plan_id}/shares')
    assert response.status_code == 200, response.text
    return response.json()


def test_share_status_lists_open_links_of_other_versions_in_the_family():
    with TestClient(app) as owner, TestClient(app) as other:
        plan = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        first = change(owner, plan['id'], 'bicycle')
        guest_headers = share(owner, first['id'])
        # 상대가 바꾼 코스(first)에 의견을 남긴다.
        place = first['places'][0]['id']
        assert other.post('/api/shared-plan/vote', headers=guest_headers, json=dict(choices={place: 'yes'})).status_code == 200
        restored = owner.post(f"/api/plans/{first['id']}/undo").json()
        assert restored['id'] == plan['id']
        # 되돌린 코스(부모)에서: 이 코스에는 링크가 없지만, 되돌리기 전 코스(자식)의 링크 1개가 열려 있고 의견 1명이 거기 있다.
        seen = status(owner, plan['id'])
        assert seen['current'] == dict(plan_id=plan['id'], active=0, expires=None)
        assert seen['earlier'] == []
        assert [(row['plan_id'], row['active'], row['relation'], row['opinions']) for row in seen['other']] == [(first['id'], 1, 'later', 1)]
        assert seen['other'][0]['places'] == [p['name'] for p in first['places']]
        assert 'token' not in json.dumps(seen)
        # 되돌린 뒤 다른 수단으로 바꾼 코스(형제)에서도 같은 링크가 보인다.
        second = change(owner, plan['id'], 'transit')
        sibling = status(owner, second['id'])
        assert [(row['plan_id'], row['relation']) for row in sibling['other']] == [(first['id'], 'branch')]
        # 바꾼 코스(자식)에서 보면 그 링크는 '이 코스'의 것이고, 다른 버전 목록에 겹쳐 나오지 않는다.
        own = status(owner, first['id'])
        assert own['current']['active'] == 1 and own['other'] == []
        # 소유자 검사는 그대로: 다른 브라우저는 현황도, 취소도 못 한다.
        assert other.get(f"/api/plans/{plan['id']}/shares").status_code == 404
        assert other.delete(f"/api/plans/{first['id']}/shares").status_code == 404
        # 취소하면 목록에서 빠진다.
        assert owner.delete(f"/api/plans/{first['id']}/shares").status_code == 200
        assert status(owner, plan['id'])['other'] == []


def test_other_owners_courses_never_join_the_family():
    with TestClient(app) as owner, TestClient(app) as stranger:
        mine = owner.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        theirs = stranger.post('/api/plans', json=PAYLOAD).json()['plans'][0]
        changed = change(stranger, theirs['id'], 'bicycle')
        share(stranger, changed['id'])
        assert status(owner, mine['id'])['other'] == []


def bulk_change(page, mode):
    before = page.evaluate('selected.id')
    page.locator('#plan-detail summary[data-transport-toggle=bulk]').click()
    page.locator(f'#plan-detail .transport-bulk .transport-chooser button[data-mode={mode}]').click()
    page.wait_for_function('(id)=>selected.id!==id', arg=before)
    wait_for_selected_detail(page)
    return before


def test_undone_course_shows_and_revokes_the_link_on_a_narrow_phone(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 320, 'height': 700})
    generate(page)
    wait_for_selected_detail(page)
    original = bulk_change(page, 'bicycle')
    changed = page.evaluate('selected.id')
    page.evaluate("(id)=>api('/plans/'+id+'/shares',{})", changed)
    page.locator('#plan-detail .undo-actions button').click()
    page.wait_for_function('(id)=>selected.id===id', arg=original)
    wait_for_selected_detail(page)
    line = page.locator('#plan-detail .share-status')
    page.wait_for_function("document.querySelector('#plan-detail .share-status').textContent.includes('공유 링크 1개가 아직 열려 있어요')", timeout=15000)
    text = line.inner_text()
    assert '이 코스로 만든 공유 링크는 없어요.' in text
    assert '의견도 그 코스에 남아' in text
    names = page.evaluate("(id)=>api('/plans/'+id).then(p=>p.places.map(x=>x.name).join(' → '))", changed)
    assert names in text
    assert page.evaluate(NO_OVERFLOW)
    line.get_by_role('button', name='그 링크 취소').click()
    page.wait_for_function("!document.querySelector('#plan-detail .share-status').textContent.includes('아직 열려 있어요')", timeout=15000)
    assert page.evaluate("(id)=>api('/plans/'+id+'/shares').then(d=>d.current.active)", changed) == 0
    assert not errors


BASE = """(extra)=>Object.assign({
  id:'p1',
  conditions:{start:'11:00',end:'21:00',return_home:true},
  places:[{id:'a',name:'A'},{id:'b',name:'B',reservation:true}],
  timeline:[{arrival:'11:10',departure:'12:10'},{arrival:'12:30',departure:'13:30'}],
  legs:[{minutes:10,mode:'walk'},{minutes:20,mode:'car'},{minutes:30,mode:'car',status:'estimated'}],
  verification:{places:[{id:'a',coverage:{missing:['예약','가격']}},{id:'b',coverage:{missing:[]}}]}
},extra)"""


def test_unchecking_every_carried_check_stays_unchecked(audit_page):
    page, _, _ = audit_page
    out = page.evaluate(f"""()=>{{
      localStorage.setItem('datemate:action-card:p1',JSON.stringify(['reserve:b']));
      const plan=({BASE})({{id:'p2',parent:'p1'}});
      const first=actionCard(plan);document.body.append(first);
      const checked=()=>[...document.querySelectorAll('.action-card input')].filter(i=>i.checked).length;
      const before=checked();
      document.querySelector('.action-card input:checked').click();
      const stored=localStorage.getItem('datemate:action-card:p2');
      first.remove();
      const second=actionCard(plan);document.body.append(second);
      const after=checked();
      second.remove();
      return {{before,stored,after}};
    }}""")
    assert out == dict(before=1, stored='[]', after=0)


def slow_transport(page):
    page.evaluate("""()=>{const real=api;window.__sent=0;window.__done=null;window.__release=null;
      window.api=async(...a)=>{if(String(a[0]).endsWith('/transport')){window.__sent++;const r=await real(...a);
        await new Promise(x=>window.__release=x);window.__done=r;return r;}return real(...a);};}""")
    page.locator('#plan-detail summary[data-transport-toggle=bulk]').click()
    page.locator('#plan-detail .transport-bulk .transport-chooser button[data-mode=transit]').click()
    page.wait_for_function('window.__sent===1&&!!window.__release', timeout=20000)


def test_undo_waits_for_a_change_in_flight(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 320, 'height': 700})
    generate(page)
    wait_for_selected_detail(page)
    bulk_change(page, 'bicycle')
    changed = page.evaluate('selected.id')
    slow_transport(page)
    # 응답을 기다리는 동안 되돌리기를 누르면 막고 알린다.
    page.locator('#plan-detail .undo-actions button').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('코스를 바꾸는 중이에요')")
    assert page.evaluate('selected.id') == changed
    page.evaluate('window.__release()')
    page.wait_for_function('()=>!!window.__done&&selected.id===window.__done.id', timeout=20000)
    late = page.evaluate('window.__done')
    assert late['parent'] == changed and page.evaluate('plans.some(p=>p.id===selected.id)')
    assert page.evaluate(NO_OVERFLOW)
    assert not errors


def test_late_course_that_cannot_be_shown_is_announced(audit_page):
    page, base, errors = audit_page
    generate(page)
    wait_for_selected_detail(page)
    assert page.evaluate('plans.length') >= 2
    start = page.evaluate('selected.id')
    slow_transport(page)
    # 기다리는 동안 다른 코스 탭으로 옮긴다.
    page.locator('#results .plan-option-tabs > button').nth(1).click()
    page.wait_for_function('(id)=>selected.id!==id', arg=start)
    wait_for_selected_detail(page)
    other = page.evaluate('selected.id')
    page.evaluate('window.__release()')
    page.wait_for_function('!!window.__done', timeout=20000)
    page.wait_for_function("document.querySelector('#toast').textContent.includes('새 코스를 저장했어요')")
    late = page.evaluate('window.__done.id')
    assert page.evaluate('selected.id') == other
    # 첫 탭이 새 코스를 가리키고, 누르면 그 코스가 열린다.
    assert page.evaluate('plans[0].id') == late
    assert page.evaluate("document.getElementById('transport-live').textContent") != '이동 시간을 다시 계산하고 있어요.'
    page.locator('#results .plan-option-tabs > button').nth(0).click()
    page.wait_for_function('(id)=>selected.id===id', arg=late)
    assert not errors
