"""관광공사 안내를 화면에 보여 주는 두 줄 (2026-11-24, 서버는 feat/public-data-1124).

1. 영업 정보 줄: 쉬는 날 글에서 읽은 휴무 요일(tour_hours.closed_days)이 있으면 '일정 계산에 반영(관광공사 안내 기준)'을 덧붙인다.
2. 식당 메뉴 칸: 관광공사 대표·취급 메뉴(tour_menu)가 있으면 '관광공사 안내 · 대표 메뉴 …' 한 줄과 출처, 그 아래 지도 링크.
서버가 이 값을 보내지 않으면(예전 응답) 예전과 똑같이 보인다."""
from test_functional_audit import audit_page  # noqa: F401  (fixture)




def test_tour_rest_day_note_in_the_operating_line(audit_page):  # noqa: F811
    page, _, _ = audit_page
    got = page.evaluate("""()=>{
      const make=()=>{const li=evidenceItem('영업 정보','check','최근 영업 정보를 확인하지 못했어요.');li.dataset.operatingPlaceId='p1';document.body.append(li);return li;};
      const out=[];
      for(const days of [[0],[0,1],[],null]){
        const li=make();markTourHours('p1',{rest:'매주 월요일',closed_days:days});out.push(li.querySelector('.tour-hours').textContent);li.remove();
      }
      return out;
    }""")
    assert '매주 월요일 휴무는 일정 계산에 반영했어요(관광공사 안내 기준)' in got[0]
    assert '매주 월·화요일 휴무는' in got[1]
    assert '연중무휴로 보고 일정을 계산했어요(관광공사 안내 기준)' in got[2]
    assert '일정 계산' not in got[3], '읽지 못한 글(예전 응답)은 예전 문구 그대로'


def test_tour_menu_line_in_the_menu_panel(audit_page):  # noqa: F811
    page, _, _ = audit_page
    base = {'status': 'not_found', 'items': [], 'menu_images': [], 'reason': 'not_collected', 'source_kind': 'map_link',
            'source_url': 'https://map.naver.com/p/search/x', 'source_label': '네이버 지도에서 메뉴 보기',
            'message': '이 식당의 메뉴·가격 자료는 모아 두지 않았어요. 네이버 지도에서 확인해 주세요.'}
    with_menu = dict(base, tour_menu={'first': '돼지국밥', 'treat': '돼지국밥, 수육', 'source_url': 'https://korean.visitkorea.or.kr/x'})
    page.route('**/api/places/m1/menu?*', lambda route: route.fulfill(json=with_menu))
    page.route('**/api/places/m2/menu?*', lambda route: route.fulfill(json=base))
    texts = page.evaluate("""async ()=>{
      const out=[];
      for(const id of ['m1','m2']){
        restaurantMenuRequests.delete(id);
        const box=restaurantMenuPanel({id,name:'국밥집'});document.body.append(box);box.scrollIntoView();
        const t=Date.now();while(!box.querySelector('a')&&Date.now()-t<5000)await new Promise(r=>setTimeout(r,50));
        out.push([box.textContent,[...box.querySelectorAll('a')].map(a=>a.textContent)]);box.remove();
      }
      return out;
    }""")
    menu_text, menu_links = texts[0]
    # 2026-11-26: 한 줄 글 → 메뉴 칩(대표 표시, 같은 이름 한 번), 제목은 가격이 없으니 '대표 메뉴', 가격은 지도에 있다는 안내.
    assert menu_text.startswith('대표 메뉴') and '대표 메뉴·가격' not in menu_text
    assert '가격은 네이버 지도 메뉴 탭에서 볼 수 있어요' in menu_text
    assert '모아 두지 않았어요' not in menu_text
    assert menu_links == ['출처 ↗', '네이버 지도에서 메뉴보기 ↗']
    plain_text, plain_links = texts[1]
    assert plain_text.startswith('대표 메뉴·가격')
    assert '모아 두지 않았어요' in plain_text and plain_links == ['네이버 지도에서 메뉴보기 ↗']


def test_tour_menu_chips_split_names(audit_page):  # noqa: F811
    """관광공사 메뉴 글을 칩으로 나눈다(meal-suggestions.js tourMenuNames): / , · 로 나누고 끝의 '등'을 떼고, 대표 메뉴에 '대표' 표시, 같은 이름은 한 번."""
    page, _, _ = audit_page
    got = page.evaluate("""()=>tourMenuNames({first:'에비가츠동',treat:'에비에비가츠동 / 대창 소고기 카레 누들 / 모듬 카레 누들 등, 에비가츠동'})""")
    assert got == [{'name': '에비가츠동', 'main': True}, {'name': '에비에비가츠동', 'main': False},
                   {'name': '대창 소고기 카레 누들', 'main': False}, {'name': '모듬 카레 누들', 'main': False}]
    assert page.evaluate("tourMenuNames(null).length") == 0
    page.route('**/api/places/m3/menu?*', lambda route: route.fulfill(json={
        'status': 'not_found', 'items': [], 'menu_images': [], 'reason': 'not_collected', 'source_url': 'https://map.naver.com/p/search/x',
        'tour_menu': {'first': '에비가츠동', 'treat': '에비에비가츠동 / 대창 소고기 카레 누들'}}))
    chips = page.evaluate("""async ()=>{
      restaurantMenuRequests.delete('m3');const box=restaurantMenuPanel({id:'m3',name:'탐광'});document.body.append(box);box.scrollIntoView();
      const t=Date.now();while(!box.querySelector('.tour-menu-chip')&&Date.now()-t<5000)await new Promise(r=>setTimeout(r,50));
      const out=[...box.querySelectorAll('.tour-menu-chip')].map(li=>li.textContent);
      const link=box.querySelector('a.menu-map-link');out.push(link&&getComputedStyle(link).minHeight);box.remove();return out;
    }""")
    assert chips == ['대표에비가츠동', '에비에비가츠동', '대창 소고기 카레 누들', '44px']
