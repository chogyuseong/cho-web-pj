"""GET /api/popups (1단계 1a). 네이버 검색 호출은 popup_api.observed_http 를 바꿔 끼워 흉내 낸다(외부 호출 없음)."""

import threading
import time
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, popup_api, store, web_security
from app.main import app

TODAY = date(2026, 11, 14)


def item(title, description="", link=None, postdate="20261114", blogger="블로거"):
    return dict(
        title=title,
        description=description,
        link=link or f"https://blog.naver.com/test/{abs(hash(title)) % 10**9}",
        postdate=postdate,
        bloggername=blogger,
    )


def local(title, address, lon, lat, category="쇼핑,유통>백화점"):
    return dict(
        title=title,
        roadAddress=address,
        category=category,
        mapx=str(int(lon * 1e7)),
        mapy=str(int(lat * 1e7)),
    )


LOCALS = {
    "더현대 서울": [
        local("현대백화점 더현대 서울", "서울특별시 영등포구 여의대로 108", 126.9284, 37.5260)
    ],
    "성수역 2호선": [
        local(
            "성수역 2호선", "서울특별시 성동구 아차산로 100", 127.0560, 37.5446, "교통,수송>지하철"
        ),
    ],
    "용산 아이파크몰": [
        local("용산 아이파크몰", "서울특별시 용산구 한강대로23길 55", 126.9647, 37.5298),
    ],
    "신세계백화점 강남점": [
        local("신세계백화점 강남점", "서울특별시 서초구 신반포로 176", 127.0040, 37.5048),
    ],
}

BLOG = [
    item(
        "더현대 서울 <b>올기</b> 팝업 &amp; 후기",
        "팝업 운영 정보 - 장소 : 더현대 서울 기간 2026.10.20~2026.11.16",
        "https://blog.naver.com/a/1",
        "20261113",
    ),
    item("성수 짱구 팝업스토어", "성수동 팝업 운영 11.14~11.30", "https://blog.naver.com/a/2"),
    item(
        "포켓몬 고풍상점 팝업 정리",
        "2026년 9월 18일부터 10월 11일까지 운영된 팝업스토어",
        "https://blog.naver.com/a/3",
    ),
    item(
        "더현대 대구 크리스마스 팝업",
        "더현대 서울 이랑은 차원이 다르게",
        "https://blog.naver.com/a/4",
    ),
    item("11월 성수 팝업스토어 총정리 10곳", "성수 팝업 모음", "https://blog.naver.com/a/5"),
    item("동네 빵집 후기", "팝업 아님", "https://blog.naver.com/a/6"),
    item("동네 카페 후기", "맛있어요", "https://blog.naver.com/a/7"),
    item("위험한 링크 팝업", "", "javascript:alert(1)"),
    item("모바일 주소 중복 팝업", "", "https://m.blog.naver.com/a/2/"),
    item("팝업 위치 모름", "어디인지 안 적힌 팝업 후기", "https://blog.naver.com/a/8", "20261112"),
]


class Fake:
    """observed_http 대역: 경로별 응답(또는 예외)을 돌려주고 부른 횟수를 센다."""

    def __init__(self, blog=None, locals_=None):
        self.blog = BLOG if blog is None else blog
        self.locals = LOCALS if locals_ is None else locals_
        self.calls = []
        self.blog_error = None
        self.local_error = None
        self.delay = 0

    def __call__(self, call, url, params=None, headers=None, **kwargs):
        kind = url.rsplit("/", 1)[-1]
        self.calls.append((kind, params["query"]))
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "fake-id"
        if self.delay:
            time.sleep(self.delay)
        request = httpx.Request("GET", url)
        error = self.blog_error if kind == "blog" else self.local_error
        if isinstance(error, Exception):
            raise error
        if isinstance(error, int):
            return httpx.Response(error, json={"errorMessage": "x"}, request=request)
        if error == "bad_json":
            return httpx.Response(200, content=b"<html>", request=request)
        if kind == "blog":
            return httpx.Response(200, json={"items": self.blog, "total": 999}, request=request)
        return httpx.Response(
            200, json={"items": self.locals.get(params["query"], [])}, request=request
        )

    def count(self, kind):
        return sum(1 for k, _ in self.calls if k == kind)


@pytest.fixture
def fake(monkeypatch):
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key LIKE 'popup%'")
        db.execute(
            "DELETE FROM request_budgets WHERE scope LIKE 'popups:%' OR scope LIKE 'ip:popup-search:%'"
        )
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_ID", "fake-id")
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_SECRET", "fake-secret")
    monkeypatch.setattr(popup_api, "today", lambda: TODAY)
    f = Fake()
    monkeypatch.setattr(popup_api, "observed_http", f)
    return f


