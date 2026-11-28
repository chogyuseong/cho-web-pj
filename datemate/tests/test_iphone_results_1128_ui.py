# ruff: noqa: F811  (pytest 픽스처 audit_page 를 가져와 인자로 받는다)
"""2026-11-28 사용자 아이폰(약 402pt, Safari) 결과 상세('우리 하루, 자세히 보기') 캡처 두 장(브랜치 fix/iphone-results-1128).

1. 화면 왼쪽 가장자리의 세로 회색 탭(›)은 우리 페이지 요소가 아니다(머리글 위 왼쪽 띠에 우리 요소 없음 — 아래 마지막 테스트).
2. 구역 표시줄(section-indicator.js)의 장소 이름이 한 칸 늦음: 2번 카드를 보는데 1번 이름. 장소는 카드 안 이름(h4)의 위치로 판정했는데
   이름은 카드 머리 줄(번호·시간·태그·체류·순서 단추) 아래 한참 밑에 있고, 판정선도 머리글 바로 아래(+12px)라 표시줄 자신의 높이를 빼지 않았다.
3. 장소 카드 머리 줄: 휴대폰(600px 이하)에서 체류 단추 묶음(.stay-stepper, overflow:hidden)이 flex:1(기준 폭 0)이라 첫 줄 남은 틈에 끼어
   '−15분'이 잘리고, 순서 ↑↓ 만 다음 줄로 떨어졌다.
4. '식사' 장소(성수노루)에 커피잔 그림: 그림 고르기(plan-detail.js stopKindKey)가 서버에 없는 is_meal 만 보고 meal 을 놓쳤다
   (서버는 meal·'food:' id — 분류 칩 placeKind 와 같은 기준이어야 함).
5. 사진 칸: 사진 없는 장소의 회색 상자가 바로 위 카드의 이름·분류·주소를 되풀이, 사진 있는 장소는 사진(180px) 아래 빈 회색 띠(사진 칸 최소 높이 210px).
"""

from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401  (pytest fixture)
from test_no_photo_map_link_ui import results_with

PHONES = (320, 375, 402, 430)


def phone_results(page, width):
    page.set_viewport_size({"width": width, "height": 874})
    page.wait_for_timeout(80)


