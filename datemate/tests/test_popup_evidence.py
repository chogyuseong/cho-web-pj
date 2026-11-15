"""팝업 행사 증거 점수(app/popups.py popup_evidence, 규칙 v2). 외부 호출 없음.

CASES 는 **합성 표본**이다(실제 검색 결과가 아니라 0단계·1단계 보고의 글 유형과 사용자가 본 KFC 사례를 본떠 직접 쓴 제목·요약).
라벨 True = 팝업 행사 글로 보여 줘야 함, False = 빼야 함.
"""

import pytest

from app import popups
from app.popup_hubs import HUBS

KFC_TITLE = "KFC 둠스데이 친구 초대 이벤트 참여 방법 및 추천코드 Qa1vX 혜택 총정리"
KFC_DESCRIPTION = (
    "초대 보상 쿠폰은 추천 코드를 통한 회원가입이 발생할 때 메인 팝업을 통해 즉시 지급되지만 "
    "#KFC이벤트 #KFC추천코드 #KFC친구초대"
)

# (이름, 검색 지역, 제목, 요약, 라벨)
CASES = [
    # ---- 진짜 팝업 글 유형
    (
        "제목 팝업스토어+기간+거점",
        "서울",
        "더현대 서울 올기 팝업스토어 후기",
        "기간 2026.10.20~2026.11.16",
        True,
    ),
    (
        "제목 '팝업'+거점",
        "서울",
        "성수 짱구 팝업 다녀왔어요",
        "성수동에서 열린 짱구 웨이팅 후기",
        True,
    ),
    ("제목 '팝업'만", "부산", "정서불안 김햄찌 팝업 굿즈 후기", "귀여운 굿즈가 가득했어요", True),
    (
        "요약 팝업 스토어+기간+거점",
        "서울",
        "오브더블루 프리 데뷔 베이스캠프",
        "팝업 스토어 기본 정보 * 장소: 성수 * 기간: 2026.11.12~2026.11.25",
        True,
    ),
    (
        "요약 '팝업'+거점",
        "부산",
        "아라비카 커피 응커피 후기",
        "신세계 센텀시티에 팝업 으로 들어왔다고 해서",
        True,
    ),
    (
        "쿠폰 증정 팝업스토어",
        "대구",
        "르비크 팝업스토어 쿠폰 증정 이벤트",
        "팝업스토어에서 구매하면 할인 쿠폰 증정",
        True,
    ),
    (
        "제목 팝업스토어+회원가입",
        "서울",
        "무신사 팝업스토어 회원가입 혜택 총정리",
        "회원가입하면 사은품",
        True,
    ),
    ("영문 POP-UP STORE", "서울", "브랜드X POP-UP STORE 오픈", "성수 팝업 정보", True),
    (
        "요약 온라인 팝업스토어+기간",
        "전북",
        "K리그 산리오 굿즈 출시",
        "2026년 11월 12일부터 CJ온스타일에서 온라인 팝업스토어 가 진행된다는 소식",
        True,
    ),
    (
        "제목 부산팝업+기간",
        "부산",
        "정서불안 김햄찌 캘린더 부산팝업 구매링크",
        "일정 : 26.11.11(수) ~ 26.11.22(금)",
        True,
    ),
    ("팝업 카페", "서울", "치이카와 팝업 카페 후기", "예약 방법 정리", True),
    ("안내 팝업스토어", "대구", "주말 나들이", "위치 안내 팝업스토어 는 1층", True),
    ("'팝업 창원'은 창이 아님", "경남", "롯데백화점 팝업 창원점 방문", "", True),
    (
        "'팝업이 뜨거운'은 창이 아님",
        "서울",
        "성수 팝업이 뜨거운 이유",
        "요즘 성수 팝업이 뜨겁다",
        True,
    ),
    ("팝업 메뉴", "서울", "더현대 팝업 메뉴 가격", "팝업 메뉴는 세 가지", True),
    (
        "요약 '팝업'+기간",
        "서울",
        "주말 나들이 기록",
        "11월 14일부터 30일까지 팝업 운영 한다고 해서 다녀옴",
        True,
    ),
    (
        "요약 팝업스토어+회원가입+기간+거점",
        "대구",
        "르비크 할인 소식",
        "대구 신세계백화점 르비크 팝업스토어 11.13~11.19 운영, 회원가입 시 쿠폰",
        True,
    ),
    # ---- 오탐 유형
    ("KFC 추천코드(사용자 사례)", "서울", KFC_TITLE, KFC_DESCRIPTION, False),
    (
        "앱 친구 초대",
        "서울",
        "토스 친구 초대 이벤트 추천인 코드",
        "가입 후 앱 팝업 에서 확인",
        False,
    ),
    ("팝업 차단", "서울", "크롬 팝업 차단 해제 방법", "팝업 차단을 해제하려면 설정에서", False),
    ("팝업북", "서울", "아이랑 만든 책 후기", "입체 팝업북 만들기", False),
    ("팝업 텐트", "서울", "캠핑 원터치 텐트 추천", "팝업텐트 3초 설치, 팝업 텐트 비교", False),
    ("팝업 카드", "서울", "생일 카드 만들기", "팝업카드 도안 공유", False),
    (
        "팝업이 뜨면",
        "서울",
        "배민 쿠폰 받는 법",
        "앱 실행 시 팝업이 뜨면 쿠폰 받기 누르세요",
        False,
    ),
    ("레이어 팝업", "서울", "웹사이트 만들기 CSS", "레이어 팝업 띄우기 예제", False),
    ("요약 '팝업' 한 마디만", "서울", "동네 빵집 후기", "팝업 아님", False),
    (
        "앱 가입 홍보",
        "서울",
        "OO 앱 신규 가입 이벤트",
        "앱 설치 후 회원가입 하면 팝업 으로 쿠폰",
        False,
    ),
    ("광고 팝업", "서울", "스마트폰 정리 팁", "광고 팝업 제거하는 법", False),
    ("알림 팝업", "서울", "카톡 설정 팁", "카톡 알림 팝업 끄기", False),
    ("팝업 창", "서울", "공지 확인 방법", "팝업 창 닫기, 팝업창 안 뜰 때", False),
    (
        "요약 팝업스토어+추천코드(거점·기간 없음)",
        "서울",
        "OO페이 추천코드 이벤트",
        "팝업스토어 대신 앱에서 추천코드 입력하면 적립",
        False,
    ),
]


