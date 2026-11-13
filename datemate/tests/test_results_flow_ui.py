"""결과 화면이 사용자 흐름 순서(코스 카드 → 비교 → 선택 코스 → 지도 → 일정 → 확인 → 결정·공유 → 축제 → 부가)로 놓이는지 확인한다."""
import os
import re
from pathlib import Path
from test_functional_audit import audit_page, generate

# DOM 순서대로 있어야 하는 결과 화면 구역. 없는 구역(조건 안내 등)은 건너뛴다.
FLOW = ['#edit-conditions', '.results-area .section-heading h2', '#progress', '#results > .condition-differences',
        '#results > .plan-option-tabs', '#results > .comparison-details', '#results > .plan-card.selected',
        '#plan-map-slot', '#plan-detail .detail-header h2', '#plan-detail .stop', '#plan-detail .execution-summary',
        '#plan-detail .cost-table-details', '#plan-detail .planning-decision', '#plan-detail .share-actions',
        '#festival-section', '#plan-extras .leisure-course-panel', '#plan-extras .chat-form']

ORDER = '''sels=>{const found=sels.map(s=>[s,document.querySelector(s)]).filter(([,el])=>el);
  const bad=[];for(let i=1;i<found.length;i++){if(!(found[i-1][1].compareDocumentPosition(found[i][1])&Node.DOCUMENT_POSITION_FOLLOWING))bad.push(found[i-1][0]+' !< '+found[i][0]);}
  return {found:found.map(([s])=>s),bad};}'''

VISIBLE_ORDER = '''sels=>{const rows=sels.map(s=>[s,document.querySelector(s)]).filter(([,el])=>el&&el.getClientRects().length).map(([s,el])=>[s,el.getBoundingClientRect().top+scrollY]);
  const bad=[];for(let i=1;i<rows.length;i++)if(rows[i][1]<rows[i-1][1])bad.push(rows[i-1][0]+' 아래에 '+rows[i][0]);return bad;}'''

SMALL_BUTTONS = '''()=>[...document.querySelectorAll('.results-area button')].filter(el=>el.getClientRects().length&&!el.closest('.leaflet-container'))
  .filter(el=>el.getBoundingClientRect().height<43.5).map(el=>({text:el.textContent.trim().slice(0,30),height:el.getBoundingClientRect().height}))'''


def save(page, name):
    folder = os.getenv('DATEMATE_UI_ARTIFACT_DIR')
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name))


def test_mobile_results_follow_the_user_flow(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map-card')")
    # ① DOM 순서와 보이는 순서가 같다.
    order = page.evaluate(ORDER, FLOW)
    assert not order['bad'], order
    assert {'#results > .plan-option-tabs', '#plan-map-slot', '#festival-section', '#plan-extras .chat-form'} <= set(order['found'])
    assert not page.evaluate(VISIBLE_ORDER, FLOW)
    # ② 코스 카드만 보고 1·2·3안을 구분할 수 있다.
    tabs = page.evaluate('''()=>[...document.querySelectorAll('.plan-option-tabs button')].map((b,i)=>({text:b.textContent,places:plans[i].places.map(p=>p.name)}))''')
    assert len(tabs) >= 2
    for tab in tabs:
        assert all(name in tab['text'] for name in tab['places']), tab
        assert re.search(r'\d{2}:\d{2}–\d{2}:\d{2}', tab['text']) and '도보 ' in tab['text'] and '원' in tab['text'], tab
    assert '비교 기준' in tabs[0]['text'] and '비교 기준' not in tabs[1]['text']
    assert len({tab['text'] for tab in tabs}) == len(tabs)
    # 장소 순서 줄은 2줄로 잘려 보여도 전체 이름이 DOM에 남는다.
    assert page.locator('.plan-option-tabs .option-route').first.evaluate("el=>getComputedStyle(el).webkitLineClamp")=='2'
    cards = page.evaluate("()=>{const r=document.querySelector('.plan-option-tabs').getBoundingClientRect();return r.height}")
    assert cards <= 844 * 1.6, cards
    save(page, 'flow-mobile-cards.png')
    # ③ 닫힌 접힘 안에는 경고가 없다.
    assert page.evaluate("document.querySelectorAll('main details:not([open]) .warning').length") == 0
    # ⑤ 비교 표를 열면 코스·비용·이동 세 칸이 가로로 넘기지 않고 보인다.
    compare = page.locator('.comparison-details')
    assert compare.evaluate('el=>!el.open')
    compare.locator('summary').click()
    region = page.locator('.option-comparison [role=region]')
    assert region.get_attribute('tabindex') == '0'
    fit = region.evaluate('''el=>{const box=el.getBoundingClientRect();return [...el.querySelectorAll('tbody tr')].map(row=>({head:row.children[0].tagName+'/'+row.children[0].scope,
      right:row.children[2].getBoundingClientRect().right,limit:box.right+0.5}))}''')
    assert fit and all(r['head'] == 'TH/row' and r['right'] <= r['limit'] for r in fit), fit
    assert page.locator('.option-comparison caption').inner_text() == '세 코스 비용·이동 시간 비교'
    assert page.locator('.option-comparison thead th[scope=col]').count() == 5
    compare.scroll_into_view_if_needed()
    save(page, 'flow-mobile-compare.png')
    # ⑥ 보이는 버튼은 모두 44px 이상. ④ 360·430px에서 가로 넘침이 없다.
    for width in (360, 390, 430):
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
        assert not page.evaluate(SMALL_BUTTONS), (width, page.evaluate(SMALL_BUTTONS))


def test_map_moves_between_mobile_slot_and_desktop_rail(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 1280, 'height': 900})
    generate(page)
    # ⑦ 데스크톱은 오른쪽 패널, 모바일은 선택 카드 바로 뒤. 폭을 바꾸면 자리가 바뀐다.
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-map-card')")
    assert page.locator('#plan-map-slot').is_hidden()
    rail = page.locator('#plan-map-rail').bounding_box()
    results = page.locator('#results').bounding_box()
    assert rail['x'] >= results['x'] + results['width'] - 1
    assert not page.evaluate(SMALL_BUTTONS)
    assert page.locator('.comparison-details').evaluate('el=>el.open')
    save(page, 'flow-desktop.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.querySelector('#plan-map-slot .plan-map-card')")
    assert page.locator('#plan-map-rail').is_hidden() and page.locator('.plan-map-card').count() == 1
    assert page.evaluate("document.querySelector('#results > .plan-card.selected').nextElementSibling.id") == 'plan-map-slot'
    page.locator('#plan-map-slot .map-option-tabs button').nth(1).click()
    page.wait_for_function("document.querySelector('.plan-option-tabs [aria-pressed=true]').dataset.option==='2'")
    assert page.locator('#plan-map-slot .map-option-tabs [aria-pressed=true]').get_attribute('data-map-option') == '2'
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.wait_for_function("document.querySelector('#plan-map-rail .plan-map-card')")
    assert page.locator('#plan-map-slot').is_hidden() and page.locator('.plan-map-card').count() == 1
