"""사용자 피드백 반영 화면: 태그라인, 축제 기준 코스·지도 표시, 이동 수단, 링크 버튼, 현재 구역 표시, 확인 상태 배지."""
import json
from test_functional_audit import audit_page, generate

FESTIVALS = [
    dict(id='201', title='점검 등불축제', start='2026-01-01', end='2027-12-31', region='서울', address='서울특별시 종로구 점검로',
         source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=a', image_url=None, image_license=None, lat=37.5762, lon=126.9850),
    dict(id='202', title='<img src=x id=xss-check>점검 야시장', start='2026-01-01', end='2027-12-31', region='서울', address='서울특별시 중구 점검로',
         source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=b', image_url=None, image_license=None, lat=37.5700, lon=126.9900),
    dict(id='203', title='좌표 없는 점검 축제', start='2026-01-01', end='2027-12-31', region='서울', address='서울특별시 중구',
         source_url='https://korean.visitkorea.or.kr/search/search_list.do?keyword=c', image_url=None, image_license=None, lat=None, lon=None),
]


def route_festivals(page, hours=None):
    page.route('**/api/festivals?*', lambda route: route.fulfill(json=dict(status='available', festivals=FESTIVALS, total_matches=3, truncated=False, message='한국관광공사 행사정보 자료입니다.')))
    page.route('**/api/festivals/*/detail', lambda route: route.fulfill(json=dict(status='available', fee='무료', hours=hours, place=None, checked_at='2026-10-24', message='')))


def test_header_tagline_fits_mobile_without_overlapping_navigation(audit_page):
    page, base, errors = audit_page
    assert page.locator('header .brand-tagline').inner_text() == '당신의 시간과 피로를 위해'
    for width in (360, 390, 768, 1440):
        page.set_viewport_size({'width': width, 'height': 800})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
        boxes = page.evaluate('''()=>{const t=document.querySelector('header .brand-tagline').getBoundingClientRect(),n=document.querySelector('header nav').getBoundingClientRect();
            return {overlap:!(t.right<=n.left||n.right<=t.left||t.bottom<=n.top||n.bottom<=t.top),right:t.right,width:innerWidth,visible:t.width>0}}''')
        assert boxes['visible'] and not boxes['overlap'] and boxes['right'] <= boxes['width'], (width, boxes)


def test_choosing_and_clearing_a_festival_changes_the_request(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    generate(page)
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    submitted = []
    page.route('**/api/plan-jobs', lambda route: (submitted.append(json.loads(route.request.post_data)), route.fulfill(status=503, json={'detail': '점검용 중단'})))
    cards = page.locator('#festival-results .festival-card')
    assert '위치 좌표가 없어' in cards.nth(2).inner_text()
    cards.nth(0).get_by_role('button', name='이 축제 주변 코스 추천받기', exact=True).click()
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    chosen = submitted[-1]
    assert chosen['mode'] == 'real' and chosen['festival']['id'] == '201'
    assert chosen['origin']['lat'] == 37.5762 and chosen['origin']['name'].endswith('점검 등불축제 행사장 주변')
    note = page.locator('#festival-origin-note')
    assert note.is_visible() and '‘점검 등불축제’ 기준 코스' in note.inner_text()
    page.wait_for_function('document.querySelectorAll("#festival-results .festival-card").length===3')
    assert cards.nth(0).get_by_role('button', name='이 축제 선택 해제', exact=True).count() == 1
    note.get_by_role('button', name='축제 선택 해제 · 원래 조건으로 다시 추천', exact=True).click()
    for _ in range(100):
        if len(submitted) >= 2: break
        page.wait_for_timeout(50)
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    restored = submitted[-1]
    assert restored['mode'] == 'demo' and restored['festival'] is None
    assert restored['origin']['name'] == '데모 출발점' and restored['visit_date'] == '2026-10-24' and restored['region'] == '서울'
    assert note.is_hidden()


def test_course_map_marks_festivals_on_leaflet_fallback(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    page.evaluate('statusData.map_js_key=null')
    generate(page)
    page.wait_for_function('document.querySelectorAll(".plan-map .festival-circle").length===2', timeout=20000)
    note = page.locator('.plan-map .map-festival-note')
    assert '방문일 축제 2곳' in note.inner_text() and '코스에는 포함되지 않아요' in note.inner_text()
    assert page.locator('#xss-check').count() == 0
    page.evaluate("FestivalPanel.chosen={festival:FestivalPanel.mapItems[0],originName:'점검'};FestivalPanel.refreshMaps()")
    page.wait_for_function('document.querySelectorAll(".plan-map .festival-circle-chosen").length===1')
    assert page.locator('.plan-map .festival-circle').count() == 2
    assert page.locator('.plan-map .leaflet-tooltip').filter(has_text='축제 · 점검 등불축제').count() == 1
    assert '진한 표시가 고른 축제' in note.inner_text()
    page.evaluate('FestivalPanel.chosen=null')


NAVER_STUB = '''()=>{
  window.__naverMarkers=[];
  function LatLng(lat,lng){this.lat=()=>lat;this.lng=()=>lng;}
  window.naver={maps:{LatLng,Point:function(){},LatLngBounds:function(){this.extend=()=>{};this.hasLatLng=()=>true;},
    Map:function(){this.fitBounds=()=>{};this.destroy=()=>{};},
    Marker:function(options){this.options=options;this.setMap=map=>{this.removed=!map;};window.__naverMarkers.push(this);},
    Polyline:function(){},Circle:function(){},InfoWindow:function(options){this.content=options.content;this.open=()=>{};},
    Event:{addListener:()=>{}}}};
  statusData.map_js_key='stub-key';
}'''


def test_course_map_marks_festivals_on_naver_map(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    page.evaluate(NAVER_STUB)
    generate(page)
    active = 'window.__naverMarkers.filter(m=>!m.removed&&m.options.icon.content.includes("festival-marker"))'
    page.wait_for_function(f'{active}.length===2', timeout=20000)
    markers = page.evaluate(f'{active}.map(m=>({{title:m.options.title,content:m.options.icon.content,info:m.options.position.lat()}}))')
    assert {m['title'] for m in markers} == {'축제 · 점검 등불축제', '축제 · <img src=x id=xss-check>점검 야시장'}
    # 축제 이름은 마커 HTML에 들어가지 않는다.
    assert all(m['content'] == '<span class="route-marker festival-marker">축제</span>' for m in markers)
    assert page.locator('#xss-check').count() == 0
    page.evaluate("FestivalPanel.chosen={festival:FestivalPanel.mapItems[0],originName:'점검'};FestivalPanel.refreshMaps()")
    page.wait_for_function(f'{active}.filter(m=>m.options.icon.content.includes("festival-marker-chosen")).length===1')
    assert page.evaluate(f'{active}.length') == 2
    page.evaluate('FestivalPanel.chosen=null')


def test_travel_time_names_the_mode_everywhere(audit_page):
    page, base, errors = audit_page
    generate(page)
    cells = page.locator('.option-comparison td:nth-child(4)').all_inner_texts()
    assert cells and all(text.startswith('도보 ') and '가상 직선거리 추정' in text for text in cells)
    assert '총 이동 시간 (수단 · 근거)' in page.locator('.option-comparison th').all_inner_texts()
    assert '이동 시간 · 도보 · 가상 직선거리 추정' in page.locator('.plan-card.selected .stats').inner_text()
    lines = page.locator('#plan-detail .route-line').all_inner_texts()
    assert lines and all('· 도보 ' in line and '가상 추정' in line for line in lines)
    assert '도보 · 가상 직선거리 추정' in page.locator('.execution-grid').inner_text()
    assert '도보 · 가상 직선거리 추정' in page.locator('.map-travel-mode').inner_text()
    labels = page.evaluate('''()=>[
      travelMode({conditions:{transport:'car',mode:'real'},legs:[{status:'api'},{status:'api'}]}).label,
      travelMode({conditions:{transport:'car',mode:'real'},legs:[{status:'api'},{status:'estimated'}]}).label,
      travelMode({conditions:{transport:'transit',mode:'real'},legs:[{status:'estimated'}]}).label,
      legModeLabel({conditions:{transport:'car',mode:'real'}},{status:'api',minutes:12})]''')
    assert labels == ['자동차 · 네이버 길찾기', '자동차 · 일부 네이버 길찾기 · 일부 추정', '대중교통 · 추정', '자동차 12분 · 네이버 길찾기']


def test_source_urls_become_named_buttons_and_print_keeps_address(audit_page):
    page, base, errors = audit_page
    result = page.evaluate('''()=>{
      const p=linkedText('p','근거: https://map.naver.com/p/search/%EC%B9%B4%ED%8E%98 · https://m.blog.naver.com/test/123 · https://example.com/a. javascript:alert(1)','named-link-test');
      document.querySelector('main').append(p);
      return [...p.querySelectorAll('a.source-url-link')].map(a=>({text:a.textContent,href:a.href,rel:a.rel,target:a.target}));}''')
    assert [r['text'] for r in result] == ['네이버 지도에서 보기 ↗', '블로그 글 보기 ↗', '출처 보기 ↗']
    assert all(r['rel'] == 'noopener noreferrer' and r['target'] == '_blank' for r in result)
    assert result[0]['href'].startswith('https://map.naver.com/p/search/') and result[2]['href'] == 'https://example.com/a'
    text = page.locator('.named-link-test').inner_text()
    assert 'https://' not in text.replace('javascript:alert(1)', '') and page.locator('.named-link-test a[href^="javascript"]').count() == 0
    page.emulate_media(media='print')
    after = page.evaluate("getComputedStyle(document.querySelector('.named-link-test a.source-url-link'),'::after').content")
    assert 'https://map.naver.com/' in after
    page.emulate_media(media='screen')
    generate(page)
    reasons = ' '.join(page.locator('#plan-detail .timeline-card > p.hint').all_inner_texts())
    assert 'http://' not in reasons and 'https://' not in reasons


def test_place_evidence_uses_plain_words_and_status_badges(audit_page):
    page, base, errors = audit_page
    generate(page)
    evidence = page.locator('#plan-detail .place-evidence').first
    evidence.locator('summary').click()
    items = evidence.locator('.evidence-item')
    assert items.count() == 4
    texts = items.all_inner_texts()
    assert texts[0].startswith('확인 필요') and '같은 지점인지는 확인하지 못했' in texts[0]
    assert '가격' in texts[3] and evidence.locator('.evidence-summary-count').count() == 1
    joined = evidence.inner_text()
    for old in ('지점 일치 여부는 원문 확인 필요', '최신 운영 확인 필요', '검색 글에서 직접 등장 확인 없음', '현재가 미검증'):
        assert old not in joined
    assert evidence.locator('.evidence-badge').count() == 4


def test_mobile_section_indicator_follows_the_current_heading(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 800})
    generate(page)
    bar = page.locator('.section-indicator')
    page.evaluate("[...document.querySelectorAll('#plan-detail h3')].find(h=>h.textContent==='비용은 투명하게').scrollIntoView({block:'start',behavior:'instant'});window.scrollBy({top:90,behavior:'instant'})")
    page.wait_for_function("document.querySelector('.section-indicator-current').textContent==='비용은 투명하게'")
    assert 'is-visible' in bar.get_attribute('class')
    assert page.locator('.section-indicator-parent').inner_text() == '우리 하루, 자세히 보기'
    page.wait_for_timeout(400)  # 나타나는 전환(0.18초)이 끝난 위치로 잰다.
    geometry = page.evaluate("({bar:document.querySelector('.section-indicator').getBoundingClientRect().top,header:document.querySelector('body>header').getBoundingClientRect().bottom})")
    assert geometry['bar'] >= geometry['header'] - 1
    assert bar.get_attribute('aria-hidden') == 'true'
    page.emulate_media(reduced_motion='reduce')
    assert page.evaluate("getComputedStyle(document.querySelector('.section-indicator')).transitionDuration").split(',')[0].strip() == '0s'
    page.set_viewport_size({'width': 1440, 'height': 900})
    assert page.evaluate("getComputedStyle(document.querySelector('.section-indicator')).display") == 'none'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_request_parse_fills_classification_and_avoid_in_the_form(audit_page):
    page, base, errors = audit_page
    page.evaluate("form.elements.request.value='가을에 여자친구랑, 매운 건 빼고';form.elements.avoid.value='클라이밍';FormState.edited.clear()")
    page.evaluate('applyRequest()')
    assert page.evaluate('form.elements.date_category.value') == '계절별'
    assert page.evaluate("document.querySelector('[name=date_subcategory]:checked').value") == '가을'
    avoid = page.locator('[name=avoid]').input_value()
    assert avoid.startswith('클라이밍') and '매운' in avoid and '마라' in avoid
    assert '매운 음식 제외' in page.locator('#parse-notice').text_content()
