"""팝업 순수 함수(app/popups.py, 규칙 v1)와 거점 사전 v0·v1 의 단위 테스트. 외부 호출 없음."""

from datetime import date

import pytest

from app import popups
from app.popup_hubs import HUBS, HUBS_V0, HUBS_VERSION

V = date(2026, 11, 20)


def period(title, description=""):
    return popups.extract_period(title, description)


# ---------------------------------------------------------------- 정규화


def test_normalize_text_strips_tags_and_entities_as_plain_text():
    assert popups.normalize_text("<b>성수</b> &amp; 팝업&#39;s  \n 후기") == "성수 & 팝업's 후기"
    # 엔티티로 온 꺾쇠는 글자로 남는다(화면에는 텍스트로만 넣는다).
    assert popups.normalize_text("&lt;무신사&gt; 팝업") == "<무신사> 팝업"


# ---------------------------------------------------------------- 날짜·기간


@pytest.mark.parametrize(
    "text,start,end",
    [
        (
            "팝업 운영 기간 2026.11.14~2026.11.30",
            date(2026, 11, 14),
            date(2026, 11, 30),
        ),
        (
            "팝업 기간 2026년 11월 14일부터 30일까지",
            date(2026, 11, 14),
            date(2026, 11, 30),
        ),
        (
            "팝업 기간 2026. 11. 14.(토) ~ 2026. 11. 30.(월)",
            date(2026, 11, 14),
            date(2026, 11, 30),
        ),
        ("팝업 운영 26.11.14~26.11.30", date(2026, 11, 14), date(2026, 11, 30)),
        # 시작에만 연도가 있으면 같은 문맥에서 종료 연도를 잇는다. 연말·연초를 넘으면 다음 해.
        ("팝업 기간 2026.12.20~1.5", date(2026, 12, 20), date(2027, 1, 5)),
        ("팝업 기간 2026.11.14~11.30", date(2026, 11, 14), date(2026, 11, 30)),
    ],
)
def test_full_periods_with_year(text, start, end):
    found = period(text)
    assert found["status"] == "period"
    p = found["period"]
    assert (p["start"], p["end"], p["year_known"]) == (start, end, True)


@pytest.mark.parametrize(
    "text,start_md,end_md",
    [
        ("성수 팝업 11.14~11.30", (11, 14), (11, 30)),
        ("팝업 기간 11월 14일부터 30일까지", (11, 14), (11, 30)),
        ("팝업스토어 11월 14일 ~ 11월 30일", (11, 14), (11, 30)),
    ],
)
def test_year_missing_keeps_month_day_but_no_full_date(text, start_md, end_md):
    found = period(text)
    assert found["status"] == "period"
    p = found["period"]
    assert (p["start_md"], p["end_md"]) == (start_md, end_md)
    assert p["start"] is None and p["end"] is None and p["year_known"] is False
    # 게시 연도나 오늘로 채우지 않으므로 상태는 기간 미확인.
    assert popups.visit_status(p, V)["status"] == "unknown"


def test_year_missing_range_across_new_year_is_marked_but_still_yearless():
    p = period("팝업 운영 12.20~1.5")["period"]
    assert p["crosses_year"] is True and p["year_known"] is False


def test_end_only_and_start_only():
    end_only = period("팝업 운영 ~2026.11.30")["period"]
    assert end_only["kind"] == "end_only" and end_only["end"] == date(2026, 11, 30)
    until = period("팝업 2026.11.30까지 운영")["period"]
    assert until["kind"] == "end_only" and until["end"] == date(2026, 11, 30)
    start_only = period("팝업스토어 2026.11.14 오픈")["period"]
    assert start_only["kind"] == "start_only" and start_only["start"] == date(2026, 11, 14)
    yearless_end = period("팝업 ~11.30")["period"]
    assert yearless_end["end_md"] == (11, 30) and yearless_end["end"] is None


@pytest.mark.parametrize(
    "text",
    [
        "팝업 운영시간 11:00~20:00",
        "팝업 방문객은 10~20대가 많아요",
        "팝업 매출이 2.5~3배 늘었다",
        "팝업 입장료 12.000원, 굿즈 1.5만원",
        "팝업 앱 버전 v2.1 업데이트",
        "팝업 버전 2.1.3 출시",
        "팝업 서울 성동구 연무장길 12-3",
        "팝업 문의 02.123.4567",
        "팝업 3.1절 기념",
    ],
)
def test_times_ages_ratios_prices_versions_are_not_dates(text):
    found = period(text)
    assert found["status"] == "none"
    assert found["rejected"] == []


