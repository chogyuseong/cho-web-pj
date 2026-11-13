"""조건 화면 개선: 지역 칸 바로 검색(1), 날짜·시간대·예산 칩 즉시 반응(2), 예산 무관(4), 현재 위치 정확도·실패 안내(6).

외부 API는 부르지 않는다. 주소 검색(/api/locations/search)·시·도 확인(/api/locations/region)·추천 요청은 가로채 응답한다.
시계는 브라우저 안에서만 2026-11-13(금) 서울 시각으로 고정한다."""
import json

import pytest

from app.models import Conditions
from test_quick_conditions_ui import (DAY, STORE_KEY, area_chip, details_chip, intercept_jobs, load, opened, region_reply,
                                      server, summary, wait_job)  # noqa: F401  (server 는 fixture)

GWANGAN = {'name': '부산광역시 수영구 광안해변로 219', 'road_address': '부산광역시 수영구 광안해변로 219',
           'jibun_address': '부산광역시 수영구 광안동 192-20', 'lat': 35.1532, 'lon': 129.1187}
UNKNOWN = {'name': '광안 어딘가', 'road_address': None, 'jibun_address': None, 'lat': 35.15, 'lon': 129.11}


def search_reply(page, reply, status=200):
    seen = []

    def handle(route):
        seen.append(route.request.post_data_json)
        return route.fulfill(status=status, json=reply)

    page.route('**/api/locations/search', handle)
    return seen


def origin(page):
    return page.locator('[name=origin_name]')


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth<=innerWidth')


@pytest.mark.parametrize('width', [390, 1440])
def test_search_in_area_field_with_keyboard(server, width):
    with opened(server) as (page, errors):
        page.set_viewport_size({'width': width, 'height': 900})
        bodies = intercept_jobs(page)
        seen = search_reply(page, {'status': 'ok', 'results': [GWANGAN, UNKNOWN], 'message': ''})
        field = origin(page)
        assert field.get_attribute('placeholder') == '동네·역·주소로 검색'
        assert field.get_attribute('role') == 'combobox' and field.get_attribute('aria-expanded') == 'false'
        assert page.locator('#origin-location').get_by_role('button', name='지도에서 고르기', exact=True).is_visible()
        # 입력 중에는 검색하지 않는다.
        field.click()
        field.press_sequentially('광안리', delay=40)
        page.wait_for_timeout(400)
        assert seen == []
        field.press('Enter')
        listbox = page.get_by_role('listbox', name='지역 검색 결과')
        listbox.wait_for()
        assert seen == [{'query': '광안리'}]
        assert field.get_attribute('aria-expanded') == 'true'
        options = listbox.get_by_role('option')
        assert options.count() == 2
        assert options.nth(1).get_attribute('aria-disabled') == 'true'
        assert '시·도를 알 수 없어' in options.nth(1).inner_text()
        assert '검색 결과 2곳' in page.locator('.origin-search-status').inner_text()
        for option in options.all():
            assert option.bounding_box()['height'] >= 44
        assert no_overflow(page)
        # 시·도를 알 수 없는 결과는 골라도 적용하지 않는다.
        field.press('ArrowUp')
        assert options.nth(1).get_attribute('aria-selected') == 'true'
        assert field.get_attribute('aria-activedescendant') == 'origin-search-option-1'
        field.press('Enter')
        assert '시·도를 알 수 없어 고를 수 없어요' in page.locator('.origin-search-status').inner_text()
        assert page.evaluate('locationState.origin') is None
        # 아래 화살표 → Enter 로 고르면 출발지가 된다. 폼은 제출되지 않는다.
        field.press('ArrowDown')
        assert options.nth(0).get_attribute('aria-selected') == 'true'
        field.press('Enter')
        page.wait_for_function('!!locationState.origin')
        assert listbox.is_hidden()
        assert field.input_value() == GWANGAN['road_address']
        assert page.locator('[name=region]').input_value() == '부산'
        assert page.evaluate('locationState.origin') == {'name': GWANGAN['road_address'], 'lat': GWANGAN['lat'], 'lon': GWANGAN['lon']}
        assert '데이트할 지역으로 골랐어요' in page.locator('.area-status').inner_text()
        assert bodies == []
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 1)
        assert body['origin']['name'].startswith('부산광역시') and Conditions.model_validate(body).region == '부산'


