"""일정의 장소 카드 아래 '후기에서 읽은 영업시간': 실제 브라우저, 로컬 서버. 응답은 가짜."""
from test_functional_audit import audit_page, generate  # noqa: F401

# 데모 코스를 실제 장소 코스처럼 보이게 하고, 영업시간을 비운다(후기 영업시간은 확인된 시간이 없을 때만 보임).
REAL = ("selected.conditions.mode='real';plans.forEach(p=>{p.conditions.mode='real';"
        "p.places.forEach(x=>{x.demo=false;x.hours=null;x.category='카페·미식'})});renderResults();renderDetail()")


def test_review_hours_line_under_the_stop(audit_page):
    page, base, errors = audit_page
    generate(page)
    first = page.evaluate('selected.places[0].id')
    requests = []

    def handle(route):
        requests.append(route.request.url)
        if first.replace(':', '%3A') in route.request.url or first in route.request.url:
            return route.fulfill(json=dict(status='available', hours='매일 11:00~21:00', closed='정기휴무 : 매주 월요일',
                                           note='블로그 후기에 적힌 정보예요. 지금과 다를 수 있어요.', evidence='…',
                                           prices=[dict(item='감자만두', amount=10000, url='https://blog.naver.com/a/1', posted_at='2026-10-08'),
                                                   dict(item='맑은한돈곰탕', amount=12000, url='https://blog.naver.com/a/1', posted_at='2026-10-08')],
                                           source=dict(url='https://blog.naver.com/a/1', title='후기', posted_at='2026-10-08')))
        return route.fulfill(json=dict(status='not_found', hours=None, closed=None, source=None, evidence=None, note='', prices=[]))

    page.route('**/api/places/*/review-facts*', handle)
    page.evaluate(REAL)
    stops = page.locator('#plan-detail .detail > .stop')
    stops.first.scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#plan-detail .review-facts:not([hidden])')")
    box = stops.first.locator('.review-facts')
    text = box.inner_text()
    assert '후기에서 읽은 영업시간' in text and '매일 11:00~21:00 · 정기휴무 : 매주 월요일' in text
    assert '후기에 나온 가격 예 감자만두 10,000원 · 맑은한돈곰탕 12,000원' in text
    assert '블로그 글(2026-10-08) 기준 · 지금과 다를 수 있어요. 예상 비용에는 넣지 않았어요.' in text
    anchor = box.locator('a')
    assert anchor.inner_text() == '근거 글 보기 ↗' and anchor.get_attribute('href') == 'https://blog.naver.com/a/1'
    # 읽은 것이 없는 장소에는 아무것도 남지 않는다.
    for i in range(1, stops.count()):
        stops.nth(i).scroll_into_view_if_needed()
    page.wait_for_function('(n)=>document.querySelectorAll("#plan-detail .review-facts").length===1', arg=1)
    assert len({u.split('/review-facts')[0] for u in requests}) == stops.count()
    for width in (390, 320):
        page.set_viewport_size({'width': width, 'height': 900})
        box.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
        assert anchor.evaluate('a=>a.getBoundingClientRect().height') >= 43.5
        small = box.evaluate(
            "b=>[...b.querySelectorAll('*')].filter(el=>[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))"
            ".filter(el=>parseFloat(getComputedStyle(el).fontSize)<14).map(el=>el.textContent)")
        assert not small, (width, small)


def test_demo_course_does_not_ask(audit_page):
    page, base, errors = audit_page
    requests = []
    page.route('**/api/places/*/review-facts*', lambda route: (requests.append(1), route.fulfill(json={}))[1])
    generate(page)
    page.locator('#plan-detail .detail > .stop').first.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    assert requests == [] and page.locator('.review-facts').count() == 0