@pytest.mark.parametrize(
    "text",
    [
        "팝업 기간 2026.2.30~2026.3.5",
        "팝업 기간 2026.13.1~2026.13.5",
        "팝업 기간 2025.2.29~2025.3.5",  # 2025년은 윤년이 아님
        "팝업 기간 2026.11.30~2026.11.14",  # 종료가 시작보다 앞섬
    ],
)
def test_impossible_dates_are_rejected(text):
    assert period(text)["status"] == "none"


def test_leap_day_is_valid():
    p = period("팝업 기간 2028.2.29~2028.3.5")["period"]
    assert p["start"] == date(2028, 2, 29)


def test_reservation_raffle_and_visit_dates_are_not_event_periods():
    reserve = period("성수 무신사 팝업", "사전 예약 11.10~11.12 진행, 응모는 11월 13일까지")
    assert reserve["status"] == "none"
    assert {r["context"] for r in reserve["rejected"]} == {"other"}
    visit = period("무신사 팝업 다녀왔어요", "11월 15일 방문 후기")
    assert visit["status"] == "none"
    # 같은 글에 예약 기간과 운영 기간이 있으면 운영 기간만 쓴다.
    both = period("무신사 팝업", "예약 2026.11.1~2026.11.5 / 팝업 운영 기간 2026.11.14~2026.11.30")
    assert both["status"] == "period"
    assert both["period"]["start"] == date(2026, 11, 14)


def test_two_different_event_periods_are_a_conflict_not_merged():
    found = period("무신사 팝업 기간 2026.11.1~2026.11.10", "2차 팝업 기간 2026.11.20~2026.11.30")
    assert found["status"] == "conflict" and found["period"] is None
    assert len(found["periods"]) == 2
    assert popups.post_status(found, V)["status"] == "unknown"


def test_single_date_without_period_words_is_not_adopted():
    assert period("무신사 팝업", "11월 15일 토요일에 친구랑")["status"] == "none"


def test_counterfactual_year_uses_source_year_only_in_the_counterfactual():
    p = period("팝업 운영 12.20~1.5")["period"]
    cf = popups.counterfactual_period(p, date(2026, 12, 1))
    assert (cf["start"], cf["end"], cf["assumed_year"]) == (
        date(2026, 12, 20),
        date(2027, 1, 5),
        True,
    )
    assert p["start"] is None  # 원래 판정은 그대로
    assert popups.counterfactual_period(p, None) is p


# ---------------------------------------------------------------- 방문일 상태


def full(start, end):
    return dict(
        start=start,
        end=end,
        start_md=(start.month, start.day) if start else None,
        end_md=(end.month, end.day) if end else None,
    )


@pytest.mark.parametrize(
    "start,end,visit,status,end_only",
    [
        (date(2026, 11, 14), date(2026, 11, 30), date(2026, 11, 14), "ongoing", False),
        (date(2026, 11, 14), date(2026, 11, 30), date(2026, 11, 30), "ongoing", False),
        (date(2026, 11, 14), date(2026, 11, 30), date(2026, 11, 13), "upcoming", False),
        (date(2026, 11, 14), date(2026, 11, 30), date(2026, 12, 1), "ended", False),
        (date(2026, 11, 14), None, date(2026, 11, 13), "upcoming", False),
        (date(2026, 11, 14), None, date(2026, 11, 14), "unknown", False),
        (None, date(2026, 11, 30), date(2026, 11, 30), "unknown", True),
        (None, date(2026, 11, 30), date(2026, 12, 1), "ended", True),
        (date(2026, 12, 28), date(2027, 1, 3), date(2027, 1, 2), "ongoing", False),
    ],
)
def test_visit_status_table(start, end, visit, status, end_only):
    got = popups.visit_status(full(start, end), visit)
    assert (got["status"], got["end_only"]) == (status, end_only)


def test_status_is_recomputed_for_each_visit_date():
    p = period("팝업 기간 2026.11.14~2026.11.30")["period"]
    assert [
        popups.visit_status(p, d)["status"] for d in (date(2026, 11, 1), V, date(2026, 12, 2))
    ] == [
        "upcoming",
        "ongoing",
        "ended",
    ]


def test_no_period_is_unknown():
    assert popups.visit_status(None, V)["status"] == "unknown"