def get(client, **params):
    return client.get("/api/popups", params=dict(region="서울") | params)


def test_posts_are_source_items_with_reading_kept_apart(fake):
    data = get(TestClient(app)).json()
    assert (
        data["status"] == "ready"
        and data["basis"] == "today"
        and data["visit_date"] == "2026-11-14"
    )
    assert data["attribution"] == "네이버 블로그 검색 결과"
    assert (
        data["sources"][0]["query"] == "2026년 11월 서울 팝업스토어"
        and data["sources"][0]["cached"] is False
    )
    posts = {p["url"]: p for p in data["posts"]}
    olgi = posts["https://blog.naver.com/a/1"]
    # 제목·요약은 태그·엔티티만 텍스트로 바뀌고 내용은 그대로.
    assert olgi["title"] == "더현대 서울 올기 팝업 & 후기"
    assert olgi["description"].startswith("팝업 운영 정보 - 장소 : 더현대 서울")
    assert olgi["blogger"] == "블로거" and olgi["posted_at"] == "2026-11-13"
    assert olgi["period"] == dict(
        level="confirmed",
        start="2026-10-20",
        end="2026-11-16",
        evidence=["2026.10.20~2026.11.16"],
        status="ongoing",
        end_only=False,
    )
    assert olgi["place"]["hub_id"] == "seoul-thehyundai" and olgi["place"]["level"] == "building"
    assert abs(olgi["place"]["lat"] - 37.526) < 1e-3
    seongsu = posts["https://blog.naver.com/a/2"]
    assert seongsu["period"]["level"] == "month_day" and seongsu["period"]["start"] is None
    assert (
        seongsu["period"]["evidence"] == ["11.14~11.30"]
        and seongsu["period"]["status"] == "unknown"
    )
    assert seongsu["place"]["level"] == "area_anchor" and seongsu["place"]["anchor"] == "성수역"
    # 주변 코스 버튼이 출발지 이름에 쓰는 시·군·구(1b).
    assert olgi["place"]["district"] == "영등포구" and seongsu["place"]["district"] == "성동구"
    unknown = posts["https://blog.naver.com/a/8"]
    assert unknown["place"] == dict(hub_id=None, level="unverified", reason="not_found")
    assert "lat" not in unknown["place"]
    # 출처 하나 = 항목 하나: 행사명·묶기 필드가 없다.
    assert not {"name", "event_name", "cards", "group"} & set(olgi)
    assert posts["https://blog.naver.com/a/5"]["roundup"] is True
    # 종료로 확정된 글은 숨기고, 다른 지역 거점 글은 빼고, 수를 남긴다. 위험한 URL·중복 URL·팝업 아닌 글은 없다.
    # 규칙 v2: 요약에 '팝업' 한 마디만 있고 기간·거점이 없는 /a/6 도 팝업 아닌 글로 센다('팝업' 없는 /a/7 과 함께).
    counts = data["counts"]
    assert counts["hidden_ended"] == 1 and counts["excluded_other_region"] == 1
    assert counts["not_popup"] == 2 and counts["shown"] == 4 and counts["roundup"] == 1
    assert all(p["url"].startswith("https://blog.naver.com/a/") for p in data["posts"])
    # 결정적 정렬: 일반 글 중 거점을 읽은 글(최근 글 먼저) → 위치 미확인 글 → 모아 보기 글.
    assert [p["url"].rsplit("/", 1)[-1] for p in data["posts"]] == ["2", "1", "8", "5"]
    assert len({p["id"] for p in data["posts"]}) == 4
    assert all(p["id"].startswith("popup-post:") for p in data["posts"])
    # 블로그 1 + 좌표 2(더현대 서울, 성수 일대).
    assert fake.count("blog") == 1 and fake.count("local") == 2


def test_referral_post_with_a_screen_popup_is_not_shown(fake):
    """사용자가 본 사례: 앱 추천코드 글의 '메인 팝업'(앱 화면)만으로 팝업 글이 되지 않는다(규칙 v2)."""
    fake.blog = [
        item(
            "KFC 둠스데이 친구 초대 이벤트 참여 방법 및 <b>추천코드</b> Qa1vX 혜택 총정리",
            "초대 보상 쿠폰은 추천 코드를 통한 회원가입이 발생할 때 메인 <b>팝업</b>을 통해 즉시 지급되지만",
            "https://blog.naver.com/a/kfc",
        ),
        item(
            "르비크 팝업스토어 쿠폰 증정",
            "팝업스토어에서 구매하면 할인 쿠폰 증정",
            "https://blog.naver.com/a/coupon",
        ),
    ]
    data = get(TestClient(app)).json()
    assert [p["url"] for p in data["posts"]] == ["https://blog.naver.com/a/coupon"]
    assert data["counts"]["not_popup"] == 1 and data["counts"]["shown"] == 1
    assert data["rules_version"] == "popups-rules-v4"


