"""99차(2026-11-26) '남은 것' 두 가지의 회귀 테스트.

1) 공유 화면(shared.html) 링크 미리보기: 카카오톡·메신저에 공유 링크를 붙이면 제목·설명·그림이 뜬다.
   첫 화면(QA-08)과 같은 방식 — 절대 주소는 {{PUBLIC_ORIGIN}} 자리표시를 앱(static_pages.with_public_origin)과
   Worker(cloudflare/edge.mjs withPublicOrigin)가 같은 규칙으로 바꾸고, 공개 주소가 없으면 그 태그를 뺀다.
   공유 토큰은 24시간 링크이고 미리보기는 크롤러가 가져가므로, 문구는 늘 같은 일반 문구이고 일정 내용(장소 이름 등)은 넣지 않는다.
   canonical·og:url 은 넣지 않는다: 토큰은 주소의 # 뒤(서버에 오지 않음)라 '/shared' 하나로 묶이면 미리보기 카드를 누를 때 토큰 없는 화면이 열릴 수 있다.
2) 장소 사진의 관광공사 이름 검색(tour_places._search_rows, searchKeyword2): 둘러보기 검색(QA-06, public_places.keyword_text)과 같은 규칙 —
   기호를 빼고 보내고, 두 글자 미만이면 부르지 않고, HTTP 400·사유 10(검색어 거절)은 장애가 아니라 '없음'으로 하루 보관한다.
외부 호출은 모두 가짜 응답이다(tests/public_fakes.py, httpx.MockTransport).
"""

import json
import os
import shutil
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app import media, tour_places
from app.config import ROOT
from app.main import app
from test_tour_photo_rules import HANDAM, cache_seconds, place, tour  # noqa: F401 (fixture)

ORIGIN = "https://datemate.guseong-family.workers.dev"
SHARE_TITLE = "데이트메이트 공유 일정"
# 2026-11-25 실제 응답(searchKeyword2 keyword='<script>'): HTTP 400 + 이 본문(test_qa_low_2026_11_25.REJECTED 와 같음).
REJECTED = httpx.Response(
    400,
    json=dict(
        OpenAPI_ServiceResponse=dict(
            cmmMsgHeader=dict(
                errMsg="INVALID_REQUEST_PARAMETER_ERROR",
                returnAuthMsg="잘못된 요청 파라미터 에러",
                returnReasonCode="10",
            )
        )
    ),
)


# ---------------------------------------------------------------- 1) 공유 화면 미리보기


def shared_page(monkeypatch, origin=ORIGIN):
    if origin:
        monkeypatch.setenv("DATEMATE_PUBLIC_ORIGIN", origin)
        monkeypatch.setenv("DATEMATE_ALLOWED_HOSTS", "testserver")
    else:
        monkeypatch.delenv("DATEMATE_PUBLIC_ORIGIN", raising=False)
    with TestClient(app) as client:
        return client.get("/shared")


def test_shared_page_has_a_generic_link_preview(monkeypatch):
    response = shared_page(monkeypatch)
    html = response.text
    assert f'<meta property="og:title" content="{SHARE_TITLE}">' in html
    assert (
        '<meta property="og:description" content="' in html
        and '<meta name="description" content="' in html
    )
    assert f'<meta property="og:image" content="{ORIGIN}/static/images/seoul-evening.jpg">' in html
    assert (
        '<meta property="og:type" content="website">' in html
        and '<meta property="og:site_name" content="데이트메이트">' in html
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert "{{PUBLIC_ORIGIN}}" not in html
    # 검색 제외는 그대로이고, 공유 화면 주소 하나로 묶는 canonical·og:url 은 없다.
    assert (
        '<meta name="robots" content="noindex, nofollow">' in html
        and response.headers["x-robots-tag"] == "noindex, nofollow"
    )
    assert 'rel="canonical"' not in html and "og:url" not in html
    assert (
        response.headers["referrer-policy"] == "no-referrer"
        and response.headers["cache-control"] == "no-store"
    )


def test_shared_preview_has_no_plan_details(monkeypatch):
    """미리보기 문구는 고정된 일반 문구다: 공유 토큰을 읽지 않는 정적 화면이라 일정·장소 이름이 들어갈 길이 없다."""
    html = shared_page(monkeypatch).text
    head = html[: html.index("</head>")]
    previews = [
        line
        for line in head.split("<meta ")
        if "og:" in line or "twitter:" in line or 'name="description"' in line
    ]
    assert len(previews) >= 6 and all("{{" not in line for line in previews)
    source = (ROOT / "static" / "shared.html").read_text(encoding="utf-8")
    assert html.count("<meta ") == source.count("<meta "), (
        "보낼 때 바뀌는 것은 주소 자리표시뿐(태그가 늘지 않음)"
    )
    assert "24시간" in html[html.index("og:description") : html.index("og:description") + 200], (
        "설명은 링크가 24시간짜리라는 일반 안내"
    )


def test_shared_preview_without_a_public_origin_drops_the_image_tag(monkeypatch):
    html = shared_page(monkeypatch, origin=None).text
    assert 'property="og:image"' not in html and "{{PUBLIC_ORIGIN}}" not in html
    assert f'<meta property="og:title" content="{SHARE_TITLE}">' in html, (
        "주소가 필요 없는 설명은 남는다"
    )


NODE_SCRIPT = """
const [build, edge] = await Promise.all([import(process.env.BUILD_URL), import(process.env.EDGE_URL)]);
const pages = build.buildEdgePages();
const shared = edge.pageResponse('/shared', 'GET', { PUBLIC_ORIGIN: process.env.EDGE_ORIGIN }, pages);
const bare = edge.pageResponse('/shared', 'GET', { PUBLIC_ORIGIN: '' }, pages);
process.stdout.write(JSON.stringify({ shared: await shared.text(), bare: await bare.text() }));
"""


@pytest.mark.skipif(
    not shutil.which("node") or not (ROOT.parent / "cloudflare" / "edge.mjs").is_file(),
    reason="needs node and cloudflare/",
)
def test_edge_shared_page_equals_the_app_page(monkeypatch):
    """잠든 컨테이너 대신 Worker 가 주는 공유 화면이 앱이 주는 것과 글자까지 같다(공개 주소 있을 때·없을 때)."""
    app_page = shared_page(monkeypatch).text
    app_bare = shared_page(monkeypatch, origin=None).text
    cloudflare = ROOT.parent / "cloudflare"
    env = dict(
        os.environ,
        BUILD_URL=(cloudflare / "build-edge-pages.mjs").as_uri(),
        EDGE_URL=(cloudflare / "edge.mjs").as_uri(),
        EDGE_ORIGIN=ORIGIN,
    )
    done = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_SCRIPT],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    edge = json.loads(done.stdout)
    assert (
        edge["shared"] == app_page
        and f'content="{ORIGIN}/static/images/seoul-evening.jpg"' in edge["shared"]
    )
    assert edge["bare"] == app_bare


