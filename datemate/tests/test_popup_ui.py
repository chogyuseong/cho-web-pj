"""팝업 글 둘러보기 화면: 실제 브라우저, /api/popups 는 page.route 가짜 응답(외부 호출 없음).

2026-11-20(특약 2.2)부터 화면은 네이버 블로그 검색 결과 블록 하나다: 받은 순서·건수 그대로, 제목·요약 그대로,
글에서 읽은 기간·장소·사진 칸 없음, 블록 안에는 네이버가 준 값과 출처 표시만.
"""

import json
from urllib.parse import parse_qs, urlsplit

from test_functional_audit import audit_page  # noqa: F401

from app import main

LONG_TITLE = (
    "성수 연무장길 대형 캐릭터 팝업스토어 SUPERLONGBRANDNAMEWITHOUTANYSPACESATALLFORTESTING "
    "웨이팅·예약·굿즈 가격·포토존까지 한 번에 정리한 아주 긴 제목의 후기 글입니다"
)
QUERY = "2026년 11월 서울 팝업스토어"


def post(i, **extra):
    base = dict(
        id=f"popup-post:{i:016x}",
        title=f"팝업 글 {i}",
        description=f"요약 {i} 팝업 운영 정보",
        url=f"https://blog.naver.com/test/{i}",
        blogger=f"블로거{i}",
        posted_at="2026-11-14",
    )
    return base | extra


def hub(hub_id, name, lat, lon, kind="building", anchor=None, district="영등포구", region="서울"):
    return dict(
        hub_id=hub_id,
        name=name,
        kind=kind,
        anchor=anchor,
        region=region,
        district=district,
        lat=lat,
        lon=lon,
    )


BUILDING = hub("seoul-thehyundai", "더현대 서울", 37.526, 126.928)
AREA = hub(
    "seoul-area-seongsu", "성수 일대", 37.5446, 127.056, "area", "성수동 카페거리", "성동구"
)


def payload(status="ready", posts=None, region="서울", hubs=None, query=QUERY, **extra):
    posts = posts if posts is not None else []
    data = dict(
        status=status,
        message=None,
        region=region,
        q="",
        visit_date="2026-11-14",
        sources=[
            dict(
                id="blog",
                name="네이버 블로그 검색",
                status="ok",
                query=query,
                sort="sim",
                returned=len(posts),
                display=50,
            )
        ],
        attribution="네이버 블로그 검색 결과",
        posts=posts,
        counts=dict(shown=len(posts), returned=len(posts)),
        hubs=hubs if hubs is not None else [],
        hubs_version="hubs-test",
        hub_coordinates=dict(provider="한국관광공사 TourAPI", checked="2026-11-20"),
    )
    return data | extra


