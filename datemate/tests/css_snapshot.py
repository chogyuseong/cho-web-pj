"""CSS 정리용 화면 계산값 찍기(설계: datemate/docs/css-consolidation-plan-2026-11-18.md 5-0). CSS 를 바꾸기 전과 후에 같은 장면을 찍어 비교한다.

평소 전체 테스트에는 들어가지 않는다(파일 이름이 test_ 로 시작하지 않음). 직접 경로를 주고, 저장할 폴더를 환경변수로 준다:
    CSS_SNAPSHOT_OUT=/tmp/css-before python -m pytest tests/css_snapshot.py -q -p no:cacheprovider
    (CSS 수정)
    CSS_SNAPSHOT_OUT=/tmp/css-after  python -m pytest tests/css_snapshot.py -q -p no:cacheprovider
    python scripts/css_snapshot_compare.py /tmp/css-before /tmp/css-after
같은 컨테이너에서 연달아 찍어야 한다(글꼴·브라우저가 같아야 픽셀이 같다). 장면 하나만: -k results_demo.

찍는 것(장면 × WIDTHS):
  · body 아래 모든 요소의 getComputedStyle 전 속성 + ::before·::after(content 가 있을 때)·::placeholder 를 이은 문자열의 해시와 화면 상자(0.1px).
    해시만 저장하는 까닭: 장면×폭×요소×속성 전부를 글자로 두면 수백 MB 다. 차이가 난 요소의 속성을 보려면
    CSS_SNAPSHOT_DETAIL='경로 일부' 를 주고 다시 찍으면 그 요소들은 속성 전체를 함께 저장한다(비교 도구가 속성별로 보여 줌).
  · 전체 페이지 스크린샷(PNG). 비교 도구가 픽셀 차이를 센다.
빼는 것: 지도 내부(.leaflet-container·.naver-plan-map 의 자손 — 타일·확대 상태가 실행마다 다름), <script>·<style>·<link>.
안정화: 동작 줄이기(prefers-reduced-motion)로 찍고, 남은 유한 애니메이션은 끝으로 보내며, 글꼴 로드를 기다린다. CSS 는 넣지 않는다.
허용 오차는 0 이다(같은 계산값·같은 상자·같은 픽셀). 무변경 두 번 찍기의 차이가 0 이어야 이 도구를 믿을 수 있다.

장면을 더할 때: SCENES 에 (이름, 준비 함수) 를 넣는다. 준비 함수는 page 를 그 화면으로 만들고 끝낸다(폭 바꾸기·찍기는 공통).
아직 안 넣은 상태: :hover·:focus-visible 표본(설계 5-5 전에 더할 것), 강제 색상.
"""
import json
import os
import pathlib

import pytest

from test_functional_audit import audit_page, generate  # noqa: F401  (audit_page 는 fixture)

OUT = os.getenv('CSS_SNAPSHOT_OUT', '')
DETAIL = os.getenv('CSS_SNAPSHOT_DETAIL', '')
# 설계의 끊는 점(360/420/480/600/720/760/800/1000/1100/1280/1461) 사이마다 하나씩.
WIDTHS = [320, 390, 450, 560, 700, 740, 780, 900, 1050, 1200, 1440, 1600]
pytestmark = pytest.mark.skipif(not OUT, reason='CSS_SNAPSHOT_OUT 를 줄 때만 찍는다')