# ---------------------------------------------------------------- 거점


def hub_ids(text):
    return [m["id"] for m in popups.match_hubs(text, HUBS_V0)]


def test_hub_dictionary_v0_shape():
    ids = [h["id"] for h in HUBS_V0]
    assert len(ids) == len(set(ids)) == 31
    for h in HUBS_V0:
        assert h["kind"] in ("building", "area")
        assert h["verify"] and h["aliases"] and h["local_query"]
        assert (h["anchor"] is None) == (h["kind"] == "building")
        assert "lat" not in h and "lon" not in h  # 좌표는 코드에 두지 않는다


def test_hub_aliases_and_longest_alias_wins():
    assert hub_ids("더현대서울 팝업") == ["seoul-thehyundai"]
    assert hub_ids("AK플라자 홍대점 팝업") == ["seoul-akplaza-hongdae"]  # '홍대' 일대가 아님
    assert hub_ids("홍대입구 팝업") == ["seoul-area-hongdae"]
    assert hub_ids("서울성수 팝업") == ["seoul-area-seongsu"]


def test_broad_brand_alone_does_not_pick_a_branch():
    # '더현대'만으로는 서울·대구 중 어디인지 모른다. '신세계'만으로도 지점을 고르지 않는다.
    assert hub_ids("더현대 팝업스토어") == []
    assert hub_ids("신세계백화점 팝업") == []
    assert hub_ids("롯데백화점 팝업") == []


def test_same_brand_other_branch_matches_the_right_hub():
    assert hub_ids("더현대 대구 팝업") == ["daegu-thehyundai"]
    assert hub_ids("롯데백화점 부산본점 팝업") == ["busan-lotte-main"]
    assert hub_ids("롯데백화점 본점 팝업") == ["seoul-lotte-main"]


def test_short_alias_boundaries():
    assert hub_ids("성수기 여행 팝업") == []  # 성수기
    assert hub_ids("코엑스마곡 팝업") == []
    assert hub_ids("안도산 팝업") == []


def test_multiple_hubs_are_not_forced_to_one_place():
    got = popups.hub_match("더현대 서울과 롯데월드몰 팝업", HUBS_V0, "서울")
    assert got["status"] == "multiple" and got["hub_id"] is None
    other = popups.hub_match("더현대 대구 팝업", HUBS_V0, "서울")
    assert other["status"] == "other_region"
    single = popups.hub_match("성수동 팝업", HUBS_V0, "서울")
    assert (single["status"], single["hub_id"]) == ("single", "seoul-area-seongsu")


HUB = next(h for h in HUBS_V0 if h["id"] == "seoul-thehyundai")
AREA = next(h for h in HUBS_V0 if h["id"] == "seoul-area-seongsu")


def local(title, address, lon, lat):
    return dict(
        title=title,
        roadAddress=address,
        mapx=str(int(lon * 1e7)),
        mapy=str(int(lat * 1e7)),
    )


def test_local_result_is_verified_by_name_region_and_district_not_first_item():
    items = [
        local("더현대 주차장", "서울특별시 영등포구 여의대로 108", 126.928, 37.525),
        local("<b>더현대 서울</b>", "서울특별시 영등포구 여의대로 108", 126.9284, 37.5259),
    ]
    got = popups.verify_local_result(HUB, items)
    assert got["status"] == "verified" and got["level"] == "building"
    assert got["point"]["name"] == "더현대 서울"
    assert abs(got["point"]["lat"] - 37.5259) < 1e-6


def test_local_result_other_district_or_far_duplicates_is_unverified():
    wrong = [local("더현대 서울 팝업", "서울특별시 성동구 성수동 1", 127.05, 37.54)]
    assert popups.verify_local_result(HUB, wrong)["status"] == "unverified"
    far = [
        local("더현대서울", "서울특별시 영등포구 여의대로 108", 126.9284, 37.5259),
        local("더현대서울 별관", "서울특별시 영등포구 국제금융로 1", 126.90, 37.52),
    ]
    assert popups.verify_local_result(HUB, far)["status"] == "ambiguous"
    area = popups.verify_local_result(
        AREA,
        [local("성수역 2호선", "서울특별시 성동구 아차산로 100", 127.0559, 37.5446)],
    )
    assert area["level"] == "area_anchor"


# ---------------------------------------------------------------- 모아 보기·행사명


