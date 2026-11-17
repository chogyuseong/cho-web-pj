"""코스 결과의 팝업 글 구역과 주변 코스 버튼(1단계 1b): 실제 브라우저, /api/popups 는 page.route 가짜 응답(외부 호출 없음)."""

import json
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from test_feedback_ui import route_festivals
from test_festival_restore import saved_plan
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401
from test_popup_ui import AREA, BUILDING, CONFIRMED, LONG_TITLE, payload, post

from app import main
from app.main import app

SEONGSU = dict(name="서울 성동구 성수동 · 성수역", lat=37.5446, lon=127.0559)
BUILDING = BUILDING | dict(district="영등포구")
AREA = AREA | dict(district="성동구")
WORLD = dict(
    hub_id="seoul-lotteworld-mall",
    name="롯데월드몰",
    kind="building",
    anchor=None,
    region="서울",
    district="송파구",
    level="building",
    reason="verified",
    lat=37.5126,
    lon=127.1025,
)
UPCOMING = dict(
    level="confirmed",
    start="2026-12-11",
    end="2027-01-10",
    evidence=["2026.12.11~2027.01.10"],
    status="upcoming",
    end_only=False,
)
UNVERIFIED = dict(
    hub_id="seoul-lotte-jamsil",
    name="롯데백화점 잠실점",
    kind="building",
    anchor=None,
    region="서울",
    district="송파구",
    level="unverified",
    reason="ambiguous",
)

# 서버 순서(일반 글 → 거점 → 최신 → ID)와 거리순이 다르게 섞는다. 성수 일대 글 둘은 ID 가 거꾸로 온다.
COURSE = payload(
    "ready",
    [
        post(1, title="더현대 서울 올기 팝업", period=CONFIRMED, place=BUILDING),
        post(12, title="성수 짱구 팝업", place=AREA),
        post(11, title="성수 디저트 팝업", place=AREA, period=UPCOMING),
        post(3, title="롯데월드몰 팝업", period=CONFIRMED, place=WORLD),
        post(4, title="장소 못 읽은 팝업"),
        post(5, title="잠실 어딘가 팝업", place=UNVERIFIED),
        post(6, title="성수 팝업 총정리", roundup=True, place=AREA),
    ],
)
CONDITIONS = dict(mode="real", region="서울", visit_date="2026-11-20", origin=SEONGSU)


def near(i):
    """성수에서 북쪽으로 1km 남짓씩 떨어진 건물 거점. 3 과 4 는 같은 좌표(거리 동률)."""
    return WORLD | dict(
        hub_id=f"seoul-test-{i}",
        name=f"건물 거점 {i}",
        lat=37.5446 + 0.01 * (min(i, 3) + 1),
        lon=127.0559,
    )


class Api:
    """방문일(visit_date)로 응답을 고른다. hold 에 든 방문일은 응답하지 않고 route 를 남겨 둔다."""

    def __init__(self, page, default=COURSE):
        self.requests = []
        self.held = {}
        self.hold = set()
        self.by_day = {}
        self.default = (200, default)
        page.route(lambda url: urlsplit(url).path == "/api/popups", self.handle)

    def handle(self, route):
        query = {k: v[0] for k, v in parse_qs(urlsplit(route.request.url).query).items()}
        self.requests.append(query)
        day = query.get("visit_date", "")
        if day in self.hold:
            self.held[day] = route
            return
        status, body = self.by_day.get(day, self.default)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def idle(page):
    page.wait_for_function(
        "document.querySelector('#popup-course-results').getAttribute('aria-busy')==='false'"
    )


def load(page, **extra):
    page.evaluate("c=>{showPlannerPage(true,false);PopupCourse.load(c)}", CONDITIONS | extra)
    idle(page)


def titles(page, scope="#popup-course-results>.popup-list"):
    return page.locator(f"{scope} .popup-title").all_inner_texts()


def hubs(page):
    """보이는 거점 묶음 머리: 이름·거리·글 수."""
    return page.evaluate(
        "[...document.querySelectorAll('#popup-course-results .popup-hub')].map(h=>({"
        "name:h.querySelector('.popup-hub-name').textContent,"
        "distance:h.querySelector('.popup-hub-head .popup-distance dd')?.textContent??null,"
        "count:h.querySelector('.popup-hub-count').textContent}))"
    )


