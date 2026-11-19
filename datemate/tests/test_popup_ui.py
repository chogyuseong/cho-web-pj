"""팝업 둘러보기 화면(1단계 1a): 실제 브라우저, /api/popups 는 page.route 가짜 응답(외부 호출 없음)."""

import json
from urllib.parse import parse_qs, urlsplit

from test_functional_audit import audit_page  # noqa: F401

from app import main

LONG_TITLE = (
    "성수 연무장길 대형 캐릭터 팝업스토어 SUPERLONGBRANDNAMEWITHOUTANYSPACESATALLFORTESTING "
    "웨이팅·예약·굿즈 가격·포토존까지 한 번에 정리한 아주 긴 제목의 후기 글입니다"
)


def post(i, **extra):
    base = dict(
        id=f"popup-post:{i:016x}",
        title=f"팝업 글 {i}",
        description=f"요약 {i} 팝업 운영 정보",
        url=f"https://blog.naver.com/test/{i}",
        blogger=f"블로거{i}",
        posted_at="2026-11-14",
        roundup=False,
        period=dict(
            level="none", start=None, end=None, evidence=[], status="unknown", end_only=False
        ),
        place=dict(hub_id=None, level="unverified", reason="not_found"),
    )
    return base | extra


CONFIRMED = dict(
    level="confirmed",
    start="2026-10-20",
    end="2026-11-16",
    evidence=["2026.10.20~2026.11.16"],
    status="ongoing",
    end_only=False,
)
BUILDING = dict(
    hub_id="seoul-thehyundai",
    name="더현대 서울",
    kind="building",
    anchor=None,
    region="서울",
    level="building",
    reason="verified",
    lat=37.526,
    lon=126.928,
)
AREA = dict(
    hub_id="seoul-area-seongsu",
    name="성수 일대",
    kind="area",
    anchor="성수역",
    region="서울",
    level="area_anchor",
    reason="verified",
    lat=37.5446,
    lon=127.056,
)


def payload(status="ready", posts=None, region="서울", **extra):
    posts = posts if posts is not None else []
    data = dict(
        status=status,
        message=None,
        region=region,
        q="",
        visit_date="2026-11-14",
        basis="today",
        sources=[dict(id="blog", name="네이버 블로그 검색", status="ok", returned=50, display=50)],
        attribution="네이버 블로그 검색 결과",
        posts=posts,
        counts=dict(
            shown=len(posts),
            general=sum(not p["roundup"] for p in posts),
            roundup=sum(p["roundup"] for p in posts),
            location_unknown=sum(p["place"]["level"] == "unverified" for p in posts),
            hidden_ended=1,
            excluded_other_region=2,
            not_popup=0,
        ),
    )
    return data | extra


READY = payload(
    posts=[
        post(1, title="더현대 서울 올기 팝업", period=CONFIRMED, place=BUILDING),
        post(
            2,
            title=LONG_TITLE,
            period=dict(
                level="month_day",
                start=None,
                end=None,
                evidence=["11.14~11.30"],
                status="unknown",
                end_only=False,
            ),
            place=AREA,
        ),
        post(3, title="<img src=x onerror=window.__xss=1> 팝업", blogger=None),
        post(4, title="11월 성수 팝업 총정리 10곳", roundup=True, place=AREA),
    ]
)


class Api:
    """요청마다 검색어(q)로 응답을 고른다. hold 에 든 검색어는 응답하지 않고 route 를 남겨 둔다."""

    def __init__(self, page):
        self.requests = []
        self.held = {}
        self.hold = set()
        self.by_query = {"": (200, READY)}
        page.route(lambda url: urlsplit(url).path == "/api/popups", self.handle)

    def handle(self, route):
        query = parse_qs(urlsplit(route.request.url).query)
        q = query.get("q", [""])[0]
        self.requests.append(dict(region=query["region"][0], q=q))
        if q in self.hold:
            self.held[q] = route
            return
        status, body = self.by_query.get(q, (200, READY))
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def open_popups(page):
    page.locator("#nav-explore").click()
    page.wait_for_selector("#explore-switch-popups")
    page.locator("#explore-switch-popups").click()


def search(page, q):
    page.locator("#popup-query").fill(q)
    page.locator("#popup-search").click()