def test_search_messages_escape_and_other_sources_keep_field_in_sync(server):
    with opened(server) as (page, errors):
        field = origin(page)
        status = page.locator('.origin-search-status')
        # 결과 없음
        search_reply(page, {'status': 'ok', 'results': [], 'message': '주소를 찾지 못했습니다.'})
        field.fill('없는동네')
        page.locator('.origin-search-button').click()
        page.wait_for_function('document.querySelector(".origin-search-status").textContent.includes("주소를 찾지 못했습니다")')
        assert '지도에서 고르기' in status.inner_text()
        assert page.locator('#origin-search-results').is_hidden()
        # 오류(요청 제한)
        page.unroute('**/api/locations/search')
        search_reply(page, {'detail': '주소 검색은 잠시 후 다시 시도하세요.'}, status=429)
        field.press('Enter')
        page.wait_for_function('document.querySelector(".origin-search-status").textContent.includes("잠시 후 다시")')
        # 시·도를 알 수 없는 결과뿐
        page.unroute('**/api/locations/search')
        search_reply(page, {'status': 'ok', 'results': [UNKNOWN], 'message': ''})
        field.press('Enter')
        page.wait_for_function('document.querySelector(".origin-search-status").textContent.includes("시·도를 알 수 없는 결과뿐")')
        # 한 글자는 검색하지 않는다.
        field.fill('광')
        field.press('Enter')
        assert '두 글자 이상' in status.inner_text()
        # Esc: 결과를 닫고, 한 번 더 누르면 입력을 지금 고른 지역으로 되돌린다.
        area_chip(page, '서울 성수').click()
        page.wait_for_function('form.elements.origin_name.value==="서울 성수역 지역 중심"')
        page.unroute('**/api/locations/search')
        search_reply(page, {'status': 'ok', 'results': [GWANGAN], 'message': ''})
        field.fill('광안리')
        field.press('Enter')
        page.locator('#origin-search-results').wait_for()
        field.press('Escape')
        assert page.locator('#origin-search-results').is_hidden() and field.input_value() == '광안리'
        field.press('Escape')
        assert field.input_value() == '서울 성수역 지역 중심'
        # 결과를 띄운 채 동네 칩을 누르면 결과가 닫히고 칸은 그 동네가 된다.
        field.fill('광안리')
        field.press('Enter')
        page.locator('#origin-search-results').wait_for()
        area_chip(page, '제주 애월').click()
        page.wait_for_function('form.elements.origin_name.value==="제주 애월 한담해변 지역 중심"')
        page.wait_for_function('document.querySelector("#origin-search-results").hidden')
        # 고르지 않은 검색어는 칸을 벗어나면 지금 고른 지역으로 돌아간다.
        field.fill('아무거나')
        page.locator('.condition-toggle').focus()
        page.wait_for_function('form.elements.origin_name.value==="제주 애월 한담해변 지역 중심"')
        # 축제 주변 추천처럼 다른 코드가 출발지를 바꿔도 칸 표시가 맞는다.
        page.evaluate("applyArea('부산',{name:'부산 해운대구 · 점검 축제 행사장 주변',lat:35.1,lon:129.1});document.body.click()")
        page.wait_for_function('form.elements.origin_name.value==="부산 해운대구 · 점검 축제 행사장 주변"')


SEONGSIMDANG = {'name': '대전광역시 중구 대종로480번길 15', 'road_address': '대전광역시 중구 대종로480번길 15',
                'jibun_address': '대전광역시 중구 은행동 145', 'lat': 36.3276, 'lon': 127.4273,
                'place_name': '성심당 <b>본점</b>', 'category': '음식점>베이커리'}
PLACE_NOWHERE = {'name': '어딘가 가게', 'road_address': None, 'jibun_address': None, 'lat': 36.3, 'lon': 127.4,
                 'place_name': '어딘가 가게', 'category': '음식점'}


