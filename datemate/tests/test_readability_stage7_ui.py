"""가독성 7단계(2026-11-18): 네이버 지도에서 화면상 겹치는 장소 번호를 '2·3' 표시 하나로 합친다.

운영 성수 코스(390px, 확대 14)에서 2·3번 표시가 7px 거리로 겹쳐 2번 원 가운데를 누르면 98%가 3번으로 갔다.
maps.js 는 지도 투영(getProjection().fromCoordToOffset)으로 번호 표시 사이 화면 거리를 재고, 표시 지름(38px)보다 가까우면
한 표시로 그린다. 합친 표시는 앞 번호 장소로 가고, 확대·축소(zoom_changed)하면 다시 묶는다.
가짜 SDK(test_popup_map_ui.NAVER_STUB)에 투영을 붙여, 장소별 화면 좌표를 테스트가 정한다(window.__offsets).
투영이 없는 SDK(기존 가짜 SDK)에서는 전처럼 번호마다 하나씩 그린다(test_readability_stage6_ui 가 확인)."""
import pytest

from test_functional_audit import audit_page, generate  # noqa: F401
from test_popup_map_ui import NAVER_STUB
from test_readability_stage6_ui import FOCUSED, NAVER_MARKERS, release_finished_plan_jobs  # noqa: F401

# 공용 가짜 SDK(test_popup_map_ui.NAVER_STUB)의 Map 정의를 글자 그대로 찾아 투영을 붙인 것으로 바꾼다.
# 공용 가짜 SDK 의 Map 줄을 고치면 이 assert 가 먼저 실패하므로, 그때 아래 STUB_MAP 을 새 정의에 맞춘다.
STUB_MAP = "Map:function(){this.fitBounds=()=>{window.__fits++;};this.destroy=()=>{};},"
assert STUB_MAP in NAVER_STUB
# 화면 좌표: window.__offsets['lat,lon'] 이 있으면 그 값, 없으면 크게 벌린 좌표(어느 두 장소도 겹치지 않음).
# 실제 SDK 처럼 '지금 확대 수준'의 좌표를 흉내 내려면 __offsets 를 바꾸고 zoom_to 로 zoom_changed 처리를 부른다.
NAVER_STUB_WITH_PROJECTION = NAVER_STUB.replace(STUB_MAP, """Map:function(){this.fitBounds=()=>{window.__fits++;};this.destroy=()=>{};
      this.getProjection=()=>({fromCoordToOffset:c=>{const o=(window.__offsets||{})[c.lat()+','+c.lng()];
        return o?new naver.maps.Point(o[0],o[1]):new naver.maps.Point(c.lng()*1e7,-c.lat()*1e7);}});},""")


def stop_markers(page):
    return page.evaluate(f"""()=>window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes('route-stop-marker')).map(m=>({{
      html:m.options.icon.content,title:m.options.title,anchor:[m.options.icon.anchor.x,m.options.icon.anchor.y],
      at:[m.options.position.lat(),m.options.position.lng()],
      clicks:window.__naverListeners.filter(l=>l.target===m&&l.name==='click'&&!l.removed).length}}))""")


def zoom_to(page, offsets):
    """장소 순번별 화면 좌표를 정하고 지도의 zoom_changed 처리를 부른다(실제 SDK 는 확대·축소 때 부름)."""
    page.evaluate("""offsets=>{window.__offsets={};offsets.forEach((o,i)=>{const p=selected.places[i];window.__offsets[p.lat+','+p.lon]=o;});
      window.__naverListeners.filter(l=>l.name==='zoom_changed'&&!l.removed).at(-1).fn();}""", offsets)


def label_of(marker):
    return marker['html'].rsplit('">', 1)[1].removesuffix('</span>')