def test_off_topic_vendor_and_other_region_title_posts_are_counted_apart(fake):
    """규칙 v3: 지나가는 언급(거점 낱말만 있음)·업체 글은 not_popup, 제목이 다른 시·도 팝업인 글은 other_region."""
    fake.blog = [
        item(
            "성수 칼국수맛집 웨이팅 후기",
            "성수동 위치... 근처 <b>팝업스토어</b> 를 구경하다가 방문했습니다",
            "https://blog.naver.com/a/noodle",
        ),
        item(
            "크리스마스 <b>팝업스토어</b> 화물 운송, 야간 반입",
            "",
            "https://blog.naver.com/a/cargo",
        ),
        item(
            "부산 <b>팝업스토어</b> 7곳 11월 말 일정",
            "공식 공지와 언론 보도를 모은 정보 글",
            "https://blog.naver.com/a/busan",
        ),
        item(
            "올기 찹쌀떡 가격 더현대 서울 웨이팅",
            "#올기 <b>팝업</b> #더현대 서울팝업",
            "https://blog.naver.com/a/olgi",
        ),
    ]
    data = get(TestClient(app)).json()
    assert [p["url"] for p in data["posts"]] == ["https://blog.naver.com/a/olgi"]
    counts = data["counts"]
    assert counts["not_popup"] == 2 and counts["excluded_other_region"] == 1


def test_cache_is_reused_and_status_is_recomputed_for_each_visit_date(fake):
    client = TestClient(app)
    first = get(client).json()
    again = get(client, visit_date="2026-11-17").json()
    assert fake.count("blog") == 1 and fake.count("local") == 2
    assert again["sources"][0]["cached"] is True and again["basis"] == "visit_date"
    ids = lambda d: [p["id"] for p in d["posts"]]  # noqa: E731
    # 11-17 에는 올기(~11-16)가 종료라 숨는다. 같은 캐시라도 날짜마다 다시 판정한다.
    assert "https://blog.naver.com/a/1" not in [p["url"] for p in again["posts"]]
    assert again["counts"]["hidden_ended"] == 2
    # 다른 달의 방문일은 검색어의 연·월이 달라 새로 검색한다.
    earlier = get(client, visit_date="2026-10-19").json()
    assert earlier["sources"][0]["cached"] is False
    assert ("blog", "2026년 10월 서울 팝업스토어") in fake.calls and fake.count("blog") == 2
    olgi = next(p for p in earlier["posts"] if p["url"].endswith("/a/1"))
    assert olgi["period"]["status"] == "upcoming"
    assert ids(get(client).json()) == ids(first)  # 같은 입력, 같은 순서
    # 검색어가 바뀌면 다른 캐시 키. 지역명이 앞에 붙어 있어도 같은 검색으로 본다.
    assert get(client, q="  성수​ ").json()["q"] == "성수"
    assert get(client, q="서울 성수").json()["sources"][0]["cached"] is True
    assert fake.count("blog") == 3 and ("blog", "2026년 11월 서울 성수 팝업스토어") in fake.calls


def test_invalid_inputs(fake):
    client = TestClient(app)
    assert get(client, region="도쿄").status_code == 422
    assert get(client, q="가" * 31).status_code == 422
    assert get(client, q="가" * 30).status_code == 200
    assert get(client, visit_date="2026-13-01").status_code == 422
    assert get(client, visit_date="2026-10-01").status_code == 422  # 31일보다 전
    assert get(client, visit_date="2027-11-20").status_code == 422
    assert client.get("/api/popups", params=dict(region="부산광역시")).json()["region"] == "부산"


def test_missing_key_is_reported_without_calls(fake, monkeypatch):
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_ID", "")
    data = get(TestClient(app), q="키없음").json()
    assert data["status"] == "key_missing" and data["posts"] == [] and fake.calls == []
    assert data["sources"][0]["status"] == "key_missing"


@pytest.mark.parametrize(
    "error,reason",
    [
        (429, "rate_limited"),
        (401, "permission"),
        (httpx.ReadTimeout("slow"), "timeout"),
        ("bad_json", "invalid_response"),
    ],
)
def test_provider_failures_are_unavailable_and_not_cached(fake, error, reason):
    client = TestClient(app)
    fake.blog_error = error
    data = get(client).json()
    assert data["status"] == "unavailable" and data["posts"] == []
    assert data["sources"][0]["reason"] == reason and data["sources"][0]["status"] == "failed"
    fake.blog_error = None
    assert get(client).json()["status"] == "ready"
    assert fake.count("blog") == 2  # 실패는 캐시하지 않아 다음 요청이 다시 부른다