def test_roundup_needs_signal_and_multiple_places():
    assert (
        popups.classify_roundup("11월 성수 팝업스토어 총정리 10곳", "", HUBS_V0)["kind"]
        == "roundup"
    )
    assert (
        popups.classify_roundup(
            "이번주 팝업 일정", "더현대 서울 'A' 팝업, 롯데월드몰 'B' 팝업", HUBS_V0
        )["kind"]
        == "roundup"
    )
    # 신호 단어만 있고 여러 행사 근거가 없으면 애매(단일 카드로 승격하지 않음).
    assert popups.classify_roundup("무신사 팝업 후기 정리", "", HUBS_V0)["kind"] == "ambiguous"
    assert popups.classify_roundup("무신사 팝업스토어 후기", "", HUBS_V0)["kind"] == "single"


@pytest.mark.parametrize(
    "title,name",
    [
        ("성수 '무신사 스탠다드' 팝업스토어 후기", "무신사 스탠다드"),
        ("[성수] 무신사 팝업스토어 다녀옴", "무신사"),
        ("더현대서울 NEW BALANCE 팝업", "NEW BALANCE"),
        ("「포켓몬」 팝업 오픈", "포켓몬"),
    ],
)
def test_event_name_explicit(title, name):
    assert popups.event_name(title, HUBS_V0)["name"] == name


@pytest.mark.parametrize(
    "title",
    [
        "성수 팝업스토어 후기",  # 거점(동네) 이름
        "더현대 서울 팝업스토어",  # 거점 이름을 행사명으로 조합하지 않음
        "부산 팝업스토어 총정리",
        "11월 팝업 일정",
        "요즘 핫한 팝업",
        "'무신사' 팝업과 '나이키' 팝업",  # 이름이 둘
    ],
)
def test_event_name_not_identified(title):
    assert popups.event_name(title, HUBS_V0)["name"] is None


# ---------------------------------------------------------------- URL·묶기


def test_url_dedupe_keeps_first_and_unifies_mobile_blog():
    posts = [
        dict(url="https://blog.naver.com/a/1", n=1),
        dict(url="https://m.blog.naver.com/a/1/", n=2),
        dict(url="javascript:alert(1)", n=3),
        dict(url="https://news.example.com/x#top", n=4),
        dict(url="https://news.example.com/x", n=5),
    ]
    assert [p["n"] for p in popups.dedupe_by_url(posts)] == [1, 4]


def P(start, end, year_known=True):
    return dict(
        kind="range",
        start=start if year_known else None,
        end=end if year_known else None,
        start_md=(start.month, start.day),
        end_md=(end.month, end.day),
        year_known=year_known,
        crosses_year=False,
    )


def post(url, hub="seoul-area-seongsu", key="무신사", per=None, conflict=False):
    return dict(url=url, hub_id=hub, name_key=key, period=per, conflict=conflict)


A = P(date(2026, 11, 1), date(2026, 11, 10))
B = P(date(2026, 11, 20), date(2026, 11, 30))
C = P(date(2026, 11, 5), date(2026, 11, 25))


def test_same_hub_name_and_period_merge_other_rounds_split():
    cards = popups.group_posts(
        [
            post("https://x/1", per=A),
            post("https://x/2", per=A),
            post("https://x/3", per=B),
        ]
    )
    assert [len(c["urls"]) for c in cards] == [2, 1]
    assert not any(c["conflict"] for c in cards)


def test_overlapping_different_periods_are_shown_as_conflict_not_widened():
    cards = popups.group_posts([post("https://x/1", per=A), post("https://x/2", per=C)])
    assert len(cards) == 1 and cards[0]["conflict"] is True
    assert {(p["start"], p["end"]) for p in cards[0]["periods"]} == {
        (A["start"], A["end"]),
        (C["start"], C["end"]),
    }
    assert popups.group_status(cards[0], V)["status"] == "unknown"


def test_undated_post_attaches_only_when_one_round_exists():
    one = popups.group_posts([post("https://x/1", per=A), post("https://x/2")])
    assert len(one) == 1 and len(one[0]["urls"]) == 2
    two = popups.group_posts(
        [post("https://x/1", per=A), post("https://x/3", per=B), post("https://x/2")]
    )
    assert len(two) == 3
    assert [c for c in two if not c["periods"]][0]["urls"] == ["https://x/2"]


def test_same_name_different_hub_or_missing_name_never_merge():
    cards = popups.group_posts(
        [
            post("https://x/1", per=A),
            post("https://x/2", hub="seoul-thehyundai", per=A),
            post("https://x/3", key=None),
        ]
    )
    assert len(cards) == 2