CAPTURE = r"""detail=>{
  const skip=e=>e.closest('.leaflet-container,.naver-plan-map')&&!e.matches('.leaflet-container,.naver-plan-map');
  const name=e=>{let s=e.tagName.toLowerCase();if(e.id)return s+'#'+e.id;
    const cls=[...e.classList].slice(0,2).join('.');if(cls)s+='.'+cls;
    const p=e.parentElement;if(p){const same=[...p.children].filter(c=>c.tagName===e.tagName);if(same.length>1)s+=':'+(same.indexOf(e)+1);}return s;};
  const path=e=>{const parts=[];for(let x=e;x&&x!==document.documentElement;x=x.parentElement){parts.unshift(name(x));if(x.id)break;}return parts.join('>');};
  // 속성 이름을 정렬한다: CSS 변수(--muted 등)를 나열하는 순서가 실행마다 달라 값이 같아도 해시가 달라졌다(2026-11-18 무변경 비교에서 확인).
  const text=cs=>{const names=[];for(let i=0;i<cs.length;i++)names.push(cs[i]);names.sort();let out='';for(const p of names)out+=p+':'+cs.getPropertyValue(p)+';';return out;};
  const hash=s=>{let a=0x811c9dc5,b=0x9747b28c;for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);a=Math.imul(a^c,16777619);b=Math.imul(b^c,2246822519)^(b>>>13);}
    return (a>>>0).toString(16).padStart(8,'0')+(b>>>0).toString(16).padStart(8,'0');};
  const rows={},details={};
  for(const e of [document.documentElement,...document.body.querySelectorAll('*')]){
    if(e!==document.documentElement&&(skip(e)||['SCRIPT','STYLE','LINK','TEMPLATE'].includes(e.tagName)))continue;
    let key=e===document.documentElement?'html':path(e);let n=2;while(rows[key])key=path(e)+'~'+(n++);
    let s='@'+text(getComputedStyle(e));
    for(const pseudo of ['::before','::after']){const cs=getComputedStyle(e,pseudo);if(cs.content&&cs.content!=='none'&&cs.content!=='normal')s+=pseudo+text(cs);}
    if(e.matches('input,textarea'))s+='::placeholder'+text(getComputedStyle(e,'::placeholder'));
    const r=e.getBoundingClientRect(),k=v=>Math.round(v*10)/10;
    rows[key]=[hash(s),k(r.left+scrollX),k(r.top+scrollY),k(r.width),k(r.height)];
    if(detail&&key.includes(detail))details[key]=s;
  }
  return {rows,details,scroll:[document.documentElement.scrollWidth,document.documentElement.scrollHeight]};
}"""
# 맨 위로 올린 뒤 찍는다: 머리글이 sticky 라 스크롤 위치에 따라 문서상 위치(top+scrollY)가 달라졌다(무변경 비교에서 확인).
SETTLE = """async()=>{scrollTo(0,0);await document.fonts.ready;document.activeElement?.blur?.();
  for(const a of document.getAnimations()){try{if(Number.isFinite(a.effect?.getComputedTiming?.().endTime))a.finish();else a.pause();}catch{}}
  await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}"""


def open_all_details(page, scope='main'):
    page.evaluate(f"document.querySelectorAll('{scope} details').forEach(d=>d.open=true)")


def scene_home(page, base):
    pass


def scene_home_expanded(page, base):
    open_all_details(page, 'body')


def scene_results_demo(page, base):
    generate(page)
    open_all_details(page)


def scene_results_course2(page, base):
    from test_functional_audit import wait_for_selected_detail
    generate(page)
    page.locator('.plan-option-tabs button').nth(1).click()
    wait_for_selected_detail(page)
    open_all_details(page)


