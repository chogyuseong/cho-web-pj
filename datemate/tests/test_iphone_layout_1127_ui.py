# ruff: noqa: F811  (pytest 픽스처 audit_page 를 가져와 인자로 받는다)
"""2026-11-27 사용자 아이폰(약 402pt, Safari) 캡처 두 장에서 보인 휴대폰 화면 깨짐(브랜치 fix/iphone-layout-1127).

1. 하단 메뉴: '코스 만들기'가 현재 탭인데 '추천 결과' 칸에 흰 알약·진한 글자가 남았다. 터치 화면은 누른 칸에 :hover 가 붙어
   남는데(iOS), redesign.css 2) 의 메뉴 :hover(흰 바탕·진한 글자)가 하단 바에도 걸렸다.
2. 하단 고정 막대(하단 메뉴 · 결과 행동 막대 · 코스 바구니)가 내용을 가린다: 스크롤 끝 여백이 막대 높이와 딱 같아 틈이 없었고,
   '…로 이동'(scrollIntoView·포커스)이 막대 밑으로 숨겼다(scroll-padding-bottom 없음).
3. 결과 머리: '추천 일정 3개'가 축제 단추 옆에 떠 있고 팝업 단추만 다음 줄로 떨어졌다.
4. 예산 사용률 카드: 금액 글자와 막대가 한 줄을 나눠 써서 글자가 좁게 줄바꿈.
5. 지역 선택: 동네 칩과 '데이트할 지역' 제목 사이 틈 없음, 지역 칸과 '검색' 단추 높이 다름, '지도에서 고르기'가 칸에 붙음.
"""

from test_functional_audit import audit_page, generate  # noqa: F401  (pytest fixture)

PHONES = (320, 375, 402, 430)


def ready(page):
    page.wait_for_function(
        "document.querySelector('#origin-location .origin-search') && document.querySelector('body > header nav')"
    )


def test_phone_bottom_menu_keeps_no_hover_highlight_after_a_tap(audit_page):
    page, _, _ = audit_page
    ready(page)
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        # 캡처처럼 '코스 만들기'를 현재 탭으로 둔다(조건 화면으로 스크롤).
        page.locator("#planner-section").scroll_into_view_if_needed()
        page.evaluate("window.syncHeaderNav()")
        page.wait_for_function("document.getElementById('nav-plan').classList.contains('active')")
        # 터치 화면에서 누른 칸에 남는 :hover 를 흉내 낸다. 현재 탭이 아닌 '추천 결과'에 마우스를 올려 둔다.
        page.hover("#nav-results")
        styles = page.evaluate("""()=>Object.fromEntries(['nav-plan','nav-home','nav-results'].map(id=>{
            const s=getComputedStyle(document.getElementById(id));return [id,[s.backgroundColor,s.color]];}))""")
        assert styles["nav-results"][0] in ("rgba(0, 0, 0, 0)", "transparent"), (width, styles)
        # 글자색도 고르지 않은 다른 칸('테마 추천')과 같아야 한다 — 현재 탭('코스 만들기')만 강조색.
        assert styles["nav-results"][1] == styles["nav-home"][1], (width, styles)
        assert styles["nav-plan"][1] != styles["nav-home"][1], (width, styles)
        page.mouse.move(1, 1)
        page.evaluate("window.scrollTo(0,0)")
    # 데스크톱 메뉴의 :hover(흰 알약)는 그대로.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.hover("#nav-explore")
    assert (
        page.evaluate("getComputedStyle(document.getElementById('nav-explore')).backgroundColor")
        == "rgb(255, 255, 255)"
    )


def bottom_bar_top(page):
    return page.evaluate("""()=>Math.min(innerHeight,...[...document.querySelectorAll('body > header nav, .results-actionbar, #basket-dock')]
        .filter(e=>e.getClientRects().length&&getComputedStyle(e).position==='fixed').map(e=>e.getBoundingClientRect().top))""")


def assert_clears_bar(page, selector, width):
    """스크롤 끝에서 마지막 내용, '…로 이동'한 칸이 모두 고정 막대 위에 틈을 두고 보인다."""
    bar = bottom_bar_top(page)
    assert bar < page.evaluate("innerHeight"), width
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_timeout(50)
    last = page.evaluate("""()=>{const kids=[...document.body.children].filter(e=>e.getClientRects().length&&getComputedStyle(e).position!=='fixed');
        return Math.max(...kids.map(e=>e.getBoundingClientRect().bottom));}""")
    assert last <= bar - 12, (width, last, bar)
    page.evaluate("window.scrollTo(0,0)")
    if not selector:
        return
    target = page.locator(selector).first
    target.evaluate("e=>e.scrollIntoView({block:'end',behavior:'instant'})")
    page.wait_for_timeout(50)
    box = target.bounding_box()
    assert box["y"] + box["height"] <= bar - 8, (width, selector, box, bar)