def distances(page):
    return [hub["distance"] for hub in hubs(page)]


def hub(page, text):
    return page.locator("#popup-course-results .popup-hub").filter(has_text=text)


def plan_jobs(page):
    """새 추천 요청 본문을 모으고 503 으로 끝낸다(코스 검색을 실제로 돌리지 않음)."""
    submitted = []
    page.route(
        "**/api/plan-jobs",
        lambda route: (
            submitted.append(json.loads(route.request.post_data)),
            route.fulfill(status=503, json={"detail": "점검용 중단"}),
        ),
    )
    return submitted


def submitted_after(page, submitted, count):
    for _ in range(100):
        if len(submitted) >= count:
            break
        page.wait_for_timeout(50)
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    assert len(submitted) == count
    return submitted[-1]


def course_request(page):
    """generate() 가 보낸 첫 추천 요청 본문."""
    sent = []
    page.on(
        "request",
        lambda r: sent.append(json.loads(r.post_data))
        if r.method == "POST" and urlsplit(r.url).path == "/api/plan-jobs"
        else None,
    )
    return sent


KEPT = (
    "visit_date",
    "start",
    "end",
    "people",
    "budget",
    "budget_unlimited",
    "transport",
    "count",
    "themes",
    "date_category",
    "date_subcategory",
    "theme_mode",
    "setting",
    "avoid",
    "max_leg",
    "max_walk",
    "include_meal",
    "stay_minutes",
    "reservation",
)


