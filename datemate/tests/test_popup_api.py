"""GET /api/popups: 네이버 블로그 검색 결과를 받은 그대로 + 우리 거점 사전(2026-11-20, 특약 2.2).

네이버 검색 호출은 popup_api.observed_http 를 바꿔 끼워 흉내 낸다(외부 호출 없음).
무엇을 고정하는가: 검색 한 번, 받은 순서·건수 그대로, 제목·요약 원문 그대로, 글에서 읽은 판정 필드 없음,
이미지·지역 검색을 부르지 않음, 거점 사전은 검색 결과와 무관.
"""

import contextvars
import inspect
import threading
import time
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, popup_api, popup_hubs, store, web_security
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


LONG = "아주 긴 요약 " * 60

# 예전 규칙이 고르고(팝업 아님·다른 지역·종료), 나누고(모아 보기), 다시 줄 세우던 글들. 이제는 받은 순서 그대로 모두 나와야 한다.
BLOG = [
    item("동네 카페 후기", "맛있어요", "https://blog.naver.com/a/7"),
    item("11월 성수 팝업스토어 총정리 10곳", "성수 팝업 모음", "https://blog.naver.com/a/5"),
    item(
        "더현대 서울 <b>올기</b> 팝업 &amp; 후기",
        "팝업 운영 정보 - 장소 : 더현대 서울 기간 2026.10.20~2026.11.16",
        "https://blog.naver.com/a/1",
        "20261113",
    ),
    item("부산 팝업스토어 7곳 11월 말 일정", "더현대 대구 크리스마스 팝업", "https://blog.naver.com/a/4"),
    item(
        "포켓몬 고풍상점 팝업 정리",
        "2026년 9월 18일부터 10월 11일까지 운영된 팝업스토어",
        "https://blog.naver.com/a/3",
    ),
    item("위험한 링크 팝업", "", "javascript:alert(1)"),
    item("같은 글 모바일 주소", LONG, "https://m.blog.naver.com/a/1/", "20261101", ""),
    item("같은 주소가 두 번", "", "https://blog.naver.com/a/5", "날짜아님"),
]
SAFE_URLS = [i["link"] for i in BLOG if i["link"].startswith("https://")]


class Fake:
    """observed_http 대역: 응답(또는 예외)을 돌려주고 부른 주소·검색어를 적는다."""

    def __init__(self):
        self.blog = BLOG
        self.calls = []
        self.params = []
        self.blog_error = None
        self.delay = 0

    def __call__(self, call, url, params=None, headers=None, **kwargs):
        kind = url.rsplit("/", 1)[-1]
        self.calls.append((kind, params["query"]))
        self.params.append(params)
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "fake-id"
        if self.delay:
            time.sleep(self.delay)
        request = httpx.Request("GET", url)
        error = self.blog_error
        if isinstance(error, Exception):
            raise error
        if isinstance(error, int):
            return httpx.Response(error, json={"errorMessage": "x"}, request=request)
        if error == "bad_json":
            return httpx.Response(200, content=b"<html>", request=request)
        return httpx.Response(200, json={"items": self.blog, "total": 999}, request=request)

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


def test_posts_keep_the_order_count_and_text_naver_gave(fake):
    data = get(TestClient(app)).json()
    assert data["status"] == "ready" and data["visit_date"] == "2026-11-14"
    assert data["attribution"] == "네이버 블로그 검색 결과"
    source = data["sources"][0]
    assert source["query"] == "2026년 11월 서울 팝업스토어" and source["cached"] is False
    assert source["sort"] == "date" and source["display"] == 50 and source["returned"] == len(BLOG)
    # 검색은 한 번뿐이다(예전에는 두 검색어 결과를 합쳤다). 이미지·지역 검색은 부르지 않는다.
    assert fake.calls == [("blog", "2026년 11월 서울 팝업스토어")]
    assert fake.params[0] == dict(
        query="2026년 11월 서울 팝업스토어", display=50, start=1, sort="date", format="json"
    )
    # 받은 순서 그대로, 받은 건수 그대로. 빠지는 것은 링크를 걸 수 없는 항목(javascript:) 하나뿐이다.
    # 팝업이 아닌 글·다른 지역 글·끝난 팝업 글·모아 보기 글·같은 글의 다른 주소·같은 주소 반복도 그대로 둔다.
    assert [p["url"] for p in data["posts"]] == SAFE_URLS
    assert data["counts"] == dict(shown=len(BLOG) - 1, returned=len(BLOG))
    # 제목·요약은 태그·엔티티만 글자로 바뀌고 내용은 그대로(자르지 않음).
    olgi = data["posts"][2]
    assert olgi["title"] == "더현대 서울 올기 팝업 & 후기"
    assert olgi["description"] == "팝업 운영 정보 - 장소 : 더현대 서울 기간 2026.10.20~2026.11.16"
    assert olgi["blogger"] == "블로거" and olgi["posted_at"] == "2026-11-13"
    mobile = data["posts"][5]
    assert mobile["description"] == LONG.strip() and len(mobile["description"]) > 400
    assert mobile["blogger"] is None and data["posts"][6]["posted_at"] is None
    # 글에서 읽어 낸 값이 없다: 항목의 필드는 네이버가 준 값과 화면용 ID 뿐이다.
    for p in data["posts"]:
        assert set(p) == {"id", "title", "description", "url", "blogger", "posted_at"}
        assert p["id"].startswith("popup-post:")
    assert not {"hub_checks", "photo_checks", "rules_version", "basis"} & set(data)