def scene_results_real(page, base):
    """실제 장소처럼 다시 그린 결과(사진·블로그·메뉴·주차·대중교통 비교 패널까지). 외부 응답은 모두 가짜."""
    from test_parking_ui import REAL, car_leg, lots_for
    from test_results_extras_ui import mount_photo_routes
    from test_transit_compare_ui import answer, to_transit
    mount_photo_routes(page, base)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': '없음'}))
    page.route('**/api/places/*/menu?*', lambda route: route.fulfill(json={'status': 'available', 'checked_at': '2026-11-18',
        'items': [{'name': '대표 메뉴', 'display_price': '12,000원'}, {'name': '두 번째 메뉴', 'display_price': '9,000원'}]}))
    generate(page)
    to_transit(page)
    car_leg(page, 1)
    place = page.evaluate('selected.places[1]')
    page.route('**/api/plans/*/parking', lambda route: route.fulfill(json=dict(
        status='available', note='', source_type='네이버 지역 검색', message='', diagnostics={},
        stops=[dict(index=1, place_id=place['id'], place_name=place['name'], status='available', message='', lots=lots_for(place))])))
    body = answer(page)
    page.route('**/api/plans/*/transit-compare', lambda route: route.fulfill(json=body))
    page.evaluate('statusData.transit_compare_available=true;' + REAL)
    page.locator('.transit-compare-start').click()
    page.wait_for_function("document.querySelectorAll('.transit-option').length>0")
    # 사진·주차는 화면 근처에서 받으므로 끝까지 한 번 훑는다.
    page.evaluate("""async()=>{for(let y=0;y<document.body.scrollHeight;y+=600){scrollTo(0,y);await new Promise(r=>setTimeout(r,60));}scrollTo(0,0);}""")
    page.wait_for_load_state('networkidle')
    open_all_details(page)


def scene_results_print(page, base):
    generate(page)
    open_all_details(page)
    page.emulate_media(media='print', reduced_motion='reduce')


def scene_explore(page, base):
    from test_results_extras_ui import mount_photo_routes
    mount_photo_routes(page, base)
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.wait_for_function("document.querySelector('#catalog .place-card .place-photo img')")
    page.wait_for_load_state('networkidle')


def scene_shared(page, base):
    generate(page)
    url = page.evaluate("api('/plans/'+selected.id+'/shares',{}).then(r=>r.url)")
    page.goto(base + url)
    page.wait_for_function("document.querySelectorAll('#shared-places article').length>0")


def scene_feedback(page, base):
    page.goto(base + '/feedback')
    page.wait_for_load_state('networkidle')


def scene_feedback_admin(page, base):
    page.goto(base + '/feedback/admin')
    page.wait_for_load_state('networkidle')


SCENES = [(f.__name__.removeprefix('scene_'), f) for f in (
    scene_home, scene_home_expanded, scene_results_demo, scene_results_course2, scene_results_real,
    scene_results_print, scene_explore, scene_shared, scene_feedback, scene_feedback_admin)]


@pytest.mark.parametrize('name,prepare', SCENES, ids=[n for n, _ in SCENES])
def test_capture(audit_page, name, prepare):
    page, base, errors = audit_page
    page.emulate_media(reduced_motion='reduce')
    prepare(page, base)
    # 장면 준비 뒤 늦게 그려지는 칸(코스 탭 전환 뒤 '함께 정하기' 등)이 실행마다 찍히거나 안 찍혔다 → 네트워크가 잠잠해질 때까지 기다린다.
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(500)
    open_all_details(page, 'body')
    out = pathlib.Path(OUT) / name
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(150)
        page.evaluate(SETTLE)
        result[str(width)] = page.evaluate(CAPTURE, DETAIL)
        # 스크린샷에서 가리는 것(스타일·상자는 styles 로 그대로 비교된다):
        #   지도 칸 — 타일·확대가 실행마다 달라 픽셀이 바뀜(스타일 비교에서도 지도 내부는 뺐다).
        #   알림(#toast) — 화면 아래 가운데에 잠깐 뜨고, 사라지는 시점이 실행마다 달랐다(무변경 비교에서 확인).
        #   지도 설명 줄(.plan-map .map-caption) — 테스트는 바깥 타일을 막아 '지도 배경을 불러오지 못했어요' 문구가 뜨는 시점이 실행마다 달랐다.
        page.screenshot(path=str(out / f'{width}.png'), full_page=True, animations='disabled', caret='hide',
                        mask=[page.locator('.leaflet-container, .naver-plan-map, #toast, .plan-map .map-caption')], mask_color='#ff00ff')
    (out / 'styles.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
