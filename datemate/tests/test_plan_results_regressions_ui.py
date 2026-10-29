"""Actual browser interactions, local backend and isolated storage."""
import pytest
from test_functional_audit import audit_page,generate


def sports_for_selected(page,monkeypatch):
    from app.catalog import places as catalog_places
    anchor=page.evaluate('selected.places[0]')
    sport=dict(anchor,id='leisure-ui-sport',name='동선 주변 클라이밍',category='레저·활동',themes=['레저·활동'],tags=['climbing'])
    monkeypatch.setattr('app.catalog.places',lambda *args,**kwargs:[*catalog_places(*args,**kwargs),sport])
    return sport


@pytest.mark.parametrize('width',[1440,390])
def test_leisure_select_map_locks_metadata_and_undo(audit_page,monkeypatch,width):
    page,base,errors=audit_page
    page.set_viewport_size({'width':width,'height':1000})
    generate(page);sport=sports_for_selected(page,monkeypatch)
    original=page.evaluate('selected.id');other=page.evaluate('selected.places[1].id')
    page.locator('#plan-detail .stop').nth(1).get_by_role('button',name='○ 장소 고정',exact=True).click()
    page.wait_for_function('Object.hasOwn(selected.conditions.locked,1)')
    panel=page.locator('.leisure-results').first
    panel.locator('summary').click()
    candidate=panel.locator('.leisure-result-card').filter(has_text=sport['name'])
    candidate.get_by_role('button',name='이 레저로 교체',exact=True).click()
    page.wait_for_function('(id)=>selected.id!==id',arg=original)
    assert page.evaluate('selected.places[0].id')==sport['id']
    assert page.evaluate('selected.places[1].id')==other
    assert page.evaluate('selected.verification&&selected.decision_summary&&Object.hasOwn(selected.conditions.locked,1)')
    assert sport['name'] in page.locator('#plan-detail .stop').first.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('(id)=>selected.id===id',arg=original)
    assert page.evaluate('locks.has(1)')


def test_leisure_failure_retry_and_locked_stop(audit_page,monkeypatch):
    page,base,errors=audit_page
    generate(page);sport=sports_for_selected(page,monkeypatch)
    def fail(route):route.fulfill(status=503,content_type='application/json',body='{"detail":"주변 검색 연결 오류"}')
    page.route('**/leisure-options',fail)
    panel=page.locator('.leisure-results').first;panel.locator('summary').click()
    retry=panel.get_by_role('button',name='다시 찾기',exact=True)
    retry.wait_for();assert '주변 검색 연결 오류' in panel.inner_text()
    page.unroute('**/leisure-options',fail);retry.click()
    panel.locator('.leisure-result-card').filter(has_text=sport['name']).wait_for()
    page.locator('#plan-detail .stop').first.get_by_role('button',name='○ 장소 고정',exact=True).click()
    page.wait_for_function('Object.hasOwn(selected.conditions.locked,0)')
    panel=page.locator('.leisure-results').first;panel.locator('summary').click()
    assert '고정한 장소예요' in panel.inner_text()
    assert panel.get_by_role('button',name='이 레저로 교체',exact=True).count()==0


def test_late_leisure_response_does_not_switch_selected_option(audit_page,monkeypatch):
    page,base,errors=audit_page
    generate(page);sports_for_selected(page,monkeypatch)
    old=page.evaluate('selected.id')
    page.evaluate("""() => {window.originalApi=api;window.releaseLeisure=null;api=async function(path,...args){const data=await originalApi(path,...args);if(path.endsWith('/leisure-select'))return await new Promise(resolve=>{window.releaseLeisure=()=>resolve(data);});return data;};}""")
    panel=page.locator('.leisure-results').first;panel.locator('summary').click()
    panel.get_by_role('button',name='이 레저로 교체',exact=True).first.click()
    page.wait_for_function('!!window.releaseLeisure')
    page.locator('.plan-option-tabs button').nth(1).click()
    active=page.evaluate('selected.id');assert active!=old
    page.evaluate('window.releaseLeisure()')
    page.wait_for_function('(id)=>!plans.some(p=>p.id===id)',arg=old)
    assert page.evaluate('selected.id')==active
    assert page.evaluate('plans.length')>=2


def test_quick_two_locks_are_both_retained(audit_page):
    page,base,errors=audit_page
    generate(page)
    page.evaluate('window.locking=Promise.all([togglePlanLock(selected,0),togglePlanLock(selected,1)])')
    page.wait_for_function('Object.keys(selected.conditions.locked).length===2')
    data=page.request.get(base+'/api/plans/'+page.evaluate('selected.id')).json()
    assert set(data['conditions']['locked'])=={'0','1'}


def test_unknown_plan_response_cannot_replace_entire_list(audit_page):
    page,base,errors=audit_page
    generate(page)
    before=page.evaluate('plans.map(p=>p.id)')
    assert page.evaluate("replaceInList('expired-plan-id',{id:'late-response'})") is False
    assert page.evaluate('plans.map(p=>p.id)')==before


def test_meal_menu_preview_apply_and_undo_in_browser(audit_page,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from test_experience import owned,food_fixture
    page,base,errors=audit_page
    with TestClient(app) as client:
        plan=owned(client);food=food_fixture(monkeypatch,plan)
        owner=client.cookies['dm_session']
    import app.main as main_module
    from app import menus
    old_get=main_module.get_place
    monkeypatch.setattr(main_module,'get_place',lambda pid,mode:food if pid==food['id'] else old_get(pid,mode))
    menu_lookup=menus.restaurant_menu
    monkeypatch.setattr(menus,'restaurant_menu',lambda place,**kwargs:menu_lookup(place))
    page.context.add_cookies([{'name':'dm_session','value':owner,'url':base}])
    page.goto(base+'/?plan='+plan['id'])
    page.wait_for_function('(id)=>selected?.id===id',arg=plan['id'])
    page.evaluate('(food)=>document.querySelector("#plan-detail").append(restaurantCard(food,{plan:selected,index:0}))',food)
    page.get_by_role('button',name='이 식당을 일정에 넣기',exact=True).last.click()
    dialog=page.locator('#dialog')
    page.wait_for_function('document.querySelector("[name=meal_menu]")?.options.length>1')
    dialog.locator('[name=meal_menu]').select_option('0')
    dialog.get_by_role('button',name='이동·시간·비용 미리 계산',exact=True).click()
    apply=dialog.get_by_role('button',name='이 변경안으로 확정',exact=True)
    apply.wait_for();assert apply.is_enabled()
    assert '테스트정식' in dialog.inner_text()
    apply.click()
    page.wait_for_function('(id)=>selected?.parent===id',arg=plan['id'])
    assert len(page.evaluate('selected.places'))==3
    assert page.evaluate('selected.places.some(p=>p.id==="food:fixture")')
    assert page.evaluate('selected.decision_summary&&selected.verification')
    page.get_by_role('button',name='교체 되돌리기',exact=True).click()
    page.wait_for_function('(id)=>selected?.id===id',arg=plan['id'])
    assert len(page.evaluate('selected.places'))==2