def test_phone_fixed_bars_leave_room_for_content(audit_page):
    page, _, _ = audit_page
    ready(page)
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(50)
        # 코스 만들기: 하단 메뉴. 종료 시간 칸으로 이동하면 메뉴 위에 보인다.
        assert_clears_bar(page, "#conditions [name=end]", width)
    page.set_viewport_size({"width": 1440, "height": 1000})
    generate(page)
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(50)
        # 결과 화면: 하단 메뉴 대신 행동 막대(지도 보기·일정·링크 복사·공유 티켓).
        assert page.locator(".results-actionbar").is_visible()
        assert_clears_bar(page, "#plan-detail .stop .timeline-card", width)
    # 장소 둘러보기: 하단 메뉴 위에 코스 바구니가 함께 뜨면 두 막대를 합친 높이만큼 비운다.
    page.set_viewport_size({"width": 402, "height": 874})
    page.evaluate(
        "document.getElementById('nav-explore').click()"
    )  # 결과 화면의 휴대폰 하단 메뉴는 행동 막대가 대신해 숨어 있다.
    page.wait_for_function("document.body.classList.contains('show-explore')")
    page.evaluate("Basket.toggle({id:'t1',name:'시험 카페',lat:37.5,lon:127.0},'서울')")
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(100)
        assert (
            page.locator("#basket-dock").is_visible()
            and page.locator("body > header nav").is_visible()
        )
        assert_clears_bar(page, None, width)
    page.evaluate("Basket.clear()")
    # 데스크톱은 고정 막대가 없어 아래 여백도 없다.
    page.set_viewport_size({"width": 1440, "height": 1000})
    assert page.evaluate("getComputedStyle(document.body).paddingBottom") == "0px"


def test_phone_results_head_and_budget_card_are_tidy(audit_page):
    page, _, _ = audit_page
    ready(page)
    page.set_viewport_size({"width": 1440, "height": 1000})
    generate(page)
    page.evaluate(
        """()=>{for(const [id,t] of [['festival-jump','서울 축제 13건 보기 ↓'],['popup-jump','서울 팝업스토어 글 50건 보기 ↓']]){const b=document.getElementById(id);b.hidden=false;b.textContent=t;}}"""
    )
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(50)
        box = lambda s: page.locator(s).bounding_box()  # noqa: E731
        head, title, count = box(".results-heading"), box("#results-title"), box("#result-count")
        festival, popup = box("#festival-jump"), box("#popup-jump")
        # 결과 수는 제목 아래 제 줄, 왼쪽 정렬.
        assert count["y"] >= title["y"] + title["height"] - 1, width
        assert abs(count["x"] - head["x"]) < 2, (width, count, head)
        # 단추 두 개는 결과 수 아래에서 같은 왼쪽 끝·같은 폭으로 줄을 맞춘다(들쭉날쭉하지 않게).
        assert festival["y"] >= count["y"] + count["height"] - 1, width
        assert abs(festival["x"] - head["x"]) < 2 and abs(popup["x"] - head["x"]) < 2, (
            width,
            festival,
            popup,
            head,
        )
        assert abs(festival["width"] - popup["width"]) < 2, (width, festival, popup)
        assert festival["height"] >= 44 and popup["height"] >= 44, width
        # 예산 사용률: 글자 줄과 막대를 나눈다 — 막대는 글자 아래, 카드 안쪽 폭을 거의 다 쓴다.
        card, text, bar = (
            box(".results-kpis .kpi-budget"),
            box(".results-kpis .kpi-budget .kpi-text"),
            box(".results-kpis .kpi-budget .kpi-bar"),
        )
        assert bar["y"] >= text["y"] + text["height"] - 1, (width, text, bar)
        assert bar["width"] >= card["width"] - 40, (width, card, bar)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    # 데스크톱: 예산 카드는 글자 옆 막대 그대로.
    page.set_viewport_size({"width": 1440, "height": 1000})
    assert (
        page.locator(".results-kpis .kpi-budget").first.evaluate(
            "e=>getComputedStyle(e).flexDirection"
        )
        == "row"
    )
    assert (
        page.locator(".results-kpis .kpi-budget .kpi-bar").first.evaluate(
            "e=>getComputedStyle(e).width"
        )
        == "84px"
    )


def test_phone_area_search_row_is_spaced_and_aligned(audit_page):
    page, _, _ = audit_page
    ready(page)
    for width in PHONES:
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(50)
        box = lambda s: page.locator(s).bounding_box()  # noqa: E731
        chips, host = box("#conditions .area-group .quick-chips"), box("#origin-location")
        field, search, row, picker = (
            box("#origin-location .origin-search input"),
            box("#origin-location .origin-search-button"),
            box("#origin-location .origin-search"),
            box("#origin-location > button"),
        )
        # 동네 칩 아래 '데이트할 지역' 제목과 틈.
        assert host["y"] - (chips["y"] + chips["height"]) >= 12, (width, chips, host)
        # 지역 칸과 '검색' 단추는 같은 높이·같은 줄.
        assert abs(field["height"] - search["height"]) < 1, (width, field, search)
        assert abs(field["y"] - search["y"]) < 1, (width, field, search)
        # '지도에서 고르기'는 검색 줄에서 떨어져 있다.
        assert picker["y"] - (row["y"] + row["height"]) >= 8, (width, row, picker)