def test_module_has_no_judging_image_or_local_search_left():
    source = inspect.getsource(popup_api)
    for gone in ("search/v1/image", "search/v1/local", "roundup", "period", "photo", "judge"):
        assert gone not in source, gone
    for name in ("judge", "order_key", "lookup_point", "lookup_photo", "post_photos", "merge_posts", "hub_points"):
        assert not hasattr(popup_api, name), name
    with pytest.raises(ImportError):
        from app import popups  # noqa: F401


def test_hub_dictionary_is_returned_whatever_the_search_gives(fake, monkeypatch):
    client = TestClient(app)
    seoul = get(client).json()
    expected = [h["id"] for h in popup_hubs.HUBS if h["region"] == "서울"]
    assert [h["hub_id"] for h in seoul["hubs"]] == expected and len(expected) >= 10
    hub = seoul["hubs"][0]
    assert set(hub) == {"hub_id", "name", "kind", "anchor", "region", "district", "lat", "lon"}
    assert seoul["hubs_version"] == popup_hubs.HUBS_VERSION
    assert seoul["hub_coordinates"] == dict(provider="한국관광공사 TourAPI", checked="2026-11-20")
    # 검색 결과가 달라도, 0건이어도, 검색에 실패해도, 키가 없어도 거점 목록은 같다(글과 잇지 않는다).
    fake.blog = [item("더현대 서울 팝업", "", "https://blog.naver.com/b/1")]
    assert get(client, q="하나").json()["hubs"] == seoul["hubs"]
    fake.blog = []
    empty = get(client, q="없음").json()
    assert empty["status"] == "empty" and empty["hubs"] == seoul["hubs"]
    fake.blog_error = 500
    assert get(client, q="실패").json()["hubs"] == seoul["hubs"]
    monkeypatch.setenv("NAVER_SEARCH_CLIENT_ID", "")
    assert get(client, q="키없음").json()["hubs"] == seoul["hubs"]
    # 거점이 없는 시·도는 빈 목록.
    assert client.get("/api/popups", params=dict(region="강원")).json()["hubs"] == []


def test_hub_dictionary_has_fixed_public_coordinates():
    from app.regions import REGIONS, korean_coordinates

    ids = [h["id"] for h in popup_hubs.HUBS]
    assert len(ids) == len(set(ids)) == 35
    for h in popup_hubs.HUBS:
        assert h["region"] in REGIONS and h["kind"] in ("building", "area"), h["id"]
        # 동네 거점만 기준 장소가 있다.
        assert (h["anchor"] is not None) == (h["kind"] == "area"), h["id"]
        assert korean_coordinates(h["lat"], h["lon"]), h["id"]
        src = h["source"]
        assert src["provider"] == "한국관광공사 TourAPI" and src["checked"] == "2026-11-20"
        assert src["basis"] in ("entity", "tenants") and src["ref"], h["id"]
        # 글에서 거점을 찾던 별칭·지역 검색어는 남기지 않는다.
        assert not {"aliases", "local_query", "verify", "not_followed_by"} & set(h)
    # 좌표가 없는 거점은 응답에 싣지 않는다(지도에 그리지 않음).
    blank = dict(popup_hubs.HUBS[0], id="x", lat=None, lon=None)
    original = popup_hubs.HUBS
    popup_hubs.HUBS = original + (blank,)
    try:
        assert "x" not in [h["hub_id"] for h in popup_hubs.hubs_in(blank["region"])]
    finally:
        popup_hubs.HUBS = original