def verdict(region, title, description):
    """judge 와 같은 순서로 기간·거점을 계산해 넘긴다."""
    text = title + " \n " + description
    hub = popups.hub_match(text, HUBS, region)
    extraction = popups.extract_period(title, description)
    return popups.popup_evidence(
        title,
        description,
        has_period=extraction["status"] != "none",
        has_hub=hub["status"] in ("single", "multiple"),
    )


@pytest.mark.parametrize("name,region,title,description,label", CASES, ids=[c[0] for c in CASES])
def test_labelled_cases(name, region, title, description, label):
    assert popups.has_popup(title + " " + description)
    result = verdict(region, title, description)
    assert result["show"] is label, result


def test_kfc_referral_post_is_excluded_with_reasons():
    result = verdict("서울", KFC_TITLE, KFC_DESCRIPTION)
    assert result["show"] is False
    # 화면 요소 '메인 팝업'은 증거가 아니고, 남은 '팝업'이 없다.
    assert result["excluded"] == ["메인 팝업"]
    assert result["evidence"] == []
    assert result["penalties"] == ["promo:초대보상,추천코드,친구초대,회원가입"]
    assert result["score"] < popups.SHOW_THRESHOLD


def test_reasons_name_the_evidence_and_points():
    result = verdict("서울", "더현대 서울 올기 팝업스토어 후기", "기간 2026.10.20~2026.11.16")
    assert result["evidence"] == ["title_term:팝업스토어", "period", "hub"]
    assert result["score"] == 6 and result["penalties"] == [] and result["excluded"] == []
    weak = popups.popup_evidence("동네 빵집 후기", "팝업 아님", has_period=False, has_hub=False)
    assert weak == dict(
        show=False, score=1, evidence=["description_bare:팝업"], penalties=[], excluded=[]
    )


@pytest.mark.parametrize(
    "text,terms,bare,excluded",
    [
        ("성수 팝업스토어 · 팝업 스토어 · 팝업샵", ["팝업스토어", "팝업 스토어", "팝업샵"], [], []),
        (
            "팝업 매장 팝업 행사 팝업존 팝업 오픈",
            ["팝업 매장", "팝업 행사", "팝업존", "팝업 오픈"],
            [],
            [],
        ),
        ("Pop-up Store / popup shop / POPUP", ["Pop-up Store", "popup shop"], ["POPUP"], []),
        (
            "메인 팝업 앱 팝업 알림 팝업 팝업 광고",
            [],
            [],
            ["메인 팝업", "앱 팝업", "알림 팝업", "팝업 광고"],
        ),
        (
            "팝업창 팝업 차단 팝업북 팝업 카드 팝업 텐트",
            [],
            [],
            ["팝업창", "팝업 차단", "팝업북", "팝업 카드", "팝업 텐트"],
        ),
        # 앞말로 거르는 꼴 뒤에 행사 표현이 오면 행사로 본다.
        ("메인 팝업스토어 안내 팝업존", ["팝업스토어", "팝업존"], [], []),
        # 행사가 열린다는 서술과 달을 붙인 팝업은 행사 표현. '열리면'은 화면 창일 수 있어 단독 '팝업'.
        (
            "지하 1층 팝업 열렸다 11월 팝업 팝업 공간 팝업이 열리면",
            ["팝업 열렸", "11월 팝업", "팝업 공간"],
            ["팝업"],
            [],
        ),
        # 한 글 안에 화면 요소와 행사가 함께 있으면 행사 쪽은 남는다.
        ("팝업창 말고 진짜 팝업 다녀옴", [], ["팝업"], ["팝업창"]),
    ],
)
def test_mentions_split_event_terms_from_screen_elements(text, terms, bare, excluded):
    assert popups.popup_mentions(text) == (terms, bare, excluded)


def test_title_term_survives_promo_penalty_but_description_bare_does_not():
    title_term = popups.popup_evidence("팝업스토어 추천코드", "", has_period=False, has_hub=False)
    assert title_term["show"] is True and title_term["score"] == 2
    title_bare = popups.popup_evidence("팝업 이벤트 추천코드", "", has_period=False, has_hub=False)
    assert title_bare["show"] is False and title_bare["score"] == 0
    # 기간·거점이 받쳐 주면 요약의 행사 표현은 감점이 있어도 남는다.
    supported = popups.popup_evidence(
        "할인 소식", "팝업스토어 회원가입 시 쿠폰", has_period=True, has_hub=True
    )
    assert supported["show"] is True and supported["score"] == 2
    unsupported = popups.popup_evidence(
        "할인 소식", "팝업스토어 회원가입 시 쿠폰", has_period=False, has_hub=False
    )
    assert unsupported["show"] is False


def test_coupon_and_discount_alone_are_not_penalties():
    result = popups.popup_evidence(
        "할인 소식", "팝업스토어 쿠폰 증정 할인 이벤트", has_period=False, has_hub=False
    )
    assert result["show"] is True and result["penalties"] == []


def test_rules_version_was_raised():
    assert popups.RULES_VERSION == "popups-rules-v2"