def test_phone_section_bar_names_the_card_under_it(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({"width": 1440, "height": 1000})
    generate(page)
    wait_for_selected_detail(page)
    names = page.evaluate(
        "[...document.querySelectorAll('#plan-detail .stop .timeline-card>h4')].map(h=>h.textContent)"
    )
    assert len(names) >= 3, names

    def place_card(i, gap):
        """i번 카드의 위 끝을 표시줄 아래 끝 + gap 에 둔다."""
        page.evaluate(
            """([i,gap])=>{const bar=document.querySelector('.section-indicator'),header=document.querySelector('body > header');
              const line=Math.max(0,header.getBoundingClientRect().bottom)+bar.getBoundingClientRect().height;
              const stop=document.querySelectorAll('#plan-detail .stop')[i];
              window.scrollBy({top:stop.getBoundingClientRect().top-line-gap,behavior:'instant'});}""",
            [i, gap],
        )
        page.wait_for_timeout(120)
        return page.evaluate("document.querySelector('.section-indicator-current').textContent")

    for width in PHONES:
        phone_results(page, width)
        for i in range(1, len(names)):
            # 캡처처럼 카드 머리 줄(번호·시간)이 표시줄 바로 아래 보이면 표시줄은 그 카드 이름.
            assert place_card(i, 4) == names[i], (width, i, names)
            assert (
                page.locator(".section-indicator-parent").inner_text() == "우리 하루, 자세히 보기"
            )
            # 카드가 아직 화면 아래쪽이면(앞 카드를 보는 중) 그 카드 이름이 아니다.
            assert place_card(i, 120) != names[i], (width, i, names)


HEAD = """card=>{const r=e=>e.getBoundingClientRect(),c=r(card),s=getComputedStyle(card);
  const left=c.left+parseFloat(s.borderLeftWidth)+parseFloat(s.paddingLeft),right=c.right-parseFloat(s.borderRightWidth)-parseFloat(s.paddingRight);
  const head=card.querySelector('.stop-head'),stepper=head.querySelector('.stay-stepper'),order=head.querySelector('.order-buttons'),tags=head.querySelector('.stop-tags');
  const parts=[...head.querySelectorAll('.stop-number,.timeline-stamp,.stop-tag,.stay-stepper button,.stay-value,.order-buttons button')];
  return {left,right,
    outside:parts.filter(e=>r(e).left<left-.5||r(e).right>right+.5).map(e=>e.className+':'+e.textContent+':'+Math.round(r(e).left)+'-'+Math.round(r(e).right)),
    clipped:parts.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent),
    stepper:stepper&&{top:r(stepper).top,bottom:r(stepper).bottom,clip:stepper.scrollWidth-stepper.clientWidth,
      kids:[...stepper.children].map(k=>[Math.round(r(k).left),Math.round(r(k).right)]),box:[Math.round(r(stepper).left),Math.round(r(stepper).right)]},
    order:order&&{top:r(order).top,buttons:[...order.children].map(b=>r(b).top)},
    tagsBottom:r(tags).bottom};}"""


def test_phone_stop_head_buttons_stay_inside_the_card(audit_page):
    page, _, _ = audit_page
    page.set_viewport_size({"width": 1440, "height": 1000})
    generate(page)
    wait_for_selected_detail(page)
    cards = page.locator("#plan-detail .stop .timeline-card")
    assert (
        cards.count() >= 3
        and page.locator("#plan-detail .stop-head .stay-stepper").count() == cards.count()
    )
    for width in PHONES:
        phone_results(page, width)
        for i in range(cards.count()):
            seen = cards.nth(i).evaluate(HEAD)
            # 번호·시간·태그·체류 단추·순서 단추 모두 카드 안쪽, 글자가 잘린 단추 없음.
            assert not seen["outside"] and not seen["clipped"], (width, i, seen)
            stepper, order = seen["stepper"], seen["order"]
            assert stepper["clip"] <= 1, (width, i, stepper)
            assert all(
                stepper["box"][0] - 1 <= a and b <= stepper["box"][1] + 1
                for a, b in stepper["kids"]
            ), (width, i, stepper)
            # 체류 단추는 태그 줄 아래 제 줄, ↑↓ 두 단추는 늘 같은 줄.
            assert stepper["top"] >= seen["tagsBottom"] - 1, (width, i, seen)
            assert abs(order["buttons"][0] - order["buttons"][1]) < 1, (width, i, order)
            if width >= 375:
                # 375px 이상: 체류 단추와 ↑↓ 가 한 줄(캡처는 ↑↓ 만 다음 줄로 떨어짐).
                assert abs(stepper["top"] - order["top"]) < 2, (width, i, seen)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    # 넓은 화면은 그대로: 체류 단추는 늘어나지 않고(flex-grow 0) 머리 줄 오른쪽.
    page.set_viewport_size({"width": 1440, "height": 1000})
    assert (
        page.locator("#plan-detail .stay-stepper").first.evaluate("e=>getComputedStyle(e).flexGrow")
        == "0"
    )


def test_meal_place_gets_the_meal_icon_and_colour(audit_page):
    page, _, _ = audit_page
    # 서버가 주는 식사 표시(app/quality.is_meal: meal 또는 'food:' id). 분류는 '카페·미식' 그대로 온다.
    kinds = page.evaluate(
        """()=>[{id:'tour:1',category:'카페·미식',meal:true},{id:'food:2',category:'카페·미식'},{id:'tour:3',category:'카페·미식'},
          {id:'x',category:'문화·예술'}].map(p=>[stopKindKey(p),placeKind(p)])"""
    )
    # 그림·색(stopKindKey)과 분류 칩 글자(placeKind)가 같은 기준.
    assert kinds == [["meal", "식사"], ["meal", "식사"], ["cafe", "카페"], ["art", "문화·예술"]], (
        kinds
    )
    page.set_viewport_size({"width": 402, "height": 874})
    generate(page)
    wait_for_selected_detail(page)
    page.evaluate(
        "selected.places[1].meal=true;selected.places[1].category='카페·미식';renderDetail()"
    )
    wait_for_selected_detail(page)
    card = page.locator("#plan-detail .stop .timeline-card").nth(1)
    assert card.locator(".stop-tag.step-category").inner_text() == "식사"
    assert card.get_attribute("data-kind") == "meal"
    assert card.locator(":scope>.stop-kind").get_attribute("data-kind") == "meal"


def test_result_card_photo_box_has_no_repeat_and_no_grey_band(audit_page):
    page, base, _ = audit_page
    page.set_viewport_size({"width": 1440, "height": 1000})
    results_with(page, base, ["photo", "none", "photo"])
    cards = page.locator("#plan-detail .stop .timeline-card")
    empty = cards.nth(1)
    empty.locator(".photo-empty-body").wait_for()
    for width in PHONES + (740, 1440):
        page.set_viewport_size({"width": width, "height": 874})
        page.wait_for_timeout(80)
        # 사진 없는 장소: 카드 위에 이미 있는 이름·분류·주소를 회색 상자로 되풀이하지 않는다(800px 이하, 넓은 화면은 예전 그대로). 안내 글·지도 링크는 그대로.
        assert empty.locator(".photo-empty-card").is_visible() == (width > 800), width
        assert (
            empty.locator(".photo-empty-body .photo-status").is_visible()
            and empty.locator(".photo-map-link").is_visible()
        ), width
        # 사진 있는 장소: 사진 칸(.photo-viewport)이 사진 높이와 같다(아래 빈 회색 띠 없음).
        for i in (0, 2):
            card = cards.nth(i)
            card.scroll_into_view_if_needed()
            page.wait_for_function(
                "c=>{const i=c.querySelector('.place-photo img');return i&&!i.hidden&&i.naturalWidth>0}",
                arg=card.element_handle(),
                timeout=30000,
            )
            sizes = card.evaluate(
                "c=>[c.querySelector('.photo-viewport').getBoundingClientRect().height,c.querySelector('.place-photo img').getBoundingClientRect().height]"
            )
            assert abs(sizes[0] - sizes[1]) < 1, (width, i, sizes)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    # 다른 곳(코스 미리보기 3칸)의 사진 없는 칸은 이름표를 그대로 둔다(그 칸에는 장소 이름이 따로 없다).
    page.evaluate("document.querySelectorAll('details.plan-photo-details').forEach(d=>d.open=true)")
    assert (
        page.locator(".plan-card.selected .plan-photo-item")
        .nth(1)
        .locator(".photo-empty-card")
        .is_visible()
    )


def test_left_edge_tab_is_not_a_page_element(audit_page):
    """캡처 왼쪽 가장자리의 세로 회색 탭(›)은 우리 것이 아니다: 결과 상세를 보는 휴대폰 화면에서 왼쪽 24px 띠의 맨 위 요소는
    머리글·표시줄·본문뿐이고, 화면에 고정된(fixed) 우리 요소 중 왼쪽 끝에 붙은 좁은 세로 막대가 없다."""
    page, _, _ = audit_page
    page.set_viewport_size({"width": 1440, "height": 1000})
    generate(page)
    wait_for_selected_detail(page)
    page.set_viewport_size({"width": 402, "height": 874})
    page.evaluate(
        "document.querySelectorAll('#plan-detail .stop')[1].scrollIntoView({block:'start',behavior:'instant'})"
    )
    page.wait_for_timeout(150)
    seen = page.evaluate(
        """()=>{const out=[];for(let y=2;y<240;y+=6)for(const x of [2,10,20]){const e=document.elementFromPoint(x,y);
            if(e&&!e.closest('body > header,.section-indicator,main'))out.push([x,y,e.tagName+'.'+e.className]);}
          const bars=[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);if(s.position!=='fixed'||s.visibility==='hidden'||!e.getClientRects().length)return false;
            const r=e.getBoundingClientRect();return r.left<=1&&r.width<60&&r.height>60;}).map(e=>e.tagName+'.'+e.className);
          return {out,bars};}"""
    )
    assert not seen["out"] and not seen["bars"], seen