def test_empty_result_differs_from_failure_and_is_kept_briefly(fake, monkeypatch):
    fake.blog = [item("동네 카페 후기", "맛있어요")]
    saved = []
    real = store.cache
    monkeypatch.setattr(
        store, "cache", lambda k, v, ttl=86400: (saved.append((k, ttl)), real(k, v, ttl))
    )
    data = get(TestClient(app)).json()
    assert data["status"] == "empty" and data["message"] and data["sources"][0]["status"] == "ok"
    assert [ttl for k, ttl in saved if k.startswith("popups-raw:")] == [popup_api.EMPTY_TTL]
    saved.clear()
    fake.blog = BLOG
    get(TestClient(app), q="정상")
    assert [ttl for k, ttl in saved if k.startswith("popups-raw:")] == [popup_api.RAW_TTL]
    assert [ttl for k, ttl in saved if k.startswith("popup-hub-point:")] == [7 * 86400] * 2


def test_external_calls_per_request_are_capped_and_point_failures_are_partial(fake):
    fake.blog = [
        item(f"{name} 팝업", "", f"https://blog.naver.com/c/{i}")
        for i, name in enumerate(
            ["더현대 서울", "성수동", "용산 아이파크몰", "신세계백화점 강남점", "롯데월드몰"]
        )
    ]
    client = TestClient(app)
    data = get(client).json()
    assert fake.count("blog") == 1 and fake.count("local") == popup_api.MAX_POINT_LOOKUPS == 3
    assert data["hub_checks"] == dict(requested=3, failed=0, skipped=2)
    reasons = sorted(p["place"]["reason"] for p in data["posts"])
    assert reasons.count("not_checked") == 2 and data["status"] == "ready"
    # 다음 요청은 캐시된 3곳은 다시 부르지 않고 남은 2곳만 확인한다. 실패는 partial 이고 캐시하지 않는다.
    fake.local_error = httpx.ConnectError("down")
    second = get(client).json()
    assert fake.count("blog") == 1 and fake.count("local") == 5
    assert second["status"] == "partial" and second["hub_checks"]["failed"] == 2
    assert {p["place"]["reason"] for p in second["posts"]} >= {"lookup_failed", "verified"}
    fake.local_error = None
    assert get(client).json()["status"] == "ready" and fake.count("local") == 7


def test_same_search_at_once_calls_the_provider_once(fake):
    fake.delay = 0.3
    results = []

    def run():
        results.append(popup_api.find_popups("서울", "동시", TODAY, "today")["status"])

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake.count("blog") == 1 and results == ["ready"] * 3


def test_new_searches_have_their_own_ip_limits(fake, monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("DATEMATE_IP_POPUP_SEARCHES_PER_MINUTE", "1")
    assert get(client, q="한도1").status_code == 200
    # 캐시로 답하는 요청은 한도를 쓰지 않는다.
    assert get(client, q="한도1").status_code == 200
    blocked = get(client, q="한도2")
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "60"
    monkeypatch.setenv("DATEMATE_IP_POPUP_SEARCHES_PER_MINUTE", "100")
    monkeypatch.setenv("DATEMATE_IP_POPUP_SEARCHES_PER_HOUR", "2")
    assert get(client, q="한도3").status_code == 200
    hourly = get(client, q="한도4")
    assert hourly.status_code == 429 and hourly.headers["Retry-After"] == "3600"
    # 시간 한도는 유지보수가 분 단위로 지우는 'ip:' 범위가 아니다.
    with store.connect() as db:
        scopes = [r[0] for r in db.execute("SELECT scope FROM request_budgets").fetchall()]
    assert any(s.startswith("popups:hour:") for s in scopes)
    assert fake.count("blog") == 2


def test_route_is_registered_as_expensive():
    assert any(p.match("GET /api/popups") for p in web_security.EXPENSIVE)


def test_switch_off_hides_the_api_and_tells_the_page(fake, monkeypatch):
    monkeypatch.setenv("DATEMATE_POPUPS_ENABLED", "0")
    main._status_cache.update(value=None, expires=0)
    client = TestClient(app)
    assert get(client).status_code == 404 and fake.calls == []
    assert client.get("/api/status").json()["popups_enabled"] is False
    monkeypatch.delenv("DATEMATE_POPUPS_ENABLED")
    main._status_cache.update(value=None, expires=0)
    assert client.get("/api/status").json()["popups_enabled"] is True