def test_grouping_is_reproducible_regardless_of_input_order():
    rows = [
        post("https://x/1", per=A),
        post("https://x/2", per=C),
        post("https://x/3", per=B),
        post("https://x/4"),
    ]
    first = popups.group_posts(rows)
    again = popups.group_posts(list(reversed(rows)))
    assert first == again
    assert len({c["id"] for c in first}) == len(first)


# ---------------------------------------------------------------- 규칙 v1: 0단계 오인식 사례 회귀 테스트
# 문장은 0단계 보고(docs/popup-stage0-2026-11-14.md) 4-1 검토 표·5절 사례의 제목·요약을 줄인 것이다.


def test_v1_weekday_without_parentheses_keeps_the_range():
    # 서울 #1: 괄호 없는 요일 때문에 '종료일만·연도 미상'으로 읽던 것.
    p = period("헬로키티 팝업", "팝업 기간 2026년 11월 25일 수요일~12월 27일 일요일")["period"]
    assert (p["kind"], p["start"], p["end"], p["year_known"]) == (
        "range",
        date(2026, 11, 25),
        date(2026, 12, 27),
        True,
    )


def test_v1_from_until_with_eseo():
    # 대구 #54: '에서 … 까지'를 연결로 몰라 놓치던 것.
    found = period(
        "더현대 대구 팝업",
        "해피메타몽 팝업스토어 에 다녀왔어요 11월6일에서 11월19일까지 열려있어요",
    )
    assert found["status"] == "period"
    assert (found["period"]["start_md"], found["period"]["end_md"]) == ((11, 6), (11, 19))
    # '까지'가 없으면 장소의 '에서'일 수 있어 범위로 잇지 않는다.
    loose = popups.date_candidates("팝업 기간 11월 6일에서 11월 9일 사이")
    assert all(c["type"] != "range" for c in loose)


def test_v1_two_digit_year_with_korean_units():
    # 강원 #61: '26년 11월 13일(금)~11월 26일(목)'의 연도를 못 읽던 것.
    p = period(
        "부산 센텀 팝업 총정리", "팝업 지하 1층! 26년 11월 13일(금)~11월 26일(목) 양배추 떡볶이"
    )["period"]
    assert (p["start"], p["end"]) == (date(2026, 11, 13), date(2026, 11, 26))
    # 네 자리 연도의 뒤 두 자리를 두 자리 연도로 다시 읽지 않는다.
    assert period("팝업 기간 2026년 11월 13일부터 20일까지")["period"]["start"] == date(
        2026, 11, 13
    )


def test_v1_store_opening_day_is_not_a_popup_start():
    # 대구 #44: 매장 개점일을 팝업 시작일로 읽던 것.
    assert (
        period("[대전 이케아] 11월 19일 오픈! 현대프리미엄아울렛 대전점 이케아 방문")["status"]
        == "none"
    )
    assert (
        period("무신사 뷰티 성수 오픈", "매장명 무신사 뷰티 성수 개점일 2026년 11월 11일")["status"]
        == "none"
    )
    # 팝업 문맥의 오픈은 그대로 시작일.
    assert period("팝업스토어 2026.11.14 오픈")["period"]["start"] == date(2026, 11, 14)


def hubs_v1(text, region):
    return popups.hub_match(text, HUBS, region)


def test_v1_past_place_is_not_the_event_place():
    # 부산 #25: '지난번 … 에 이어' 장소에 매칭하고, 띄어쓰기가 다른 이번 장소는 놓치던 것.
    got = hubs_v1(
        "나가노마켓 팝업 지난번 신세계백화점 센텀시티에 이어 이번에는 롯데백화점 부산 본점에서 진행",
        "부산",
    )
    assert (got["status"], got["hub_id"]) == ("single", "busan-lotte-main")
    assert got["past_ids"] == ["busan-shinsegae-centum"]


def test_v1_comparison_mention_moves_post_out_of_the_searched_region():
    # 서울 #19: 더현대 대구 후기를 비교로 언급한 '더현대 서울'에 매칭하던 것 → 다른 지역 글로 분리.
    got = hubs_v1(
        "더현대 대구 크리스마스 ／ 더현대 서울 이랑은 차원이 다르게 볼품이 없구나", "서울"
    )
    assert got["status"] == "other_region" and got["ids"] == ["daegu-thehyundai"]