def no_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth<=innerWidth")


def test_popup_browse_states_and_reading_kept_apart_from_the_quote(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    api.by_query.update(
        {
            "부분": (
                200,
                payload(
                    "partial",
                    READY["posts"][:1],
                    message="일부 장소의 위치를 확인하지 못해 위치 미확인으로 표시했어요.",
                ),
            ),
            "없음": (
                200,
                payload("empty", [], message="검색된 글 중에 보여 드릴 팝업 글이 없어요."),
            ),
            "실패": (
                200,
                payload(
                    "unavailable",
                    [],
                    message="네이버 블로그 검색에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
                ),
            ),
            "키": (
                200,
                payload(
                    "key_missing",
                    [],
                    message="네이버 검색 키가 설정되지 않아 팝업 글을 찾을 수 없어요.",
                ),
            ),
            "한도": (429, {"detail": "새 팝업 검색이 많아요. 잠시 후 다시 시도해 주세요."}),
        }
    )
    page.evaluate(
        "ExploreView.regionTouched=true;document.getElementById('explore-region').value='부산'"
    )
    open_popups(page)
    page.wait_for_selector(".popup-post")
    # 처음 열면 장소 둘러보기의 시·도로 한 번 찾는다. 헤더 메뉴는 그대로 4개.
    assert api.requests[0] == dict(region="부산", q="")
    assert page.locator("#explore-places").is_hidden()
    assert page.locator("#explore-switch-popups").get_attribute("aria-pressed") == "true"
    assert page.locator("#explore-section h2").inner_text() == "팝업스토어 둘러보기"
    assert page.locator("body>header nav>*").count() == 4
    status = page.locator("#popup-status").inner_text()
    assert "오늘(2026.11.14) 기준" in status and "네이버 블로그 검색 결과" in status
    # 일반 글과 모아 보기 글이 나뉘고, 종료·다른 지역으로 뺀 수를 알린다.
    # 안내 줄의 전체 수(4건)와 목록 제목의 수가 같은 기준(보여 주는 글)으로 맞는다: 4 = 일반 3 + 모아 보기 1.
    # 운영에서 안내 줄 43건 · 목록 제목 "검색된 팝업 글 42건"으로 보이던 1건 차이(모아 보기 글 1건)의 회귀 검사.
    assert status.endswith("팝업 글 4건 (일반 글 3건 · 여러 팝업을 모아 소개한 글 1건)")
    lists = page.locator(".popup-list h3").all_inner_texts()
    assert lists == ["일반 팝업 글 3건", "여러 팝업을 모아 소개한 글 1건"]
    notes = page.locator(".popup-note").all_inner_texts()
    assert any("종료로 확인된 글 1건" in n for n in notes) and any("다른 시·도" in n for n in notes)
    assert "출처: 네이버 블로그 검색 결과" in page.locator(".popup-attribution").inner_text()
    first = page.locator(".popup-post").nth(0)
    # 원문 인용(제목·요약·링크)과 읽은 정보가 다른 칸이다.
    assert first.locator(".popup-quote .popup-title").inner_text() == "더현대 서울 올기 팝업"
    assert first.locator(".popup-quote a").get_attribute("href") == "https://blog.naver.com/test/1"
    assert first.locator(".popup-quote a").get_attribute("rel") == "noopener noreferrer"
    reading = first.locator(".popup-reading")
    assert (
        reading.locator(".popup-reading-title").inner_text()
        == "데이트메이트가 검색 요약에서 읽은 정보"
    )
    assert "2026.10.20 ~ 2026.11.16 · 오늘 기준 진행 중 · 원문 확인" in reading.inner_text()
    assert "더현대 서울 · 건물 위치 확인" in reading.inner_text()
    assert reading.locator(".is-unconfirmed").count() == 0
    second = page.locator(".popup-post").nth(1)
    period = second.locator(".popup-period")
    assert "is-unconfirmed" in period.get_attribute("class")
    assert (
        period.inner_text()
        .replace("\n", " ")
        .endswith("기간 미확인 · 검색 요약에 적힌 날짜: 11.14~11.30")
    )
    # 미확인은 점선 + 글자.
    assert period.evaluate("e=>getComputedStyle(e,'::before').borderTopStyle") == "dashed"
    assert "성수 일대(대략) · 동네 기준점 성수역" in second.inner_text()
    third = page.locator(".popup-post").nth(2)
    assert "위치 미확인 · 요약에서 장소를 찾지 못했어요" in third.inner_text()
    # 검색 결과 글은 텍스트로만 넣는다.
    assert third.locator(".popup-title").inner_text().startswith("<img")
    assert (
        page.locator("#popup-results img").count() == 0
        and page.evaluate("typeof window.__xss") == "undefined"
    )
    # 부분 실패, 결과 없음, 전체 실패(다시 찾기), 키 없음, 한도 초과(HTTP 429)를 다르게 보인다.
    search(page, "부분")
    page.wait_for_selector(".popup-state-partial")
    assert page.locator(".popup-post").count() == 1
    # 모아 보기 글이 없으면 안내 줄의 수와 목록 제목의 수가 그대로 같다.
    assert page.locator("#popup-status").inner_text().endswith("팝업 글 1건")
    assert page.locator(".popup-list h3").all_inner_texts() == ["검색된 팝업 글 1건"]
    search(page, "없음")
    page.wait_for_selector(".popup-state-empty")
    assert "보여 드릴 팝업 글이 없어요" in page.locator("#popup-status").inner_text()
    search(page, "실패")
    page.wait_for_selector(".popup-state-error")
    asked = len(api.requests)
    page.locator(".popup-state-error button").click()
    page.wait_for_function(
        "document.querySelector('#popup-results').getAttribute('aria-busy')==='false'"
    )
    assert len(api.requests) == asked + 1 and api.requests[-1]["q"] == "실패"
    search(page, "키")
    page.wait_for_selector(".popup-state-key")
    assert page.locator(".popup-state-key button").count() == 0
    search(page, "한도")
    page.wait_for_selector(".popup-state-error:has-text('새 팝업 검색이 많아요')")
    # 장소로 돌아가면 장소 목록이 다시 보인다.
    page.locator("#explore-switch-places").click()
    assert (
        page.locator("#explore-places").is_visible() and page.locator("#popup-browse").is_hidden()
    )
    assert page.locator("#explore-section h2").inner_text() == "데이트 장소 둘러보기"


def test_late_success_error_and_loading_end_are_ignored(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    api.hold = {"느림", "느린실패"}
    api.by_query["빠름"] = (200, payload(posts=[post(9, title="빠른 응답 글")]))
    open_popups(page)
    page.wait_for_selector(".popup-post")
    # 취소(AbortController)만 믿지 않는지 보려고 취소를 끈다. 늦은 응답은 generation 으로만 버려져야 한다.
    page.evaluate("AbortController.prototype.abort=function(){}")
    search(page, "느림")
    page.wait_for_function(
        "document.querySelector('#popup-results').getAttribute('aria-busy')==='true'"
    )
    search(page, "빠름")
    page.wait_for_selector(".popup-post:has-text('빠른 응답 글')")
    # 앞선 요청이 늦게 성공해도 화면을 바꾸지 않는다(로딩 끝 처리도 하지 않는다).
    search(page, "느린실패")
    page.wait_for_function(
        "document.querySelector('#popup-results').getAttribute('aria-busy')==='true'"
    )
    api.held.pop("느림").fulfill(
        status=200, content_type="application/json", body=json.dumps(READY)
    )
    page.wait_for_timeout(300)
    assert page.locator("#popup-results").get_attribute("aria-busy") == "true"
    assert page.locator(".popup-post").count() == 0
    search(page, "빠름")
    page.wait_for_selector(".popup-post:has-text('빠른 응답 글')")
    api.held.pop("느린실패").fulfill(
        status=500, content_type="application/json", body='{"detail":"늦은 오류"}'
    )
    page.wait_for_timeout(300)
    assert page.locator(".popup-state-error").count() == 0
    assert page.locator(".popup-post").all_inner_texts()[0].count("빠른 응답 글") == 1
    assert page.locator("#popup-search").is_enabled()


def test_four_widths_long_titles_touch_targets_and_keyboard(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    many = [post(i, title=LONG_TITLE + f" {i}", period=CONFIRMED, place=AREA) for i in range(12)]
    api.by_query[""] = (200, payload(posts=many + [post(99, roundup=True)]))
    open_popups(page)
    page.wait_for_selector(".popup-post")
    assert page.locator(".popup-more").inner_text() == "글 더 보기 (2건)"
    page.locator(".popup-more").click()
    assert page.locator(".popup-list").first.locator(".popup-post").count() == 12
    for width in (320, 390, 768, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert no_overflow(page), width
        check = page.evaluate(
            """() => {
              const area=document.querySelector('#explore-section');
              const small=[...area.querySelectorAll('#popup-browse p,#popup-browse dt,#popup-browse dd,#popup-browse h4,#popup-browse a,#popup-browse label,#explore-switch button')]
                .filter(e=>e.getClientRects().length && e.textContent.trim() && parseFloat(getComputedStyle(e).fontSize)<14)
                .map(e=>e.className+':'+getComputedStyle(e).fontSize);
              const short=[...area.querySelectorAll('#popup-browse button,#explore-switch button,#popup-browse .popup-source-link,#popup-browse select,#popup-browse input')]
                .filter(e=>e.getClientRects().length && e.getBoundingClientRect().height<44).map(e=>e.textContent.trim()||e.id);
              const clipped=[...area.querySelectorAll('.popup-title,.popup-fact dd,.popup-meta')]
                .filter(e=>e.scrollWidth>e.clientWidth+1 || getComputedStyle(e).textOverflow==='ellipsis' || getComputedStyle(e).webkitLineClamp!=='none')
                .map(e=>e.textContent.slice(0,20));
              const outside=[...area.querySelectorAll('.popup-post')].filter(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth;}).length;
              return {small, short, clipped, outside};
            }"""
        )
        assert check == dict(small=[], short=[], clipped=[], outside=0), (width, check)
    title = page.locator(".popup-title").first
    assert title.inner_text().endswith("긴 제목의 후기 글입니다 0")  # 말줄임 없이 끝까지
    # 키보드로 전환·검색·출처 링크에 닿고 포커스 표시가 보인다.
    page.locator("#explore-switch-places").focus()
    page.keyboard.press("Enter")
    assert page.locator("#explore-places").is_visible()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "explore-switch-popups"
    page.keyboard.press("Enter")
    page.wait_for_selector("#popup-browse:not([hidden])")
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
    page.locator(".popup-source-link").first.focus()
    assert page.evaluate("document.activeElement.classList.contains('popup-source-link')")
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"


def photo(name, original=None):
    """대표 사진(app/popup_api.post_photos 의 post.photo). 사진 서버는 page.route 로 흉내 낸다(외부 호출 없음)."""
    return dict(
        image_url=f"https://photos.example.test/{name}-thumb.png",
        original_url=original or f"https://photos.example.test/{name}-original.png",
        source=original or f"https://photos.example.test/{name}-original.png",
        title="<img src=x onerror=window.__xss_photo=1> 검색 결과 제목",
        provider="네이버 이미지 검색",
        search_url="https://search.naver.com/search.naver?where=image&query=x",
    )


def test_popup_photo_sits_beside_the_intro_and_disappears_when_broken(audit_page):
    """2026-11-19 사용자 요청: 팝업 소개 옆 작은 사진 + 출처. 맞는 사진이 없거나 깨지면 사진 칸 없이(깨진 그림·빈칸 없음)."""
    from test_results_extras_ui import wide_png

    page, base, errors = audit_page
    png = wide_png(300, 300)
    ok = {"good-thumb.png", "backup-original.png", "long-thumb.png"}
    page.route(
        "https://photos.example.test/**",
        lambda route: route.fulfill(body=png, content_type="image/png")
        if route.request.url.rsplit("/", 1)[-1] in ok
        else route.fulfill(status=404, body=b""),
    )
    posts = [
        post(1, title="더현대 서울 올기 팝업", period=CONFIRMED, place=BUILDING, photo=photo("good")),
        post(2, title="성수 짱구 팝업", place=AREA, photo=photo("backup")),
        post(3, title="성수 깨진 팝업", place=AREA, photo=photo("broken")),
        post(4, title="성수 위험 팝업", place=AREA, photo=dict(photo("x"), image_url="javascript:alert(1)")),
        post(5, title=LONG_TITLE, place=AREA, photo=photo("long")),
        post(6, title="사진 없는 팝업", photo=None),
    ]
    api = Api(page)
    api.by_query[""] = (200, payload(posts=posts))
    # 사진은 loading=lazy 라 모든 글이 화면 안에 들어오게 높은 창에서 시작한다.
    page.set_viewport_size({"width": 1440, "height": 5000})
    open_popups(page)
    page.wait_for_selector(".popup-post")
    # 정상(1)·작은 사진이 깨져 원본으로 바꾼 것(2)·긴 제목(5)만 사진이 남는다. 둘 다 깨진 것(3)은 칸째 지우고, 위험한 주소(4)는 만들지 않는다.
    page.wait_for_function("document.querySelectorAll('#popup-results .popup-photo').length===3")
    cards = page.locator(".popup-post")
    assert [cards.nth(i).locator(".popup-photo").count() for i in range(6)] == [1, 1, 0, 0, 1, 0]
    page.wait_for_function(
        "[...document.querySelectorAll('#popup-results .popup-photo img')].every(i=>i.complete&&i.naturalWidth>0)"
    )
    second = cards.nth(1).locator(".popup-photo img")
    assert second.get_attribute("src") == "https://photos.example.test/backup-original.png"
    first = cards.nth(0)
    # 사진은 소개(원문 인용) 옆이고, 원문 인용 안의 링크는 여전히 블로그 원문 하나뿐이다.
    assert first.locator(".popup-intro > .popup-quote + .popup-photo").count() == 1
    assert first.locator(".popup-quote a").get_attribute("href") == "https://blog.naver.com/test/1"
    credit = first.locator(".popup-photo-credit")
    assert "검색 사진" in credit.inner_text()
    source = credit.locator("a")
    assert source.get_attribute("href") == "https://photos.example.test/good-original.png"
    assert source.get_attribute("rel") == "noopener noreferrer"
    # 검색 결과 제목은 화면에 넣지 않는다(그림 설명도 고정 문구).
    assert first.locator(".popup-photo img").get_attribute("alt") == "팝업 관련 검색 사진"
    assert page.evaluate("typeof window.__xss_photo") == "undefined"
    assert page.locator("#popup-results img").count() == 3
    for width, size in ((320, 72), (390, 72), (1440, 96)):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert no_overflow(page), width
        check = page.evaluate(
            """() => [...document.querySelectorAll('#popup-results .popup-post')].filter(c=>c.querySelector('.popup-photo')).map(c=>{
                const card=c.getBoundingClientRect(),img=c.querySelector('.popup-photo img').getBoundingClientRect(),
                  quote=c.querySelector('.popup-quote').getBoundingClientRect(),title=c.querySelector('.popup-title');
                return {inside:img.left>=card.left&&img.right<=card.right+0.5, beside:img.left>=quote.right-0.5,
                  width:Math.round(img.width), clipped:title.scrollWidth>title.clientWidth+1, quote:Math.round(quote.width)};})"""
        )
        assert all(c["inside"] and c["beside"] and not c["clipped"] for c in check), (width, check)
        assert {c["width"] for c in check} == {size}, (width, check)
        assert min(c["quote"] for c in check) >= 160, (width, check)


def test_switch_off_draws_nothing_and_api_is_404(audit_page, monkeypatch):
    page, base, errors = audit_page
    monkeypatch.setenv("DATEMATE_POPUPS_ENABLED", "0")
    main._status_cache.update(value=None, expires=0)
    # 같은 주소에 해시만 바꾸면 새로 읽지 않으므로 쿼리를 붙여 새로 연다.
    page.goto(base + "/?switch=off#explore-section", wait_until="networkidle")
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData")
    assert statusData_flag(page) is False
    assert (
        page.locator("#explore-switch").count() == 0 and page.locator("#popup-browse").count() == 0
    )
    assert page.locator("#explore-places").is_visible()
    assert page.evaluate("fetch('/api/popups?region=서울').then(r=>r.status)") == 404
    main._status_cache.update(value=None, expires=0)


def statusData_flag(page):
    return page.evaluate("statusData.popups_enabled")
