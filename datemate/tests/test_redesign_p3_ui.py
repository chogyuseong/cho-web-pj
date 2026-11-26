"""2026-11-26 요구 문서 Phase 3(datemate/docs/redesign-2026-11-26-plan.ko.md).

- 장소 카드 순서 ↑/↓: POST /api/plans/{id}/reorder {order, manual:true}(app/order_suggestion.apply_manual)로 같은 규칙에 따라 다시 계산해 저장,
  알림의 [되돌리기]로 돌아간다. 맨 위 ↑·맨 아래 ↓ 는 꺼져 있다. 고정한 장소의 자리를 옮기는 순서는 서버가 거절한다.
- 늦어짐 미리 보기에서 문제가 나면 [대체 장소로 자동 조정]: 서버 지각 복구의 1순위 후보로 delay-recovery 를 보낸다."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)


def test_order_buttons_move_a_stop_and_undo_brings_it_back(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    before = page.evaluate('selected.places.map(p=>p.name)')
    boxes = page.locator('#plan-detail .order-buttons')
    assert boxes.count() == len(before)
    assert boxes.first.locator('.order-up').is_disabled() and boxes.last.locator('.order-down').is_disabled()
    assert boxes.first.locator('.order-down').bounding_box()['height'] >= 44
    boxes.first.locator('.order-down').click()
    page.wait_for_function("b=>JSON.stringify(selected.places.map(p=>p.name))!==JSON.stringify(b)", arg=before, timeout=30000)
    after = page.evaluate('selected.places.map(p=>p.name)')
    assert after[:2] == [before[1], before[0]] and after[2:] == before[2:]
    assert page.evaluate('selected.change_reason').startswith('방문 순서를 직접 바꿨어요.')
    page.wait_for_function("!!document.querySelector('#toast .toast-action')")
    assert '2번째로 옮겼어요' in page.locator('#toast .toast-text').inner_text()
    page.locator('#toast .toast-action').click()
    page.wait_for_function("b=>JSON.stringify(selected.places.map(p=>p.name))===JSON.stringify(b)", arg=before, timeout=20000)


def test_manual_order_refuses_moving_a_locked_place(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    # 첫 장소를 고정하면 그 자리를 옮기는 순서는 거절(409)된다.
    result = page.evaluate("""async()=>{
      const p=selected;const locked=await fetch(`/api/plans/${p.id}/locks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({locked:[0]})});
      const fresh=locked.ok?await locked.json():p;const order=fresh.places.map(x=>x.id);[order[0],order[1]]=[order[1],order[0]];
      const r=await fetch(`/api/plans/${fresh.id}/reorder`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order,manual:true})});
      return [locked.status,r.status,(await r.json()).detail];}""")
    assert result[0] == 200, result
    assert result[1] == 409 and '자리를 옮기지 않아요' in result[2], result


def test_auto_adjust_sends_the_first_recovery_option(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    generate(page)
    wait_for_selected_detail(page)
    plan_id = page.evaluate('selected.id')
    names = page.evaluate('selected.places.map(p=>p.name)')
    problem = {
        'status': 'problem', 'index': 0, 'delay': 30, 'stays': {}, 'finish': None, 'original_finish': '19:43', 'pending': [], 'basis': '',
        'first_problem': {'place': names[1], 'time': '18:40', 'reason': '영업시간 밖 방문', 'kind': 'closing', 'limit': '18:30', 'over': 20},
        'rows': [{'name': names[0], 'arrival': '17:32', 'start': '17:32', 'departure': '18:17', 'wait': 0, 'shift': 30, 'stay': 45, 'state': 'ok', 'missing': []},
                 {'name': names[1], 'arrival': '18:20', 'start': '18:20', 'departure': '19:10', 'wait': 0, 'shift': 30, 'stay': 50, 'state': 'problem',
                  'reason': '영업시간 밖 방문', 'limit': '18:30', 'over': 40, 'missing': []}],
        'recovery': {'index': 1, 'place': names[1], 'kind': '카페', 'blocked': None, 'note': '',
                     'options': [{'id': 'opt-1', 'name': '대신 카페', 'distance_m': 300, 'extra_minutes': 2, 'start': '18:20', 'departure': '19:10', 'hours_known': True},
                                 {'id': 'opt-2', 'name': '둘째 카페', 'distance_m': 500, 'extra_minutes': 4, 'start': '18:22', 'departure': '19:12', 'hours_known': True}],
                     'skip': {'allowed': True, 'reason': '빼도 돼요'}},
    }
    page.route(f'**/plans/{plan_id}/delay-check?*', lambda route: route.fulfill(json=problem))
    sent = []

    def recover(route):
        sent.append(route.request.post_data_json)
        route.fulfill(status=409, json={'detail': '테스트: 저장하지 않음'})
    page.route(f'**/plans/{plan_id}/delay-recovery', recover)
    page.locator('#plan-detail .delay-sim-pill[data-minutes="30"]').click()
    auto = page.locator('#plan-detail .delay-sim-auto')
    auto.wait_for()
    assert auto.inner_text() == '대체 장소로 자동 조정'
    auto.click()
    page.wait_for_function('!!document.querySelector("#toast")?.textContent.includes("테스트: 저장하지 않음")')
    assert sent == [{'index': 0, 'minutes': 30, 'target': 1, 'replacement_id': 'opt-1'}]


def test_place_info_opens_as_a_drawer_or_bottom_sheet(audit_page):
    """장소 정보(place-dialog.js showPlace)는 넓은 화면에서 오른쪽 서랍, 720px 이하에서 아래 시트(redesign.css 27)). 닫으면 보통 대화상자로."""
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    for width in (1280, 390):
        page.set_viewport_size({'width': width, 'height': 800})
        page.evaluate("showPlace(selected.places[0].id,'demo')")
        page.wait_for_function("document.getElementById('dialog').open&&document.getElementById('dialog').classList.contains('place-drawer')")
        page.wait_for_timeout(350)
        box = page.evaluate("""()=>{const r=document.getElementById('dialog').getBoundingClientRect();
          return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,cw:document.documentElement.clientWidth,vh:innerHeight};}""")
        assert abs(box['right'] - box['cw']) <= 1 and box['bottom'] <= box['vh'] + 1, (width, box)
        if width > 720:
            assert box['top'] <= 1 and box['left'] > 200, box
        else:
            assert abs(box['bottom'] - box['vh']) <= 1 and box['left'] <= 1, box
        page.keyboard.press('Escape')
        page.wait_for_function("!document.getElementById('dialog').open")
        assert page.evaluate("document.getElementById('dialog').classList.contains('place-drawer')") is False