# ---------------------------------------------------------------- 2) 사진 이름 검색의 400


@pytest.fixture
def photo_api(tour):  # noqa: F811 (가져온 고정장치를 받아 씀)
    """tests/test_tour_photo_rules.py 의 가짜 관광공사(이름 검색은 photo_api['search'], 기록은 photo_api['searches'])."""
    return tour


def test_photo_name_search_sends_the_cleaned_name(photo_api):
    """기호가 든 이름은 둘러보기 검색처럼 기호를 빼고 보낸다(예전에는 '"한담해변"!' 그대로 보내 0건 → 사진 없음)."""
    info = tour_places.tour_info(place('"한담해변"!'))
    assert info["status"] == "available" and info["content_id"] == "2723542"
    assert [search["keyword"] for search in photo_api["searches"]] == ["한담해변"]


def test_rejected_photo_name_search_is_not_found_for_a_day_not_an_outage(photo_api):
    photo_api["search"] = REJECTED
    beach = place("한담해변 onerror")
    assert tour_places.tour_info(beach) == dict(status="not_found", reason="rejected")
    # 낱말(가장 긴 낱말) → 이름 전체, 둘 다 거절. 장애(1분)가 아니라 하루 보관이라 다시 부르지 않는다.
    assert [search["keyword"] for search in photo_api["searches"]] == [
        "onerror",
        "한담해변 onerror",
    ]
    left = cache_seconds("tour-place-v3:")
    assert len(left) == 1 and 86000 < left[0] <= 86400
    assert tour_places.tour_photo_result(beach) == dict(status="not_found", photos=[])
    data = media.media_info(beach)
    assert data["photos"] == [] and data["photo_retry"] is False, (
        "'사진 다시 불러오기'를 띄우지 않는다"
    )
    media.media_info(beach, force=True)
    assert len(photo_api["searches"]) == 2, (
        "다시 불러오기(force)도 거절된 이름은 다시 부르지 않는다"
    )
    assert tour_places.tour_hours(beach) is None and tour_places.tour_menu(beach) is None


def test_one_rejected_word_still_tries_the_whole_name(photo_api):
    """찾는 낱말만 거절되고 이름 전체는 받아지면 그 결과로 맞춘다."""
    item = dict(HANDAM[2], title="한담해변 onerror")
    photo_api["search"] = (
        lambda params: REJECTED
        if params["keyword"] == "onerror"
        else {
            "response": dict(
                header=dict(resultCode="0000"), body=dict(items=dict(item=[item]), totalCount=1)
            )
        }
    )
    info = tour_places.tour_info(place("한담해변 onerror"))
    assert info["status"] == "available" and info["content_id"] == "2723542"
    assert [search["keyword"] for search in photo_api["searches"]] == [
        "onerror",
        "한담해변 onerror",
    ]


def test_too_short_photo_name_is_not_searched(photo_api):
    for name in ("★", "<>", "가!"):
        assert tour_places.tour_info(place(name))["status"] == "not_found", name
    assert photo_api["searches"] == [], "정리한 이름이 두 글자 미만이면 부르지 않는다"
    assert media.media_info(place("★"))["photo_retry"] is False


def test_real_outage_is_still_unavailable(photo_api):
    photo_api["search"] = httpx.Response(
        400,
        json=dict(
            OpenAPI_ServiceResponse=dict(
                cmmMsgHeader=dict(
                    errMsg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR", returnReasonCode="30"
                )
            )
        ),
    )
    assert tour_places.tour_info(place("한담해변")) == dict(status="unavailable"), (
        "사유 10 이 아닌 400 은 그대로 실패(1분)"
    )
    assert all(left <= tour_places.FAIL_SECONDS for left in cache_seconds("tour-place-v3:"))