def test_place_name_results_show_name_and_address(server):
    with opened(server) as (page, errors):
        bodies = intercept_jobs(page)
        search_reply(page, {'status': 'ok', 'results': [SEONGSIMDANG, PLACE_NOWHERE], 'message': '', 'provider': 'NAVER 지역 검색'})
        field = origin(page)
        field.fill('대전 성심당')
        field.press('Enter')
        listbox = page.get_by_role('listbox', name='지역 검색 결과')
        listbox.wait_for()
        options = listbox.get_by_role('option')
        assert options.count() == 2
        first = options.nth(0)
        # 이름과 주소를 함께 보이고, 이름은 HTML 이 아니라 글자로 넣는다.
        assert first.locator('strong').inner_text() == '성심당 <b>본점</b>' and first.locator('b').count() == 0
        assert SEONGSIMDANG['road_address'] in first.inner_text()
        assert first.get_attribute('aria-disabled') is None
        # 주소가 없어 시·도를 알 수 없는 장소는 고를 수 없다.
        assert options.nth(1).get_attribute('aria-disabled') == 'true'
        assert '시·도를 알 수 없어' in options.nth(1).inner_text()
        first.click()
        page.wait_for_function('!!locationState.origin')
        assert field.input_value() == SEONGSIMDANG['road_address']
        assert page.locator('[name=region]').input_value() == '대전'
        assert page.evaluate('locationState.origin') == {'name': SEONGSIMDANG['road_address'], 'lat': SEONGSIMDANG['lat'], 'lon': SEONGSIMDANG['lon']}
        assert '성심당 <b>본점</b>(' in page.locator('.area-status').inner_text()
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 1)
        assert Conditions.model_validate(body).region == '대전'
        assert no_overflow(page)


def test_date_chip_pressed_immediately_even_when_same_day_as_tomorrow(server):
    # 2026-11-13 은 금요일: ‘내일’과 ‘이번 토요일’이 같은 날이다.
    with opened(server) as (page, errors):
        page.locator('.condition-toggle').click()
        today, tomorrow, saturday = (details_chip(page, '방문 날짜', name) for name in ('오늘', '내일', '이번 토요일'))
        note = page.locator('.date-note')
        saturday.click()
        assert saturday.get_attribute('aria-pressed') == 'true'
        assert tomorrow.get_attribute('aria-pressed') == 'false' and today.get_attribute('aria-pressed') == 'false'
        assert note.inner_text() == '내일 11월 14일 (토)로 정했어요.' and note.get_attribute('role') == 'status'
        assert '내일 11월 14일 (토)' in summary(page)
        tomorrow.click()
        assert tomorrow.get_attribute('aria-pressed') == 'true' and saturday.get_attribute('aria-pressed') == 'false'
        today.click()
        assert today.get_attribute('aria-pressed') == 'true'
        assert note.inner_text() == '오늘 11월 13일 (금)로 정했어요.'
        assert 'is-adjusted' not in note.get_attribute('class')
        # 시간대·예산 칩도 누르는 즉시 정한 값을 알린다.
        details_chip(page, '시간대', '저녁 17–22').click()
        assert page.locator('.time-note').inner_text() == '시간대를 17:00–22:00에 맞췄어요.'
        details_chip(page, '전체 예산', '5만').click()
        assert page.locator('.budget-note').inner_text() == '전체 예산을 5만 원에 맞췄어요.'
        details_chip(page, '방문 날짜', '직접').click()
        page.locator('[name=visit_date]').fill('2026-11-20')
        page.wait_for_function('document.querySelector(".date-note").textContent==="11월 20일 (금)로 정했어요."')


def test_today_chip_explains_moved_time_or_day(server):
    with opened(server, clock='12:30') as (page, errors):
        page.locator('.condition-toggle').click()
        note = page.locator('.date-note')
        details_chip(page, '방문 날짜', '내일').click()
        details_chip(page, '시간대', '하루 종일 11–19').click()
        details_chip(page, '방문 날짜', '오늘').click()
        assert note.inner_text() == '오늘 11월 13일 (금)로 정했어요. 오늘은 11:00 시작이 이미 지나 시간대를 13:00–19:00에 맞췄어요.'
        assert 'is-adjusted' in note.get_attribute('class')
        assert details_chip(page, '방문 날짜', '오늘').get_attribute('aria-pressed') == 'true'
        assert details_chip(page, '시간대', '오후 13–19').get_attribute('aria-pressed') == 'true'
    with opened(server, clock='18:10') as (page, errors):
        page.locator('.condition-toggle').click()
        today = details_chip(page, '방문 날짜', '오늘')
        today.click()
        note = page.locator('.date-note')
        assert note.inner_text() == '오늘은 고를 수 있는 시간대가 모두 지나 내일 11월 14일 (토)로 맞췄어요.'
        assert 'is-adjusted' in note.get_attribute('class')
        # 칩 상태는 실제 값(내일)과 맞춘다.
        assert today.get_attribute('aria-pressed') == 'false'
        assert details_chip(page, '방문 날짜', '내일').get_attribute('aria-pressed') == 'true'
        assert page.locator('[name=visit_date]').input_value() == '2026-11-14'
        assert note.evaluate('el=>getComputedStyle(el).backgroundColor') == 'rgb(255, 243, 196)'