# 예전에는 나누거나(모아 보기) 뒤로 보내던 글들. 이제는 받은 순서 그대로 한 목록이다.
READY = payload(
    posts=[
        post(4, title="11월 성수 팝업 총정리 10곳"),
        post(1, title="더현대 서울 올기 팝업", description="기간 2026.10.20~2026.11.16 더현대 서울"),
        post(3, title="<img src=x onerror=window.__xss=1> 팝업", blogger=None, posted_at=None),
        post(2, title=LONG_TITLE),
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


# 블록 안의 글자 조각(위에서 아래로). 블록에 우리 문구가 끼어들지 않았는지 본다.
BLOCK_TEXTS = """()=>{const out=[],walk=n=>{for(const c of n.childNodes){if(c.nodeType===3){if(c.textContent.trim())out.push(c.textContent.trim());}else walk(c);}};
  walk(document.querySelector('#popup-results .popup-naver-block'));return out;}"""


def test_popup_browse_shows_one_untouched_naver_block_and_its_states(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    api.by_query.update(
        {
            "없음": (200, payload("empty", [], message="이 검색어로 검색된 글이 없어요.")),
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
    # 어떤 검색어의 결과인지와 받은 건수를 그대로 적는다.
    assert page.locator("#popup-status").inner_text() == f"네이버 블로그 검색 ‘{QUERY}’ · 정확도순 4건"
    # 왜 기간·장소가 없는지는 블록 밖 한 줄로.
    about = page.locator("#popup-browse .popup-about").inner_text()
    assert "받은 순서 그대로" in about and "기간과 장소는 글 원문에서 확인" in about
    assert page.locator(".popup-naver-block .popup-about").count() == 0
    # 블록은 하나, 받은 순서 그대로(나누거나 다시 줄 세우지 않음).
    assert page.locator("#popup-results .popup-list").count() == 1
    assert page.locator(".popup-list h3").all_inner_texts() == ["네이버 블로그 검색 결과 4건"]
    assert page.locator(".popup-post .popup-title").all_inner_texts() == [
        p["title"] for p in READY["posts"]
    ]
    assert page.locator(".popup-post").evaluate_all("cs=>cs.map(c=>c.dataset.postId)") == [
        p["id"] for p in READY["posts"]
    ]
    # 출처 표시(네이버 검색결과 · 블로그 검색 · 같은 검색어의 원본 · NAVER 오픈 API)가 블록 안에 있다.
    mark = page.locator(".popup-naver-block .naver-attribution")
    assert mark.count() == 1 and "네이버 검색결과 · 블로그 검색" in mark.inner_text()
    original = mark.locator("a").first.get_attribute("href")
    assert original.startswith("https://search.naver.com/search.naver?where=blog&query=")
    assert "NAVER 오픈 API" in mark.inner_text()
    # 블록 안의 글자는 제목 줄·출처 표시·글(블로거·작성일, 제목, 요약, 원문 링크)뿐이다. 글 사이에 우리 문구·판정이 없다.
    expected = ["네이버 블로그 검색 결과 4건", "네이버 검색결과 · 블로그 검색", "·", "원본 ↗", "·", "NAVER 오픈 API"]
    for p in READY["posts"]:
        meta = " · ".join(filter(None, [p["blogger"], (p["posted_at"] or "").replace("-", ".")]))
        expected += ([meta] if meta else []) + [p["title"], p["description"], "블로그 원문 보기 ↗"]
    assert page.evaluate(BLOCK_TEXTS) == expected
    # 예전의 읽은 정보 칸·기간·장소 줄·사진·모아 보기 나눔·뺀 글 안내가 없다.
    for gone in (".popup-reading", ".popup-facts", ".popup-fact", ".popup-photo", ".popup-note", "dl", "img", "button"):
        assert page.locator(f"#popup-results {gone}").count() == 0, gone
    text = page.locator("#popup-results").inner_text()
    for word in ("읽은 정보", "기간 미확인", "위치 미확인", "진행 중", "모아 소개", "숨겼어요", "뺐어요"):
        assert word not in text, word
    first = page.locator(".popup-post").nth(1)
    link = first.locator("a")
    assert link.count() == 1 and link.get_attribute("href") == "https://blog.naver.com/test/1"
    assert link.get_attribute("rel") == "noopener noreferrer"
    assert first.locator(".popup-summary").inner_text() == "기간 2026.10.20~2026.11.16 더현대 서울"
    # 검색 결과 글은 텍스트로만 넣는다.
    third = page.locator(".popup-post").nth(2)
    assert third.locator(".popup-title").inner_text().startswith("<img")
    assert third.locator(".popup-meta").count() == 0
    assert page.evaluate("typeof window.__xss") == "undefined"
    # 결과 없음, 전체 실패(다시 찾기), 키 없음, 한도 초과(HTTP 429)를 다르게 보인다.
    search(page, "없음")
    page.wait_for_selector(".popup-state-empty")
    assert page.locator("#popup-status").inner_text().endswith("0건")
    assert page.locator(".popup-naver-block").count() == 0
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
    assert not errors, errors


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
    many = [
        post(
            i,
            title=LONG_TITLE + f" {i}",
            blogger="아주아주긴블로그이름SUPERLONGBLOGGERNAMEWITHOUTSPACES의 데이트 기록장",
        )
        for i in range(12)
    ]
    api.by_query[""] = (200, payload(posts=many, query="2026년 11월 서울 " + "긴검색어" * 6 + " 팝업스토어"))
    open_popups(page)
    page.wait_for_selector(".popup-post")
    # 「글 더 보기」는 뒤쪽 글을 접어 둔 것뿐이다: 펼쳐도 순서는 받은 그대로, 포커스는 새로 열린 첫 글로.
    assert page.locator(".popup-more").inner_text() == "글 더 보기 (2건)"
    assert page.locator(".popup-post").count() == 10
    page.locator(".popup-more").click()
    assert page.locator(".popup-post .popup-title").all_inner_texts() == [p["title"] for p in many]
    assert page.locator(".popup-more").count() == 0
    assert page.evaluate(
        "document.activeElement===document.querySelectorAll('.popup-post')[10].querySelector('.popup-source-link')"
    )
    for width in (320, 390, 768, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert no_overflow(page), width
        check = page.evaluate(
            """() => {
              const area=document.querySelector('#explore-section');
              const small=[...area.querySelectorAll('#popup-browse p,#popup-browse h3,#popup-browse h4,#popup-browse a,#popup-browse label,#popup-browse span,#explore-switch button')]
                .filter(e=>e.getClientRects().length && e.textContent.trim() && parseFloat(getComputedStyle(e).fontSize)<14)
                .map(e=>e.className+':'+getComputedStyle(e).fontSize);
              const short=[...area.querySelectorAll('#popup-browse button,#explore-switch button,#popup-browse .popup-source-link,#popup-browse select,#popup-browse input')]
                .filter(e=>e.getClientRects().length && e.getBoundingClientRect().height<44).map(e=>e.textContent.trim()||e.id);
              const clipped=[...area.querySelectorAll('.popup-title,.popup-summary,.popup-meta,.popup-status,.popup-list h3')]
                .filter(e=>e.scrollWidth>e.clientWidth+1 || getComputedStyle(e).textOverflow==='ellipsis' || getComputedStyle(e).webkitLineClamp!=='none')
                .map(e=>e.textContent.slice(0,20));
              const outside=[...area.querySelectorAll('.popup-post,.popup-naver-block,.naver-attribution')].filter(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth;}).length;
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
