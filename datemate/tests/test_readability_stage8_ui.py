"""가독성 8단계(2026-11-18): 지도 아래 장소 목록의 「일정에서 보기」, 대체 지도(Leaflet)의 겹친 장소 번호 합치기.

1) 지도 아래 목록 한 줄 = 네이버 지도 링크 + 「일정에서 보기」 단추. 누르면 일정의 그 장소 카드로 가고 제목에 포커스(focusPlanStop).
   지도 표시는 키보드 Tab 으로 닿지 않아 키보드·화면 읽기 사용자의 길이다.
2) 네이버 지도(test_readability_stage7_ui)처럼 대체 지도도 화면에서 38px 보다 가까운 번호 원을 '2·3' 원 하나로 묶고,
   확대(zoomend)하면 다시 나눈다. 데모 장소는 서로 멀어서, 2·3번 장소를 거의 같은 좌표로 옮겨 겹침을 만든다."""
import pytest

from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_map_ui import LEAFLET_CAPTURE
from test_readability_stage6_ui import FOCUSED, release_finished_plan_jobs  # noqa: F401

# 지금 그려진 장소 번호 원: 툴팁 글자, 화면 읽기 이름, 화면 좌표.
CIRCLES = """()=>{const m=courseMaps.at(-1),box=m.getContainer().getBoundingClientRect();
  const out=[];m.eachLayer(l=>{if(l.options?.className?.includes('route-stop-circle')){const c=m.latLngToContainerPoint(l.getLatLng());
    out.push({tip:l.getTooltip()?.getContent()?.textContent,label:l.getElement()?.getAttribute('aria-label'),merged:l.options.className.includes('merged'),
      x:box.left+c.x,y:box.top+c.y});}});
  return out.sort((a,b)=>a.tip.localeCompare(b.tip,'ko',{numeric:true}));}"""


@pytest.mark.parametrize('width', [390, 1440])
def test_map_place_list_jumps_to_the_place_card(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 844})
    generate(page)
    holder = '#plan-map-slot' if width == 390 else '#plan-map-rail'
    rows = page.locator(f'{holder} .map-place-list .map-place-row')
    names = page.evaluate('selected.places.map(p=>p.name)')
    assert rows.count() == len(names)
    for number, name in enumerate(names, 1):
        row = rows.nth(number - 1)
        assert row.locator('a').inner_text() == f'{number}. {name}'
        go = row.get_by_role('button', name=f'{number}번 {name} 일정에서 보기', exact=True)
        assert go.inner_text() == '일정에서 보기'
    last = rows.nth(len(names) - 1).locator('.map-place-go')
    last.scroll_into_view_if_needed()
    box = last.bounding_box()
    assert box['height'] >= 43.5
    last.click()
    page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
    page.wait_for_timeout(700)
    state = page.evaluate(FOCUSED)
    assert state['index'] == len(names) - 1 and state['inView'] and state['name'] == names[-1], state
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors, errors


@pytest.mark.parametrize('width', [390, 1440])
def test_leaflet_merges_overlapping_stop_numbers_and_splits_on_zoom(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 844})
    page.evaluate(LEAFLET_CAPTURE)
    generate(page)
    holder = '#plan-map-slot' if width == 390 else '#plan-map-rail'
    page.wait_for_function(f"document.querySelector('{holder} .fallback-plan-map')&&courseMaps.length", timeout=20000)
    names = page.evaluate('selected.places.map(p=>p.name)')
    assert len(names) >= 3
    # 처음(데모 장소는 서로 멂): 번호마다 원 하나, 예전과 같은 이름.
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom")
    assert [c['tip'] for c in page.evaluate(CIRCLES)] == [f'{n} · {names[n - 1]}' for n in range(1, len(names) + 1)]
    # 3번 장소를 2번에서 북쪽 약 33m 로 옮겨 다시 그린다 → 코스 전체가 보이는 확대(약 1km 간격)에서는 몇 px 라 '2·3' 원 하나.
    before = page.evaluate('courseMaps.length')
    page.evaluate("""()=>{const a=selected.places[1],b=selected.places[2];b.lat=a.lat+0.0003;b.lon=a.lon;renderDetail();}""")
    page.wait_for_function('n=>courseMaps.length>n', arg=before, timeout=20000)
    page.wait_for_function("!courseMaps.at(-1)._animatingZoom&&courseMaps.at(-1).getSize().x>0")
    page.locator(f'{holder} .fallback-plan-map').scroll_into_view_if_needed()
    page.wait_for_timeout(600)  # 첫 맞춤(fit: requestAnimationFrame·ResizeObserver)이 끝날 때까지
    circles = page.evaluate(CIRCLES)
    tips = [c['tip'] for c in circles]
    assert f'2·3 · {names[1]} / {names[2]}' in tips and len(circles) == len(names) - 1, tips
    merged = next(c for c in circles if c['merged'])
    assert merged['label'] == '2·3번 장소 · 눌러서 일정에서 2번부터 보기'
    # 합친 원을 누르면 앞 번호(2번) 장소로.
    target = page.evaluate("([x,y])=>{const e=document.elementFromPoint(x,y);return e?.getAttribute('class')||e?.tagName}", [merged['x'], merged['y']])
    if 'leaflet-tooltip' in (target or ''):
        pytest.skip(f'장소 이름 말풍선이 겹쳐 합친 원을 누를 수 없는 배치: {target}')
    page.mouse.click(merged['x'], merged['y'])
    page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
    assert page.evaluate(FOCUSED)['index'] == 1
    # 19레벨로 확대하면 33m 가 100px 넘게 벌어져 다시 번호마다 하나(zoomend 로 다시 묶음), 처음 확대로 돌아가면 다시 합친다.
    fitted = page.evaluate('courseMaps.at(-1).getZoom()')
    zoom = "z=>{const m=courseMaps.at(-1);m.setView([selected.places[1].lat,selected.places[1].lon],z,{animate:false});}"
    page.evaluate(zoom, 19)
    page.wait_for_timeout(300)
    split = page.evaluate(CIRCLES)
    assert not any(c['merged'] for c in split) and len(split) == len(names), [c['tip'] for c in split]
    assert {c['label'] for c in split} >= {'2번 장소 · 눌러서 일정에서 보기', '3번 장소 · 눌러서 일정에서 보기'}
    page.evaluate(zoom, fitted)
    page.wait_for_timeout(300)
    assert sum(c['merged'] for c in page.evaluate(CIRCLES)) == 1
    assert not errors, errors