def test_budget_unlimited_chip_request_summary_and_last_conditions(server):
    with opened(server) as (page, errors):
        bodies = intercept_jobs(page)
        area_chip(page, '제주 애월').click()
        page.locator('.condition-toggle').click()
        free = details_chip(page, '전체 예산', '예산 무관')
        free.click()
        assert free.get_attribute('aria-pressed') == 'true'
        assert details_chip(page, '전체 예산', '10만').get_attribute('aria-pressed') == 'false'
        assert '예산 무관' in summary(page) and '10만 원' not in summary(page)
        assert page.locator('.budget-note').inner_text() == '예산 무관으로 정했어요. 예산 상한 없이 코스를 찾아요.'
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 1)
        assert body['budget_unlimited'] is True and body['budget'] == 100000
        assert Conditions.model_validate(body).budget_unlimited is True
        # 진행 안내의 ‘적용 조건’ 줄도 금액 대신 예산 무관.
        assert '· 예산 무관 ·' in page.evaluate('FormState.summary(values())')
        saved = json.loads(page.evaluate(f'localStorage.getItem("{STORE_KEY}")'))
        assert saved['budget_unlimited'] is True
        # 다시 오면 ‘지난번처럼 추천’에도 예산 무관이 남는다.
        page.evaluate('sessionStorage.clear()')
        load(page, server)
        again = page.locator('.last-conditions .again-button')
        assert '예산 무관' in again.inner_text()
        again.click()
        body = wait_job(page, bodies, 2)
        assert body['budget_unlimited'] is True
        # 금액 칩을 고르면 다시 false.
        page.locator('#edit-conditions').click()
        page.wait_for_function('!document.querySelector(".conditions").hidden')
        page.locator('.condition-toggle').click()
        assert details_chip(page, '전체 예산', '예산 무관').get_attribute('aria-pressed') == 'true'
        details_chip(page, '전체 예산', '5만').click()
        assert '5만 원' in summary(page)
        page.locator('#submit-plan').click()
        body = wait_job(page, bodies, 3)
        assert body['budget_unlimited'] is False and body['budget'] == 50000
        saved = json.loads(page.evaluate(f'localStorage.getItem("{STORE_KEY}")'))
        assert 'budget_unlimited' not in saved
        # ‘직접’도 예산 무관을 끈다.
        page.locator('#edit-conditions').click()
        page.wait_for_function('!document.querySelector(".conditions").hidden')
        details_chip(page, '전체 예산', '예산 무관').click()
        details_chip(page, '전체 예산', '직접').click()
        assert page.evaluate('form.elements.budget_unlimited.checked') is False


def fake_geolocation(page, outcomes):
    """getCurrentPosition 을 바꿔 순서대로 결과를 돌려준다. outcomes: [{'error':code}|{'lat','lon','accuracy'}]."""
    page.evaluate("""outcomes=>{
      window.__geoCalls=[];const queue=[...outcomes];
      navigator.geolocation.getCurrentPosition=(ok,fail,options)=>{
        window.__geoCalls.push(options);const next=queue.shift();
        setTimeout(()=>next.error?fail({code:next.error}):ok({coords:{latitude:next.lat,longitude:next.lon,accuracy:next.accuracy}}),10);
      };
    }""", outcomes)