def test_located_posts_by_distance_unknown_folded_and_states(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    load(page)
    assert api.requests[-1] == dict(region="서울", visit_date="2026-11-20")
    assert page.locator("#popup-course-title").inner_text() == "서울에서 찾은 팝업스토어 글"
    section = page.locator("#popup-course")
    assert (
        "네이버 블로그 검색 결과예요. 기간과 장소는 원문에서 확인해 주세요." in section.inner_text()
    )
    # 축제 구역 바로 뒤, 부가 정보 앞(모바일 DOM 순서도 같음).
    assert page.evaluate(
        "document.querySelector('#festival-section').nextElementSibling.id==='popup-course'"
        "&&document.querySelector('#popup-course').nextElementSibling.id==='plan-extras'"
    )
    # 기본 목록은 위치가 확인된 글을 거점별로 묶은 것. 묶음은 출발지에서 가까운 순이고,
    # 장소·거리·글 수는 묶음 머리에 한 번만 적는다("검색된 글 N건", 인기 지표가 아님).
    assert hubs(page) == [
        dict(
            name="성수 일대(대략)",
            distance="출발지에서 직선거리 1km 이내 · 성수 일대 기준",
            count="검색된 글 3건",
        ),
        dict(name="롯데월드몰", distance="출발지에서 직선거리 약 5.4km", count="검색된 글 1건"),
        dict(name="더현대 서울", distance="출발지에서 직선거리 약 11km", count="검색된 글 1건"),
    ]
    assert hub(page, "성수 일대").locator(".popup-hub-head .popup-place dd").inner_text() == (
        "동네 기준점 성수역 · 대략 위치"
    )
    assert hub(page, "롯데월드몰").locator(".popup-hub-head .popup-place dd").inner_text() == (
        "건물 위치 확인 · 층·입구는 원문 확인"
    )
    # 묶음마다 처음 1건 + 더 보기. 묶음 안은 기간이 확인된 글(오픈 예정) 먼저.
    assert titles(page) == ["성수 디저트 팝업", "롯데월드몰 팝업", "더현대 서울 올기 팝업"]
    heading = page.locator("#popup-course-results>.popup-list>h4").inner_text()
    assert heading == "위치를 확인한 글 5건 · 장소 3곳 · 출발지에서 가까운 순(직선거리)"
    notes = page.locator("#popup-course-results>.popup-note").all_inner_texts()
    assert notes == [
        "오늘(2026.11.14) 기준 종료로 확인된 글 1건은 숨겼어요.",
        "다른 시·도 장소로 읽힌 글 2건은 뺐어요.",
    ]
    # 버튼은 묶음마다 하나. 문구는 거점 종류로 나뉘고, 글마다 다른 기간 상태는 버튼 옆에 글 수로 적는다.
    seongsu = hub(page, "성수 일대")
    assert seongsu.get_by_role("button", name="이 일대 주변 코스 추천받기").count() == 1
    assert seongsu.locator(".popup-hub-head .popup-action-note").inner_text() == (
        "오픈 예정 1건 · 기간 미확인 2건 · 방문일에 열리는지 글마다 원문에서 확인해 주세요."
    )
    ongoing = hub(page, "롯데월드몰").locator(".popup-action")
    assert ongoing.locator("button").inner_text() == "이 장소 주변 코스 추천받기"
    assert ongoing.locator(".popup-action-note").count() == 0
    # 글 항목에는 그 글에만 해당하는 것만: 장소·거리·버튼을 글마다 되풀이하지 않는다.
    posts = page.locator("#popup-course-results .popup-hub .popup-post")
    assert posts.count() == 3
    assert "오픈 예정" in posts.nth(0).locator(".popup-period dd").inner_text()
    # 원문 인용(제목·요약·링크)과 읽은 정보가 다른 칸이다.
    assert posts.nth(0).locator(".popup-quote .popup-period").count() == 0
    assert posts.nth(0).locator(".popup-reading .popup-period").count() == 1
    # 그다음은 글 ID 순(…06 총정리 → …0c 짱구).
    seongsu.get_by_role("button", name="이 장소의 글 2건 더 보기").click()
    assert titles(page, "#popup-course-results .popup-hub[data-hub-id='seoul-area-seongsu']") == [
        "성수 디저트 팝업",
        "성수 팝업 총정리",
        "성수 짱구 팝업",
    ]
    assert posts.count() == 5
    assert posts.locator(".popup-place, .popup-distance, button").count() == 0
    assert posts.nth(1).locator(".popup-kind dd").inner_text() == "여러 팝업을 모아 소개한 글"
    # 위치 미확인 글은 접혀 있고, 펼치면 거리 없이 이유 한 줄만 있다.
    toggle = page.locator(".popup-unknown-toggle")
    assert toggle.inner_text() == "위치를 확인하지 못한 글 2건 보기"
    assert toggle.get_attribute("aria-expanded") == "false"
    assert page.locator("#popup-course-unknown .popup-post").count() == 0
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    unknown = page.locator("#popup-course-unknown .popup-post")
    assert titles(page, "#popup-course-unknown") == ["장소 못 읽은 팝업", "잠실 어딘가 팝업"]
    assert (
        unknown.locator(".popup-distance").count() == 0 and unknown.locator("button").count() == 0
    )
    assert (
        unknown.nth(1).locator(".popup-action-note").inner_text()
        == "위치를 확인하지 못해 주변 코스 추천을 할 수 없어요."
    )
    toggle.click()
    assert page.locator("#popup-course-unknown").is_hidden()

    # 출발지가 없으면(이어받은 검색·데모) 거리 없이 거점이 처음 나온 순서. 데모는 그렇다고 알린다.
    load(page, mode="demo", origin=dict(name="데모 출발점", lat=37.575, lon=126.985))
    assert [h["name"] for h in hubs(page)] == ["더현대 서울", "성수 일대(대략)", "롯데월드몰"]
    assert distances(page) == [None] * 3
    assert "받은 순서" in page.locator("#popup-course-results>.popup-list>h4").inner_text()
    assert page.locator("#popup-course-demo").is_visible()

    # 첫 화면은 묶음 3곳 + "다른 장소 N곳 더 보기". 같은 거리의 두 거점은 거점 ID 순.
    many = [post(20 + i, title=f"성수 팝업 {i}", place=AREA) for i in range(5)] + [
        # 받은 순서는 4 가 3 보다 먼저다(거점 ID 동률 규칙이 실제로 순서를 정하는지 보려고).
        post(40 + i, title=f"건물 팝업 {i}", place=near(i))
        for i in (0, 1, 2, 4, 3)
    ]
    api.by_day["2026-11-21"] = (200, payload(posts=many))
    load(page, visit_date="2026-11-21")
    assert page.locator("#popup-course-demo").is_hidden()
    assert [h["name"] for h in hubs(page)] == ["성수 일대(대략)", "건물 거점 0", "건물 거점 1"]
    assert page.locator("#popup-course-results .popup-hub .popup-post").count() == 3
    page.get_by_role("button", name="다른 장소 3곳 더 보기").click()
    # 거점 3·4 는 같은 좌표라 거점 ID 순(seoul-test-3 → seoul-test-4).
    assert [h["name"] for h in hubs(page)][3:] == ["건물 거점 2", "건물 거점 3", "건물 거점 4"]
    page.get_by_role("button", name="이 장소의 글 4건 더 보기").click()
    assert page.locator("#popup-course-results .popup-hub .popup-post").count() == 10
    assert page.locator(".popup-unknown-toggle").count() == 0

    # 위치 확인 0건(미확인은 있음) / 글 0건 / 일부 좌표 실패 / 전체 실패 / 키 없음 / 429 를 다르게 보인다.
    api.by_day.update(
        {
            "2026-11-22": (200, payload(posts=[post(30), post(31, place=UNVERIFIED)])),
            "2026-11-23": (
                200,
                payload("empty", [], message="검색된 글 중에 보여 드릴 팝업 글이 없어요."),
            ),
            "2026-11-24": (
                200,
                payload(
                    "partial",
                    [post(32, place=BUILDING)],
                    message="일부 장소의 위치를 확인하지 못해 위치 미확인으로 표시했어요.",
                ),
            ),
            "2026-11-25": (
                200,
                payload("unavailable", [], message="네이버 블로그 검색에 연결하지 못했어요."),
            ),
            "2026-11-26": (
                200,
                payload("key_missing", [], message="네이버 검색 키가 설정되지 않았어요."),
            ),
            "2026-11-27": (429, {"detail": "새 팝업 검색이 많아요. 잠시 후 다시 시도해 주세요."}),
            "2026-11-28": (404, {"detail": "없는 기능이에요."}),
        }
    )
    load(page, visit_date="2026-11-22")
    assert page.locator(".popup-state-unlocated").is_visible()
    assert page.locator(".popup-unknown-toggle").inner_text() == "위치를 확인하지 못한 글 2건 보기"
    load(page, visit_date="2026-11-23")
    assert page.locator(".popup-state-empty").is_visible()
    assert "보여 드릴 팝업 글이 없어요" in page.locator("#popup-course-status").inner_text()
    load(page, visit_date="2026-11-24")
    assert page.locator("#popup-course .popup-state-partial").is_visible()
    assert page.locator("#popup-course-results .popup-post").count() == 1
    load(page, visit_date="2026-11-25")
    retry = page.locator("#popup-course .popup-state-error button")
    asked = len(api.requests)
    retry.click()
    idle(page)
    assert len(api.requests) == asked + 1 and api.requests[-1]["visit_date"] == "2026-11-25"
    assert "코스 추천에는 영향이 없어요" in page.locator("#popup-course-status").inner_text()
    load(page, visit_date="2026-11-26")
    assert page.locator("#popup-course .popup-state-key").is_visible()
    assert page.locator("#popup-course .popup-state-key button").count() == 0
    load(page, visit_date="2026-11-27")
    assert "새 팝업 검색이 많아요" in page.locator("#popup-course .popup-state-error").inner_text()
    # 페이지를 연 뒤 스위치가 꺼지면(404) 구역을 내린다.
    load(page, visit_date="2026-11-28")
    assert section.is_hidden()
    # 구역을 내리면 코스 제목 옆 '팝업스토어 보기' 단추도 숨는다.
    assert page.locator("#popup-jump").is_hidden()


def test_late_success_error_and_loading_end_are_ignored(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    api.hold = {"2026-11-20", "2026-11-21"}
    api.by_day["2026-11-22"] = (200, payload(posts=[post(9, title="빠른 응답 글", place=BUILDING)]))
    # 취소(AbortController)만 믿지 않는지 보려고 취소를 끈다. 늦은 응답은 generation 으로만 버려져야 한다.
    page.evaluate("AbortController.prototype.abort=function(){}")
    page.evaluate("c=>{showPlannerPage(true,false);PopupCourse.load(c)}", CONDITIONS)
    page.wait_for_function(
        "()=>document.querySelector('#popup-course-results').getAttribute('aria-busy')==='true'"
    )
    load(page, visit_date="2026-11-22")
    assert titles(page) == ["빠른 응답 글"]
    # 늦은 성공: 화면·카드를 바꾸지 않는다.
    api.held.pop("2026-11-20").fulfill(
        status=200, content_type="application/json", body=json.dumps(COURSE)
    )
    page.wait_for_timeout(300)
    assert titles(page) == ["빠른 응답 글"]
    # 진행 중인 새 요청이 있을 때 늦은 오류·로딩 끝은 그 요청의 로딩 표시를 끄지 않는다.
    page.evaluate("c=>PopupCourse.load(c)", CONDITIONS | dict(visit_date="2026-11-21"))
    page.wait_for_function(
        "()=>document.querySelector('#popup-course-results').getAttribute('aria-busy')==='true'"
    )
    page.evaluate("c=>PopupCourse.load(c)", CONDITIONS | dict(visit_date="2026-11-20"))
    api.held.pop("2026-11-21").fulfill(
        status=500, content_type="application/json", body='{"detail":"늦은 오류"}'
    )
    page.wait_for_timeout(300)
    assert page.locator("#popup-course .popup-state-error").count() == 0
    assert page.locator("#popup-course-results").get_attribute("aria-busy") == "true"
    api.held.pop("2026-11-20").fulfill(
        status=200, content_type="application/json", body=json.dumps(COURSE)
    )
    idle(page)
    assert [h["name"] for h in hubs(page)] == ["성수 일대(대략)", "롯데월드몰", "더현대 서울"]


def test_popup_button_changes_only_the_origin_and_reverts(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    first = course_request(page)
    generate(page)
    page.wait_for_selector("#popup-course .popup-post")
    original = first[-1]
    assert api.requests[-1] == dict(region="서울", visit_date="2026-10-24")
    submitted = plan_jobs(page)
    # 코스를 찾는 중에는 막고 안내한다.
    page.evaluate("document.querySelector('#submit-plan').disabled=true")
    hub(page, "더현대 서울 올기 팝업").get_by_role("button").click()
    assert page.locator("#toast").inner_text() == "코스를 찾는 중이에요. 끝난 뒤 다시 눌러 주세요."
    page.evaluate("document.querySelector('#submit-plan').disabled=false")
    assert submitted == []
    hub(page, "더현대 서울 올기 팝업").get_by_role(
        "button", name="이 장소 주변 코스 추천받기", exact=True
    ).click()
    sent = submitted_after(page, submitted, 1)
    # 출발지(와 시·도)만 거점으로. 데모 코스였으므로 실제 장소로 바뀐다. festival 은 싣지 않는다.
    assert sent["origin"] == dict(name="서울 영등포구 · 더현대 서울 주변", lat=37.526, lon=126.928)
    assert sent["mode"] == "real" and sent["region"] == "서울" and sent["festival"] is None
    assert {k: sent[k] for k in KEPT} == {k: original[k] for k in KEPT}
    assert sent["visit_date"] == "2026-10-24"
    note = page.locator("#popup-origin-note")
    assert note.is_visible() and "‘더현대 서울’ 주변 기준 코스" in note.inner_text()
    assert "가상 장소 데모 대신 실제 장소로" in note.inner_text()
    assert page.locator("#festival-origin-note").is_hidden()
    # 다시 그린 구역: 고른 거점 묶음은 출발 기준이라 거리·버튼 대신 안내, 다른 묶음은 새 출발지 기준 거리.
    idle(page)
    chosen = hub(page, "더현대 서울 올기 팝업")
    assert "지금 코스는 ‘더현대 서울’ 주변에서 출발해요." in chosen.inner_text()
    assert chosen.locator("button").count() == 0 and chosen.locator(".popup-distance").count() == 0
    assert titles(page)[0] == "더현대 서울 올기 팝업"
    assert distances(page)[1:] == [
        "출발지에서 직선거리 약 11km · 성수 일대 기준",
        "출발지에서 직선거리 약 15km",
    ]
    # 다른 거점(동네)으로 바꿔 골라도 되돌릴 출발지는 처음 것.
    hub(page, "성수 일대(대략)").get_by_role(
        "button", name="이 일대 주변 코스 추천받기", exact=True
    ).click()
    sent = submitted_after(page, submitted, 2)
    assert sent["origin"]["name"] == "서울 성동구 성수역 · 성수 일대(대략) 주변"
    assert sent["festival"] is None and sent["visit_date"] == "2026-10-24"
    assert "‘성수 일대(대략)’ 주변 기준 코스" in note.inner_text()
    note.get_by_role("button", name="원래 출발지로 다시 추천", exact=True).click()
    restored = submitted_after(page, submitted, 3)
    assert restored["mode"] == "demo" and restored["origin"] == original["origin"]
    assert restored["festival"] is None and restored["visit_date"] == "2026-10-24"
    assert note.is_hidden() and page.evaluate("PopupCourse.chosen") is None


def test_festival_and_popup_choices_do_not_tangle(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    Api(page)
    first = course_request(page)
    generate(page)
    original = first[-1]
    page.wait_for_selector("#popup-course .popup-post")
    page.wait_for_function(
        'document.querySelectorAll("#festival-results .festival-card").length===3'
    )
    submitted = plan_jobs(page)
    festival_note = page.locator("#festival-origin-note")
    popup_note = page.locator("#popup-origin-note")
    popup_button = hub(page, "더현대 서울 올기 팝업").get_by_role("button")
    # 축제를 고른 뒤 팝업 버튼: 축제 기준이 풀리고 팝업 안내만 남는다.
    page.locator("#festival-results .festival-card").nth(0).get_by_role(
        "button", name="이 축제 주변 코스 추천받기", exact=True
    ).click()
    festival_sent = submitted_after(page, submitted, 1)
    assert festival_sent["festival"]["id"] == "201"
    assert festival_note.is_visible() and popup_note.is_hidden()
    idle(page)
    popup_button.click()
    sent = submitted_after(page, submitted, 2)
    assert sent["festival"] is None and sent["origin"]["name"] == "서울 영등포구 · 더현대 서울 주변"
    # 축제 버튼은 방문일을 축제 기간 안으로 옮긴다(기존 동작). 팝업 버튼은 그 방문일을 다시 옮기지 않는다.
    assert sent["visit_date"] == festival_sent["visit_date"]
    assert {k: sent[k] for k in KEPT} == {k: festival_sent[k] for k in KEPT}
    assert festival_note.is_hidden() and popup_note.is_visible()
    assert page.locator("#festival-results .festival-card .tag").count() == 0
    # 되돌리면 축제를 고르기 전 출발지(데모)로. 축제 기준은 되살리지 않는다.
    popup_note.get_by_role("button", name="원래 출발지로 다시 추천", exact=True).click()
    restored = submitted_after(page, submitted, 3)
    assert restored["mode"] == "demo" and restored["origin"] == original["origin"]
    assert restored["festival"] is None
    assert festival_note.is_hidden() and popup_note.is_hidden()
    # 팝업을 고른 뒤 축제 버튼: 팝업 안내가 사라지고 축제 안내만 남는다.
    idle(page)
    popup_button.click()
    submitted_after(page, submitted, 4)
    page.wait_for_function(
        'document.querySelectorAll("#festival-results .festival-card").length===3'
    )
    # 실제 출발지가 생겨 축제가 거리순으로 바뀌므로 이름으로 찾는다.
    page.locator("#festival-results .festival-card").filter(has_text="점검 등불축제").get_by_role(
        "button", name="이 축제 주변 코스 추천받기", exact=True
    ).click()
    sent = submitted_after(page, submitted, 5)
    assert sent["festival"]["id"] == "201"
    assert festival_note.is_visible() and popup_note.is_hidden()
    assert page.evaluate("PopupCourse.chosen") is None


def test_saved_course_resumed_search_and_shared_page(audit_page):
    page, base, errors = audit_page
    api = Api(page)
    with TestClient(app) as client:
        plan = saved_plan(client)
        owner = client.cookies["dm_session"]
        token = client.post("/api/plans/" + plan["id"] + "/shares").json()["url"]
    page.context.add_cookies([{"name": "dm_session", "value": owner, "url": base}])
    # 저장된 코스 다시 열기: 그 코스의 지역·방문일로 구역을 그리고, 팝업 거점 안내는 없다.
    page.goto(base + "/?plan=" + plan["id"])
    page.wait_for_function("(id)=>selected?.id===id", arg=plan["id"])
    page.wait_for_selector("#popup-course .popup-post")
    assert api.requests[-1] == dict(region="서울", visit_date="2026-10-24")
    assert page.locator("#popup-course").is_visible()
    assert page.locator("#popup-origin-note").is_hidden()
    # 새로고침으로 이어받은 검색: 출발지가 없는 조건이라 거리 없이 보인다.
    page.goto(base + "/")
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData")

    def still_running(route):
        if route.request.method != "GET":
            return route.continue_()
        route.fulfill(json=dict(id="x", status="running", stage="코스 탐색", message="찾는 중"))

    page.route("**/api/plan-jobs/*", still_running)
    generate_started = page.evaluate(
        "form.elements.mode.value='demo';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));"
        "form.elements.visit_date.value='2026-10-24';form.elements.max_leg.value=180;form.elements.budget.value=1000000;"
        "document.querySelector('#submit-plan').click();true"
    )
    assert generate_started
    page.wait_for_function('!!sessionStorage.getItem("datemate-active-search")')
    before = len(api.requests)
    page.reload()
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData")
    page.wait_for_selector("#popup-course .popup-post")
    assert len(api.requests) > before and api.requests[-1]["visit_date"] == "2026-10-24"
    assert page.locator(".popup-distance").count() == 0
    page.evaluate("PlanSearch.generation++;PlanSearch.controller?.abort()")
    # 공유 화면에는 구역이 없고 팝업을 부르지 않는다.
    before = len(api.requests)
    page.goto(base + token)
    page.wait_for_function('document.querySelectorAll("#shared-places article").length===2')
    assert page.locator("#popup-course").count() == 0 and page.locator(".popup-post").count() == 0
    page.wait_for_timeout(300)
    assert len(api.requests) == before


def test_popup_failure_keeps_course_festivals_and_map(audit_page):
    page, base, errors = audit_page
    route_festivals(page)
    Api(page, default=None).default = (500, {"detail": "점검용 연결 실패"})
    generate(page)
    assert page.locator("#results .plan-card").count() >= 1
    assert "추천 완료" in page.locator("#progress").inner_text()
    page.wait_for_function(
        'document.querySelectorAll("#festival-results .festival-card").length===3'
    )
    assert page.locator(".plan-map").count() >= 1
    page.wait_for_selector("#popup-course .popup-state-error")
    assert "코스 추천에는 영향이 없어요" in page.locator("#popup-course-status").inner_text()
    # 코스 탭 이동도 그대로.
    page.locator(".plan-option-tabs button").nth(1).click()
    page.wait_for_function(
        'document.querySelector(".plan-option-tabs button:nth-child(2)").getAttribute("aria-pressed")==="true"'
    )
    wait_for_selected_detail(page)


def test_switch_off_draws_no_course_section(audit_page, monkeypatch):
    page, base, errors = audit_page
    api = Api(page)
    monkeypatch.setenv("DATEMATE_POPUPS_ENABLED", "0")
    main._status_cache.update(value=None, expires=0)
    page.goto(base + "/?switch=off", wait_until="networkidle")
    page.wait_for_function(
        "typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')"
    )
    generate(page)
    assert page.locator("#popup-course").count() == 0
    assert page.locator("#popup-origin-note").count() == 0
    assert api.requests == []
    main._status_cache.update(value=None, expires=0)


def test_four_widths_long_names_touch_targets_and_keyboard(audit_page):
    page, base, errors = audit_page
    long_hub = BUILDING | dict(
        name="롯데백화점 본점 에비뉴엘 월드타워 SUPERLONGHUBNAMEWITHOUTSPACESFORTESTING 지하 1층 행사장",
        district="중구",
    )
    rows = [
        post(
            i,
            title=LONG_TITLE + f" {i}",
            blogger="아주아주긴블로그이름SUPERLONGBLOGGERNAMEWITHOUTSPACES의 데이트 기록장",
            period=CONFIRMED if i % 2 else UPCOMING,
            place=long_hub if i % 2 else AREA,
        )
        for i in range(8)
    ] + [post(40, title=LONG_TITLE, place=UNVERIFIED)]
    Api(page, default=payload(posts=rows))
    generate(page)
    page.wait_for_selector("#popup-course .popup-post")

    def expand():
        while page.locator("#popup-course-results .popup-hub-more").count():
            page.locator("#popup-course-results .popup-hub-more").first.click()
        page.locator(".popup-unknown-toggle").click()

    expand()
    assert page.locator("#popup-course .popup-post").count() == 9
    # 고른 거점 안내도 긴 이름으로 본다(요청은 503 으로 끝냄).
    plan_jobs(page)
    hub(page, "에비뉴엘").get_by_role("button").click()
    page.wait_for_function('!document.querySelector("#submit-plan").disabled')
    idle(page)
    expand()
    assert page.locator("#popup-origin-note").is_visible()
    for width in (320, 390, 768, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
        check = page.evaluate(
            """() => {
              const area=[document.querySelector('#popup-course'),document.querySelector('#popup-origin-note')];
              const all=s=>area.flatMap(a=>[...a.querySelectorAll(s)]).filter(e=>e.getClientRects().length);
              const small=all('p,dt,dd,h3,h4,h5,h6,a,button,strong,span').filter(e=>e.textContent.trim()&&parseFloat(getComputedStyle(e).fontSize)<14)
                .map(e=>e.className+':'+getComputedStyle(e).fontSize);
              const short=all('button,.popup-source-link').filter(e=>e.getBoundingClientRect().height<44).map(e=>e.textContent.trim());
              const clipped=all('.popup-title,.popup-summary,.popup-hub-name,.popup-fact dd,.popup-meta,.popup-action-note,.popup-origin-title,button')
                .filter(e=>e.scrollWidth>e.clientWidth+1||getComputedStyle(e).textOverflow==='ellipsis'||getComputedStyle(e).webkitLineClamp!=='none')
                .map(e=>e.textContent.slice(0,20));
              const outside=all('.popup-hub,.popup-post,.popup-origin-note button').filter(e=>{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth;}).length;
              return {small,short,clipped,outside};
            }"""
        )
        assert check == dict(small=[], short=[], clipped=[], outside=0), (width, check)
    note = page.locator("#popup-origin-note").inner_text()
    assert "SUPERLONGHUBNAMEWITHOUTSPACESFORTESTING 지하 1층 행사장’ 주변 기준 코스" in note
    period = page.locator("#popup-course .popup-period dd").first.inner_text()
    # 날짜·상태 글자가 잘리지 않고 끝까지 있다(위 clipped 검사와 함께).
    assert period == "2026.10.20 ~ 2026.11.16 · 오늘 기준 진행 중 · 원문 확인"
    # 키보드로 주변 코스 버튼·접기 버튼·출처 링크에 닿고 포커스 표시가 보인다.
    for selector in (
        "#popup-course .popup-action button",
        ".popup-unknown-toggle",
        "#popup-course .popup-source-link",
        "#popup-origin-note button",
    ):
        page.locator(selector).first.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        assert page.evaluate("s=>document.activeElement===document.querySelector(s)", selector), (
            selector
        )
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"


def test_popup_jump_sits_next_to_the_festival_jump_and_moves_to_the_popup_section(audit_page):
    page, base, errors = audit_page
    Api(page)
    load(page)
    jump = page.locator("#popup-jump")
    assert jump.is_visible()
    count = page.locator("#popup-course-results .popup-post").count() or None
    text = jump.inner_text()
    assert text.startswith("서울 팝업스토어") and text.endswith("보기 ↓"), text
    # 축제 보기 단추 바로 옆(같은 제목 줄).
    assert page.evaluate("document.getElementById('festival-jump').nextElementSibling.id") == "popup-jump"
    page.emulate_media(reduced_motion="reduce")  # 부드러운 스크롤 중간 위치를 재지 않게
    jump.click()
    page.wait_for_function("document.activeElement?.id==='popup-course-title'")
    # 팝업 구역이 페이지 끝 가까이에 있으면 맨 위까지 올라가지 못하므로, 제목이 화면 안에 들어왔는지를 본다.
    seen = page.evaluate("""()=>{const r=document.getElementById('popup-course-title').getBoundingClientRect();
      return r.top>=0&&r.bottom<=innerHeight;}""")
    assert seen, count