def test_v1_spacing_variants_and_new_aliases():
    ids = [m["id"] for m in popups.match_hubs("서면롯데백화점 팝업", HUBS)]
    assert ids == ["busan-lotte-main"]
    assert [m["id"] for m in popups.match_hubs("신세계백화점 대구 점 팝업", HUBS)] == [
        "daegu-shinsegae"
    ]
    assert [m["id"] for m in popups.match_hubs("전주 롯데백화점 위드썸 팝업", HUBS)] == [
        "jeonbuk-lotte-jeonju"
    ]
    # 지점을 특정할 수 없는 표기는 여전히 매칭하지 않는다.
    for text in ("센텀시티 팝업", "롯데백화점 팝업", "대구 롯데백화점 팝업", "더현대 팝업"):
        assert popups.match_hubs(text, HUBS) == [], text


def test_hub_dictionary_v1_keeps_v0_and_has_verifiable_entries():
    v1 = {h["id"]: h for h in HUBS}
    assert len(v1) == len(HUBS) == 35
    assert HUBS_VERSION == "hubs-v1.1-2026-11-14" and popups.RULES_VERSION == "popups-rules-v4"
    for h in HUBS:
        assert h["verify"] and h["local_query"] and h["district"]
        assert "lat" not in h and "lon" not in h
    assert all(set(v1[h["id"]]["aliases"]) >= set(h["aliases"]) for h in HUBS_V0)


def test_v1_local_search_prefers_the_building_over_a_tenant_shop():
    hub = next(h for h in HUBS if h["id"] == "daegu-shinsegae")
    items = [
        dict(
            local("유니클로 신세계 대구점", "대구광역시 동구 효신로 88", 128.6290, 35.8820),
            category="패션,의류>캐주얼",
        ),
        dict(
            local("신세계백화점 대구점", "대구광역시 동구 동부로 149", 128.6280, 35.8771),
            category="쇼핑,유통>백화점",
        ),
    ]
    got = popups.verify_local_result(hub, items)
    # v0 은 두 항목이 300m 넘게 떨어져 모호로 판정했다.
    assert got["status"] == "verified" and got["point"]["name"] == "신세계백화점 대구점"
    jeonju = next(h for h in HUBS if h["id"] == "jeonbuk-lotte-jeonju")
    ok = popups.verify_local_result(
        jeonju,
        [local("롯데백화점 전주점", "전북특별자치도 전주시 완산구 온고을로 2", 127.115, 35.832)],
    )
    assert ok["status"] == "verified"


# ---------------------------------------------------------------- v1.1 사후 조정: 새 표본(2페이지)에서 본 v1 오인식


def test_v1_1_last_month_mention_is_a_past_place():
    # 대구 표본: 인천점 팝업 글의 '지난 10월 신세계백화점 대구 점'을 이번 장소로 읽던 것.
    got = hubs_v1(
        "이번 롯데백화점 인천점 팝업스토어 는 지난 10월 신세계백화점 대구 점과 11월 신세계백화점 강남점에 이어 진행",
        "대구",
    )
    assert got["status"] == "none" and got["hub_id"] is None
    assert set(got["past_ids"]) == {"daegu-shinsegae", "seoul-shinsegae-gangnam"}


def test_v1_1_hubs_from_several_regions_are_not_forced_to_the_searched_one():
    # 부산 표본: 잠실 방문 글에 나열된 '롯데백화점 부산 본점', 대구 표본: 더현대 서울 글의 '대구 더현대에서도 … 운영된 적이'.
    listed = hubs_v1(
        "피크민 in 잠실 방문 후기 롯데몰 청량리점, 롯데몰 잠실점, 롯데백화점 부산 본점 총 3곳",
        "부산",
    )
    assert listed["status"] == "multiple" and listed["mixed_regions"] is True
    seoul = hubs_v1(
        "더현대 서울 치이카와 클리닉 팝업 예약방법 대구 더현대에서도 나가노마켓이 운영된 적이",
        "대구",
    )
    assert seoul["status"] == "multiple" and seoul["hub_id"] is None
    # 부산 해시태그 '# 부산 롯데백화점본점'은 서울 '롯데백화점 본점'이 아니다(사전 v1.1 별칭).
    busan = hubs_v1("무기와라 팝업스토어 (롯데백화점 부산 본점) # 부산 롯데백화점본점", "부산")
    assert (busan["status"], busan["hub_id"]) == ("single", "busan-lotte-main")