def test_personal_cache_is_reused_within_the_month_and_cleared_by_a_new_search(fake):
    client = TestClient(app)
    first = get(client).json()
    again = get(client, visit_date="2026-11-17").json()
    assert fake.count("blog") == 1 and again["sources"][0]["cached"] is True
    # 같은 달의 다른 방문일은 같은 검색이라 같은 글·같은 순서다(방문일로 글을 숨기지 않는다).
    assert again["posts"] == first["posts"] and again["visit_date"] == "2026-11-17"
    # 다른 달의 방문일은 검색어의 연·월이 달라 새로 검색한다.
    earlier = get(client, visit_date="2026-10-19").json()
    assert earlier["sources"][0]["cached"] is False
    assert fake.calls[-1] == ("blog", "2026년 10월 서울 팝업스토어") and fake.count("blog") == 2
    # 새 검색은 같은 사용자의 새 질의라 이전 팝업 검색 보관분을 지운다(특약 2.4, app/naver_cache.new_query).
    assert get(client).json()["posts"] == first["posts"] and fake.count("blog") == 3
    # 검색어가 바뀌면 다른 보관 키. 지역명이 앞에 붙어 있어도 같은 검색으로 본다.
    assert get(client, q="  성수​ ").json()["q"] == "성수"
    assert get(client, q="서울 성수").json()["sources"][0]["cached"] is True
    assert fake.count("blog") == 4 and fake.calls[-1] == ("blog", "2026년 11월 서울 성수 팝업스토어")
    assert popup_api.search_query("서울", "캐릭터 팝업", TODAY) == "2026년 11월 서울 캐릭터 팝업"


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
    assert data["counts"] == dict(shown=0, returned=0)


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
    assert fake.count("blog") == 2  # 실패는 보관하지 않아 다음 요청이 다시 부른다


def test_empty_result_differs_from_failure_and_is_kept_briefly(fake, monkeypatch):
    fake.blog = []
    saved = []
    # 네이버 검색 결과는 사용자별 보관(app/naver_cache)을 거친다.
    from app import naver_cache

    real = naver_cache.cache
    monkeypatch.setattr(
        naver_cache, "cache", lambda k, v, ttl=86400: (saved.append((k, ttl)), real(k, v, ttl))
    )
    data = get(TestClient(app)).json()
    assert data["status"] == "empty" and data["message"] and data["sources"][0]["status"] == "ok"
    assert [(k.split(":")[0], ttl) for k, ttl in saved] == [("popups-raw", popup_api.EMPTY_TTL)]
    saved.clear()
    # '팝업' 글자가 없는 글뿐이어도 받은 글이 있으면 그대로 보여 주고 보통 수명으로 둔다(글을 판정하지 않는다).
    fake.blog = [item("동네 카페 후기", "맛있어요")]
    kept = get(TestClient(app), q="정상").json()
    assert kept["status"] == "ready" and len(kept["posts"]) == 1
    # 보관하는 것은 검색 결과 하나뿐이고(거점 좌표·사진 보관 없음) 사용자별 24시간을 넘지 않는다.
    assert [(k.split(":")[0], ttl) for k, ttl in saved] == [("popups-raw", popup_api.RAW_TTL)]
    assert popup_api.RAW_TTL <= naver_cache.PERSONAL_MAX_SECONDS
    assert naver_cache.purpose_of(saved[0][0]) == "popups"


def test_same_search_at_once_calls_the_provider_once(fake):
    fake.delay = 0.3
    results = []

    def run():
        results.append(popup_api.find_popups("서울", "동시", TODAY)["status"])

    # 같은 사용자(같은 소유자 문맥)의 동시 요청이다. 다른 사용자끼리는 보관분을 나누지 않아 각자 부른다(app/naver_cache).
    threads = [
        threading.Thread(target=contextvars.copy_context().run, args=(run,)) for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake.count("blog") == 1 and results == ["ready"] * 3


@pytest.mark.usefixtures("same_rate_window")
def test_new_searches_have_their_own_ip_limits(fake, monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("DATEMATE_IP_POPUP_SEARCHES_PER_MINUTE", "1")
    assert get(client, q="한도1").status_code == 200
    # 보관분으로 답하는 요청은 한도를 쓰지 않는다.
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