def test_current_location_precise_applies_with_high_accuracy_request(server):
    with opened(server, permissions=['geolocation'], geolocation={'latitude': 37.5446, 'longitude': 127.0559, 'accuracy': 30}) as (page, errors):
        region_reply(page, {'status': 'ok', 'region': '서울', 'label': '서울특별시 성동구 성수동1가', 'message': ''})
        page.evaluate("""()=>{const original=navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);window.__geoCalls=[];
          navigator.geolocation.getCurrentPosition=(ok,fail,options)=>{window.__geoCalls.push(options);original(ok,fail,options);};}""")
        page.get_by_role('button', name='현재 위치', exact=True).click()
        page.wait_for_function('form.elements.origin_name.value.endsWith("· 현재 위치")')
        calls = page.evaluate('__geoCalls')
        assert calls[0]['enableHighAccuracy'] is True and calls[0]['maximumAge'] == 0
        text = page.locator('.area-status').inner_text()
        assert '현재 위치(서울특별시 성동구 성수동1가)' in text and '대략' not in text
        assert page.locator('.location-choice').is_hidden()


def test_current_location_rough_asks_before_applying(server):
    with opened(server, permissions=['geolocation'], geolocation={'latitude': 37.5446, 'longitude': 127.0559, 'accuracy': 3000}) as (page, errors):
        region_reply(page, {'status': 'ok', 'region': '서울', 'label': '서울특별시 성동구 성수동1가', 'message': ''})
        here = page.get_by_role('button', name='현재 위치', exact=True)
        here.click()
        choose = page.get_by_role('button', name='이 위치로 정하기', exact=True)
        choose.wait_for()
        status = page.locator('.area-status').inner_text()
        assert '대략적인 위치예요(오차 약 3km). 서울특별시 성동구 성수동1가 근처로 나왔어요.' in status
        assert page.evaluate('locationState.origin') is None
        assert page.get_by_role('button', name='동네 직접 검색하기', exact=True).is_visible()
        assert no_overflow(page)
        choose.click()
        page.wait_for_function('form.elements.origin_name.value==="서울특별시 성동구 성수동1가 · 현재 위치"')
        assert '대략적인 위치(오차 약 3km)' in page.locator('.area-status').inner_text()
        assert page.locator('.location-choice').is_hidden()
        # 오차가 수십 km 면 적용 버튼 없이 검색으로만 안내한다.
        page.context.set_geolocation({'latitude': 37.5, 'longitude': 127.0, 'accuracy': 45000})
        here.click()
        search = page.get_by_role('button', name='동네 직접 검색하기', exact=True)
        search.wait_for()
        assert page.get_by_role('button', name='이 위치로 정하기', exact=True).count() == 0
        assert '오차가 너무 커서' in page.locator('.area-status').inner_text()
        # 그 사이 출발지는 바뀌지 않는다.
        assert origin(page).input_value() == '서울특별시 성동구 성수동1가 · 현재 위치'
        search.click()
        assert page.evaluate('document.activeElement===form.elements.origin_name')


def test_current_location_errors_and_timeout_retry(server):
    with opened(server) as (page, errors):
        region_reply(page, {'status': 'ok', 'region': '부산', 'label': '부산광역시 수영구 광안동', 'message': ''})
        here = page.get_by_role('button', name='현재 위치', exact=True)
        status = page.locator('.area-status')
        # 위치를 알 수 없음(code 2): 위치 서비스를 켜라고 안내, 다시 시도하지 않음.
        fake_geolocation(page, [{'error': 2}])
        here.click()
        page.wait_for_function('document.querySelector(".area-status").textContent.includes("위치 서비스를 켜고")')
        assert page.evaluate('__geoCalls.length') == 1
        assert page.evaluate('document.activeElement===form.elements.origin_name')
        # 시간 초과(code 3) 뒤에는 낮은 정확도로 한 번 더 시도해 성공한다.
        fake_geolocation(page, [{'error': 3}, {'lat': 35.153, 'lon': 129.118, 'accuracy': 200}])
        here.click()
        page.wait_for_function('form.elements.origin_name.value==="부산광역시 수영구 광안동 · 현재 위치"')
        calls = page.evaluate('__geoCalls')
        assert len(calls) == 2 and calls[0]['enableHighAccuracy'] is True and calls[1]['enableHighAccuracy'] is False
        # 두 번 다 시간 초과면 시간 초과 안내.
        fake_geolocation(page, [{'error': 3}, {'error': 3}])
        here.click()
        page.wait_for_function('document.querySelector(".area-status").textContent.includes("시간이 너무 오래 걸렸어요")')
        assert not page.locator('#dialog').evaluate('dialog=>dialog.open')
        assert '현재 위치를 확인하고' not in status.inner_text()