@pytest.mark.parametrize('width', [390, 1440])
def test_overlapping_stop_numbers_merge_and_split_again_on_zoom(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 844})
    page.evaluate(NAVER_STUB_WITH_PROJECTION)
    generate(page)
    holder = '#plan-map-slot' if width == 390 else '#plan-map-rail'
    page.wait_for_function(f"document.querySelector('{holder} .naver-plan-map')&&window.__naverMarkers.length>=3", timeout=20000)
    places = page.evaluate('selected.places.map(p=>p.name)')
    assert len(places) >= 3, places
    # 처음 그린 모습: 투영 좌표가 멀어 번호마다 하나(전과 같은 이름).
    first = stop_markers(page)
    assert [label_of(m) for m in first] == [str(n) for n in range(1, len(places) + 1)], first
    assert all('route-stop-merged' not in m['html'] and m['anchor'] == [19, 19] for m in first), first
    assert page.evaluate("window.__naverListeners.filter(l=>l.name==='zoom_changed').length") == 1

    # 축소: 2·3번이 7px 거리(운영 측정과 같은 겹침), 1번은 100px 떨어짐 → '1', '2·3'.
    offsets = [[0, 0], [100, 0], [100, 7]] + [[300 + 100 * i, 0] for i in range(len(places) - 3)]
    zoom_to(page, offsets)
    merged_view = stop_markers(page)
    labels = [label_of(m) for m in merged_view]
    assert labels[:2] == ['1', '2·3'] and len(labels) == len(places) - 1, merged_view
    merged = merged_view[1]
    assert ('class="route-marker route-stop-marker route-stop-merged" style="width:56px" role="button" '
            'aria-label="2·3번 장소 · 눌러서 일정에서 2번부터 보기">2·3</span>') in merged['html'], merged
    assert merged['anchor'] == [28, 19] and merged['clicks'] == 1, merged
    assert merged['title'] == f'2 · {places[1]} / 3 · {places[2]}', merged
    # 자리는 두 장소의 가운데.
    two, three = page.evaluate('[selected.places[1],selected.places[2]]')
    assert merged['at'] == pytest.approx([(two['lat'] + three['lat']) / 2, (two['lon'] + three['lon']) / 2])
    # 앞에 그린 번호 표시는 모두 지도에서 내렸다(지도에 남은 번호 표시 = 지금 묶음 수).
    assert page.evaluate("window.__naverMarkers.filter(m=>m.options.icon.content.includes('route-stop-marker')&&!m.removed).length") == len(labels)

    # 합친 표시를 누르면 앞 번호(2번) 장소 제목으로 간다.
    page.evaluate(f"document.querySelector('{holder} .naver-plan-map').scrollIntoView({{block:'center',behavior:'instant'}})")
    page.evaluate("""()=>{const m=window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes('route-stop-merged')).at(-1);
      window.__naverListeners.filter(l=>l.target===m&&l.name==='click'&&!l.removed).forEach(l=>l.fn());}""")
    page.wait_for_function("document.activeElement?.matches('#plan-detail .timeline-card>h4')")
    page.wait_for_timeout(700)
    state = page.evaluate(FOCUSED)
    assert state['index'] == 1 and state['inView'] and state['name'] == places[1], state

    # 확대: 2·3번이 40px(표시 지름 38px 보다 멂) → 다시 번호마다 하나.
    zoom_to(page, [[0, 0], [100, 0], [140, 0]] + [[300 + 100 * i, 0] for i in range(len(places) - 3)])
    split = stop_markers(page)
    assert [label_of(m) for m in split] == [str(n) for n in range(1, len(places) + 1)], split
    for number, marker in enumerate(split, 1):
        assert f'role="button" aria-label="{number}번 장소 · 눌러서 일정에서 보기">{number}</span>' in marker['html'], marker
        assert marker['clicks'] == 1 and marker['anchor'] == [19, 19], marker

    # 셋 이상이 한자리: 1·2·3 하나(너비 74px, 기준점 가운데).
    zoom_to(page, [[0, 0], [5, 0], [0, 6]] + [[300 + 100 * i, 0] for i in range(len(places) - 3)])
    trio = stop_markers(page)[0]
    assert label_of(trio) == '1·2·3' and 'style="width:74px"' in trio['html'] and trio['anchor'] == [37, 19], trio
    # 출발 표시는 그대로 하나이고 동작이 없다.
    start = [m for m in page.evaluate(NAVER_MARKERS) if '>출발<' in m['html']]
    assert len(start) == 1 and start[0]['clicks'] == 0, start
    assert not errors, errors


def test_merged_marker_text_fits_inside_the_pill(audit_page):
    """합친 표시의 글자가 알약 안에 들어가는지 실제 CSS 로 잰다(두 자리 번호 포함). 가짜 SDK 는 표시 DOM 을 만들지 않아 직접 넣는다."""
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    # 너비는 maps.js 의 stopMarkerWidth 를 그대로 써서(공식을 여기 다시 적지 않음) 공식이 바뀌어도 '글자가 들어가는지'만 본다.
    # 아래 [56, 56, 74, 74] 는 지금 공식의 값이라, 공식을 일부러 바꾸면 이 줄과 위 테스트의 56/74·기준점도 함께 고친다.
    sizes = page.evaluate("""()=>['2·3','10·11','1·2·3','8·9·10'].map(label=>{
      const n=label.split('·').length,box=document.createElement('div');
      box.innerHTML='<span class="route-marker route-stop-marker'+(n>1?' route-stop-merged" style="width:'+stopMarkerWidth(n)+'px':'')+'">'+label+'</span>';
      document.body.append(box);const span=box.firstChild,style=getComputedStyle(span);
      const result={label,width:span.getBoundingClientRect().width,height:span.getBoundingClientRect().height,
        overflow:span.scrollWidth>span.clientWidth,radius:style.borderTopLeftRadius,cursor:style.cursor};
      box.remove();return result;})""")
    for size in sizes:
        assert not size['overflow'] and size['height'] == 38 and size['radius'] == '19px' and size['cursor'] == 'pointer', size
    assert [s['width'] for s in sizes] == [56, 56, 74, 74], sizes
    assert not errors, errors
