"""가격 확인 중에 보이는 '확정 전 후보' 카드(static/plan-progress.js PlanPreview).

실제 서버로 가상 장소(데모) 추천을 돌리되, 완료 응답은 풀어 줄 때까지 '가격 확인 중'으로 바꿔 돌려준다.
기다려 주지 않는 서버처럼 같은 단계를 바로 답하므로 긴 폴링이 없는 경우도 함께 본다.
"""
import re

from test_functional_audit import audit_page  # noqa: F401 (fixture)

HELD = dict(status='running', stage='가격 확인', message='코스 후보를 찾았어요. 가격과 필수 조건을 마지막으로 확인해요')


def hold(page, state):
    def handle(route):
        if route.request.method != 'GET':
            return route.continue_()
        response = route.fetch()
        data = response.json()
        if data.get('status') == 'complete':
            if state.get('fail'):
                data = dict(id=data['id'], status='failed', stage='가격 확인', message='가격 확인 단계에서 처리 오류가 발생했어요.')
            elif not state.get('release'):
                data = dict(HELD, id=data['id'], preview=data.get('preview'), preview_options=data.get('preview_options'))
            elif state.get('change'):
                data = state['change'](data)
        route.fulfill(response=response, json=data)
    page.route('**/api/plan-jobs/*', handle)


def submit(page):
    page.evaluate("form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;")
    page.locator('#submit-plan').click()
    page.wait_for_function('document.querySelectorAll("#results .plan-preview-card").length>0', timeout=45000)


def no_overflow(page, width):
    page.set_viewport_size({'width': width, 'height': 900})
    return page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth&&[...document.querySelectorAll(".plan-preview,.plan-preview-card,.plan-preview-changes")].every(e=>e.getBoundingClientRect().right<=innerWidth+1)')


def test_preview_cards_are_read_only_and_marked_as_unconfirmed(audit_page):
    page, base, errors = audit_page
    state = {}
    hold(page, state)
    submit(page)
    preview = page.locator('#results .plan-preview')
    cards = preview.locator('.plan-preview-card')
    options = page.evaluate('PlanPreview.options')
    assert cards.count() == len(options)
    text = preview.inner_text()
    assert '확정 전 후보 · 가격 확인 중' in text and text.count('비용 · 가격 확인 중') == cards.count()
    # 가격·비용 숫자나 0원을 확정값처럼 보이지 않고, 누를 수 있는 것이 없다(저장·공유·교체는 확정 뒤).
    assert not re.search(r'\d[\d,]*\s*원', text)
    assert preview.locator('button,a,input,select,[tabindex]').count() == 0
    assert page.evaluate('selected===null&&plans.length===0') and page.locator('#results .plan-option-tabs').count() == 0
    first = options[0]
    assert first['places'][0]['name'] in cards.nth(0).inner_text()
    # 진행 안내(role=status)는 짧게 한 번만 바뀐다. 같은 단계의 응답이 이어져도 다시 그리지 않는다.
    progress = page.locator('#progress')
    assert f"찾은 후보 {cards.count()}개를 아래에 먼저 보여 드려요" in progress.inner_text()
    assert '찾은 후보 · 최종 확인 후' not in progress.inner_text()
    page.evaluate("window.__mutations=0;new MutationObserver(r=>window.__mutations+=r.length).observe(document.querySelector('#progress'),{childList:true,subtree:true,characterData:true})")
    page.wait_for_timeout(2600)
    assert page.evaluate('window.__mutations') == 0
    assert no_overflow(page, 320) and no_overflow(page, 390)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    # 새로고침해도 진행 중인 검색에 다시 붙고 확정 전 후보를 다시 보여 준다.
    page.reload()
    page.wait_for_function('document.querySelectorAll("#results .plan-preview-card").length>0', timeout=45000)
    state['release'] = True
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled', timeout=45000)
    assert page.locator('#results .plan-preview').count() == 0
    # 확정 전 후보와 같으면 달라진 점 안내가 없다.
    assert page.locator('#results .plan-preview-changes').count() == 0
    assert '달라진 점' not in page.locator('#progress').inner_text()


def test_confirmed_courses_say_what_changed_from_the_preview(audit_page):
    page, base, errors = audit_page

    def change(data):
        plans = data['result']['plans']
        assert len(plans) == 3
        # 둘째 후보가 빠지고, 셋째 후보가 둘째 자리로 오며 이름이 바뀐 경우.
        plans[2]['option_purpose'] = '이름이 바뀐 코스'
        data['result']['plans'] = [plans[0], plans[2]]
        return data

    state = dict(change=change)
    hold(page, state)
    submit(page)
    options = page.evaluate('PlanPreview.options')
    state['release'] = True
    page.wait_for_function('selected?.id&&!document.querySelector("#submit-plan").disabled', timeout=45000)
    notice = page.locator('#results .plan-preview-changes')
    assert notice.count() == 1
    items = notice.locator('li').all_inner_texts()
    second = ' → '.join(p['name'] for p in options[1]['places'])
    assert items[0] == f'후보 2({second}) · 최종 코스에서 빠졌어요.'
    assert items[1].startswith('후보 3 · 코스 2 자리로 옮겼어요 · 이름이 ‘') and items[1].endswith('’에서 ‘이름이 바뀐 코스’(으)로 바뀌었어요.')
    assert len(items) == 2
    assert page.locator('#progress').inner_text().endswith('· 가격 확인 전 후보와 달라진 점이 있어요')
    # 안내는 결과 맨 위, 코스 카드보다 먼저. 다른 코스를 골라 다시 그려도 그대로 남는다.
    assert page.evaluate("document.querySelector('#results').firstElementChild.classList.contains('plan-preview-changes')")
    page.locator('#results .plan-option-tabs button').nth(1).click()
    page.wait_for_function('selected?.id===plans[1].id')
    assert page.locator('#results .plan-preview-changes').count() == 1
    assert no_overflow(page, 320) and no_overflow(page, 390)


def test_failure_and_cancel_remove_the_unconfirmed_preview(audit_page):
    page, base, errors = audit_page
    state = {}
    hold(page, state)
    submit(page)
    state['fail'] = True
    page.wait_for_function('document.querySelector("#progress").innerText.includes("검색을 완료하지 못했어요")', timeout=20000)
    assert page.locator('#results .plan-preview').count() == 0
    assert '가격 확인 전에 보여 드린 후보는 확정되지 않아 지웠어요.' in page.locator('#progress').inner_text()
    assert page.evaluate('selected===null')
    # 취소: 다시 검색해 확정 전 후보가 보일 때 취소하면 후보를 지운다.
    state['fail'] = False
    page.locator('#progress').get_by_role('button', name='조건 확인하고 다시 검색').click()
    submit(page)
    page.locator('#progress').get_by_role('button', name='검색 취소').click()
    page.wait_for_function('!document.querySelector("#results .plan-preview")', timeout=20000)
    assert page.evaluate('selected===null&&plans.length===0')
