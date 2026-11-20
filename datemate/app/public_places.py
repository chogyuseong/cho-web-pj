"""추천 후보와 둘러보기 목록을 공공 자료에서 만든다(2026-11-20, docs/naver-terms-stage2-design.ko.md 3.8(b)·3.5(b)).

왜: 네이버 검색 API 특약(2026-09 개정) 2.1·2.2 의 엄격한 읽기 — 검색 결과를 우리 계산(후보 찾기·점수·필터·이유 문장)의 입력으로
쓰지 않는다. 예전에는 서울 밖과 요청 활동의 후보가 네이버 지역 검색 결과였다(app/intent_discovery, leisure, restaurants, explore).
이제 후보는 우리 카탈로그(시드·큐레이션) + 아래 두 공공 자료에서만 나온다. 둘 다 공공데이터포털 '이용허락범위 제한 없음'이라
저장·가공·정렬이 자유롭다.

자료
  1) 한국관광공사 TourAPI(KorService2) — 시·군·구 목록 areaBasedList2(법정동 코드 lDongRegnCd·lDongSignguCd), 이름 검색 searchKeyword2.
     관광지·문화시설·레포츠·쇼핑·음식점(카페 포함). 사진(공공누리 제1·제3유형만, app/festivals.festival_image 와 같은 기준)이 함께 온다.
     관광공사가 고른 곳이라 가게마다 사진·소개가 있다(종로구: 관광지 147, 문화시설 160, 음식점 187곳). 후보에서 먼저 쓴다.
     반경 목록(locationBasedList2)과 예전 지역 코드(areaCode·sigunguCode)·예전 분류(cat1~3)는 쓰지 않는다: 2026-11-20 실제 응답에서
     대부분의 항목이 빠져 있었다(경복궁 400m 옆에서 반경 1km 를 불러도 경복궁이 없고, 종로구 관광지가 3곳뿐). 항목의 예전 코드 칸이
     비어 있고 법정동 코드와 새 분류(lclsSystm1~3)만 채워져 있기 때문이다. 그래서 시·군·구 목록을 통째로 받아 우리가 거리로 거른다.
     어느 시·군·구인지는 상가정보로 안다: 반경 안 약국(어디에나 고르게 있는 업종)의 시·군·구 코드를 세어 많은 곳부터 고른다(districts_near).
  2) 소상공인시장진흥공단 상가(상권)정보 storeListInRadius — 반경 안 업소(상호·업종 대/중/소분류·주소·좌표). 응답 0.1~1.5초.
     업종 조건(indsLclsCd·indsMclsCd·indsSclsCd)으로 걸러 받을 수 있다. 수는 많지만(성수역 1km 안 음식 1,910곳) 사진·영업시간·평판이 없다.
     업소를 고를 신호가 없어 '지점 표기가 없는 곳 먼저, 가까운 순'으로 종류마다 몇 곳만 쓴다(STORE_CAPS).
  영업 여부는 장소 카드의 '위치' 줄이 행정안전부 인허가 자료로 따로 확인한다(app/place_identity.py, 배경 조회).

공공 API 를 느리고 불안정한 것으로 다룬다(app/place_identity.py 와 같은 태도)
  · 응답은 사용자 공용 캐시(store)에 둔다 — 공공 자료라 사용자 사이에 나눠 써도 된다. 관광공사 목록은 시·군·구와 관광 타입마다 7일,
    상가정보는 좌표를 GRID(약 200m) 격자에 맞춰 7일(분기 자료). 같은 동네의 요청은 같은 캐시를 쓴다.
  · 실패·시간 초과는 후보 없음으로 넘어가고(추천은 카탈로그만으로 계속) 60초 동안 다시 부르지 않는다.
  · 하루 호출 상한(_reserve): 관광공사 개발계정 한도가 하루 1,000건이라 이 모듈의 관광공사 호출을 하루 DATEMATE_TOUR_CANDIDATE_CALLS_PER_DAY
    (기본 600)건으로 막는다(축제·장소 카드 조회 몫을 남김). 넘으면 상가정보와 카탈로그만 쓴다.

후보의 보관
  찾은 후보는 그 사용자의 추천 범위에만 둔다(remember → naver_cache 의 개인화 보관 틀: 24시간, 새 추천 때 비움). 공공 자료라 의무는
  아니고, 이전에 찾은 다른 동네 후보가 카탈로그에 계속 쌓이지 않게 하려는 것이다(app/catalog.py 가 candidates() 를 합친다).
  저장된 코스에는 장소 전체가 들어 있어, 보관이 끝난 뒤의 장소 상세는 그 사용자의 코스에서 찾는다(from_owner_plans).

키: 공공데이터포털 계정 키 하나(TOUR_API_KEY). 로그·캐시·응답에 키를 남기지 않는다.
"""

import hashlib
import json
import logging
import math
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timezone

import httpx

from . import store
from .routes import distance
from .telemetry import observed_http

TOUR_BASE = "https://apis.data.go.kr/B551011/KorService2/"
TOUR_AREA_URL = TOUR_BASE + "areaBasedList2"
TOUR_KEYWORD_URL = TOUR_BASE + "searchKeyword2"
STORE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInRadius"
TOUR_SOURCE_TYPE = "한국관광공사 TourAPI · 공공데이터"
STORE_SOURCE_TYPE = "소상공인시장진흥공단 상가(상권)정보 · 공공데이터"
STORE_DATASET_URL = "https://www.data.go.kr/data/15012005/openapi.do"
ID_PREFIX = "public:"

# 좌표 격자(도). 0.002도 = 남북 약 220m, 동서 약 180m. 격자점에서 부르고 SNAP_MARGIN_M 만큼 넓게 받아 실제 중심의 반경을 덮는다.
GRID = 0.002
SNAP_MARGIN_M = 150
TOUR_PAGE_ROWS = 1000
TOUR_MAX_PAGES = 2
TOUR_TIMEOUT = 10
TOUR_SECONDS = 7 * 86400
# 추천·주변 식당이 쓰는 관광 타입: 관광지·문화시설·레포츠·쇼핑·음식점. 숙박(32)·축제(15)·여행코스(25)는 받지 않는다.
TOUR_TYPES = ("12", "14", "28", "38", "39")
# 한 번에 보는 시·군·구 수. 반경이 구 경계에 걸치면 약국이 많은 곳부터 이만큼(전체의 DISTRICT_SHARE 이상인 곳만).
MAX_DISTRICTS = 3
DISTRICT_SHARE = 0.15
DISTRICT_SECONDS = 30 * 86400
PHARMACY_CODE = "G21501"
STORE_PAGE_ROWS = 1000
STORE_MAX_PAGES = 2
STORE_TIMEOUT = 10
STORE_SECONDS = 7 * 86400
FAIL_SECONDS = 60
# 상가정보 반경(m). 좁은 반경에 업소가 SPARSE_ROWS 곳보다 적으면(읍·면, 해변 등) 넓은 반경으로 한 번 더 찾는다.
SPARSE_ROWS = 8
# 한 추천의 후보에 넣는 수. 관광공사 항목은 가까운 순 TOUR_CAP 곳, 상가정보는 종류마다 STORE_CAPS.
TOUR_CAP = 60
STORE_CAPS = {
    "meal": 8,
    "cafe": 6,
    "game": 6,
    "workshop": 4,
    "book": 3,
    "shopping": 3,
    "rest": 2,
    "jazz": 2,
    "sport": 3,
}
CANDIDATE_PREFIX = "public-candidate:"
NEARBY_PREFIX = "public-nearby:"
# 측정용 누적 수(프로세스 단위). 이름: {tour_district|tour_area|tour_keyword|store|district}_{call|cache|failed|limited}.
STATS = Counter()

log = logging.getLogger(__name__)

# 시·도 → 법정동 시·도 코드(TourAPI lDongRegnCd, 상가정보 ctprvnCd 와 같다. 2026-11-20 응답으로 서울·부산·강원·전북·경북·세종 확인).
REGION_CODES = {
    "서울": "11", "부산": "26", "대구": "27", "인천": "28", "광주": "29", "대전": "30", "울산": "31", "세종": "36110", "경기": "41",
    "강원": "51", "충북": "43", "충남": "44", "전북": "52", "전남": "46", "경북": "47", "경남": "48", "제주": "50",
}  # fmt: skip
# TourAPI 새 분류(lclsSystmCode2 소분류 246개, 2026-11-20 조회) → 우리 장소. 여기에 없는 소분류(숙박·축제·코스·교통시설·면세점·주점·
# 치킨·분식·종교성지 등)는 후보로 쓰지 않는다. 값: (화면·대조용 분류 이름, 우리 활동 분류, 식사 여부, 요청 활동 태그들, 실내외 또는 None).
_T_MEAL = ("카페·미식", True, ("meal",), "indoor")
_T_CAFE = ("카페·미식", False, ("cafe",), "indoor")
_T_HISTORY = ("문화·예술", False, ("museum",), None)
_T_NATURE = ("산책·풍경", False, ("walk",), "outdoor")
_T_PARK = ("산책·풍경", False, ("walk",), "outdoor")
_T_VIEW = ("산책·풍경", False, ("view",), None)
_T_PLAY = ("오락·놀이", False, (), None)
_T_SHOP = ("오락·놀이", False, ("shopping",), None)
_T_CRAFT = ("체험·제작", False, ("workshop",), None)
_T_REST = ("휴식·힐링", False, ("rest",), "indoor")


def _kinds(prefix, kind, names):
    return {code: (prefix + ">" + name, *kind) for code, name in names}


TOUR_KINDS = {
    **_kinds("음식>한식", _T_MEAL, (("FD010100", "관광식당"), ("FD010200", "모범음식점"))),
    **_kinds(
        "음식>외국식",
        _T_MEAL,
        (
            ("FD020100", "중식"),
            ("FD020200", "일식"),
            ("FD020300", "서양식"),
            ("FD020400", "기타외국식"),
            ("FD020500", "퓨전음식"),
        ),
    ),
    "FD030200": ("음식>간이음식>피자·햄버거·샌드위치", *_T_MEAL),
    "FD030100": ("음식>간이음식>제과", *_T_CAFE),
    **_kinds(
        "음식>카페/찻집",
        _T_CAFE,
        (("FD050100", "카페"), ("FD050200", "찻집"), ("FD050300", "기타음료점")),
    ),
    **_kinds(
        "역사관광>역사유적지",
        _T_HISTORY,
        (
            ("HS010100", "고궁"),
            ("HS010200", "성·산성·성곽"),
            ("HS010300", "문"),
            ("HS010400", "고택"),
            ("HS010500", "생가"),
            ("HS010600", "민속마을"),
            ("HS010700", "사적지"),
            ("HS010800", "고분·능"),
            ("HS010900", "사당"),
            ("HS011000", "선사유적지"),
            ("HS011100", "근대건축물"),
            ("HS011200", "기타역사유적지"),
        ),
    ),
    **_kinds(
        "자연관광",
        _T_NATURE,
        (
            ("NA010100", "산·고개·오름"),
            ("NA010200", "숲"),
            ("NA010300", "폭포"),
            ("NA010400", "계곡"),
            ("NA020100", "강"),
            ("NA020200", "호수"),
            ("NA020300", "저수지"),
            ("NA020400", "연못·늪"),
            ("NA020500", "섬"),
            ("NA020700", "항구/포구"),
            ("NA020800", "해안절경"),
            ("NA020900", "해변·해수욕장"),
            ("NA030400", "생태습지"),
            ("NA040100", "국립공원"),
            ("NA040200", "도립공원"),
            ("NA040300", "군립공원"),
            ("NA040400", "지질공원"),
            ("NA040500", "생태관광지"),
            ("NA040600", "자연휴양림"),
            ("NA040700", "수목원·정원"),
        ),
    ),
    **_kinds(
        "문화관광>랜드마크관광",
        _T_VIEW,
        (("VE010100", "건물"), ("VE010200", "타워/전망대"), ("VE010800", "등대")),
    ),
    "VE010300": (
        "문화관광>랜드마크관광>다리/대교",
        "산책·풍경",
        False,
        ("walk", "view"),
        "outdoor",
    ),
    **_kinds(
        "문화관광>테마공원",
        _T_PLAY,
        (("VE020100", "테마파크"), ("VE020200", "워터파크"), ("VE020300", "동물원")),
    ),
    "VE020400": ("문화관광>테마공원>수족관/아쿠아리움", "오락·놀이", False, (), "indoor"),
    "VE020500": ("문화관광>테마공원>천문대", "문화·예술", False, ("museum",), None),
    **_kinds(
        "문화관광>도시공원",
        _T_PARK,
        (
            ("VE030100", "시민공원"),
            ("VE030200", "소공원"),
            ("VE030400", "근린공원"),
            ("VE030500", "주제공원"),
        ),
    ),
    **_kinds(
        "문화관광>도시·지역문화관광",
        _T_PARK,
        (("VE040100", "골목길·문화거리"), ("VE040200", "마을관광지"), ("VE040300", "둘레길")),
    ),
    "VE060100": ("문화관광>공연시설>공연장", "문화·예술", False, ("performance",), "indoor"),
    "VE060200": ("문화관광>공연시설>영화관", "문화·예술", False, ("cinema",), "indoor"),
    "VE070100": ("문화관광>전시시설>박물관", "문화·예술", False, ("museum", "culture"), "indoor"),
    "VE070200": ("문화관광>전시시설>기념관", "문화·예술", False, ("museum",), "indoor"),
    "VE070300": ("문화관광>전시시설>전시관", "문화·예술", False, ("culture",), "indoor"),
    "VE070500": ("문화관광>전시시설>과학관", "문화·예술", False, ("museum",), "indoor"),
    "VE070600": ("문화관광>전시시설>미술관/화랑", "문화·예술", False, ("culture",), "indoor"),
    "VE090300": ("문화관광>교육시설>도서관", "문화·예술", False, ("book",), "indoor"),
    "VE090400": ("문화관광>교육시설>문화전수시설", "문화·예술", False, ("culture",), "indoor"),
    "VE120100": ("문화관광>기타문화관광지>서점", "문화·예술", False, ("book",), "indoor"),
    "VE120300": (
        "문화관광>기타문화관광지>기타문화시설",
        "문화·예술",
        False,
        ("culture",),
        "indoor",
    ),
    "EX010100": ("체험관광>전통체험>전통문화체험", *_T_CRAFT),
    **_kinds(
        "체험관광>공예체험",
        _T_CRAFT,
        (
            ("EX020100", "금속공예체험"),
            ("EX020200", "유리공예체험"),
            ("EX020300", "가죽공예체험"),
            ("EX020400", "기타공예체험"),
        ),
    ),
    "EX070200": ("체험관광>기타체험>기타체험관광", *_T_CRAFT),
    **_kinds(
        "체험관광>웰니스관광",
        _T_REST,
        (("EX050100", "온천/사우나/스파"), ("EX050200", "찜질방"), ("EX050500", "뷰티스파")),
    ),
    "EX070100": (
        "체험관광>기타체험>유람선/잠수함관광",
        "레저·활동",
        False,
        ("boating",),
        "outdoor",
    ),
    "SH010100": ("쇼핑>백화점", "오락·놀이", False, ("shopping",), "indoor"),
    "SH020100": ("쇼핑>쇼핑몰>복합쇼핑몰", "오락·놀이", False, ("shopping",), "indoor"),
    "SH020200": ("쇼핑>쇼핑몰>아웃렛", *_T_SHOP),
    "SH050100": ("쇼핑>전문매장/상가>공방/공예품점", "체험·제작", False, ("workshop",), "indoor"),
    "SH050300": ("쇼핑>전문매장/상가>관광기념품/특산물판매점", *_T_SHOP),
    "SH060100": ("쇼핑>시장>비상설시장", *_T_SHOP),
    "SH060200": ("쇼핑>시장>상설시장", *_T_SHOP),
}
# 레저스포츠(LS…)와 스포츠센터는 소분류 이름과 상호로 종목을 정한다(app/sports.classify). 종목을 모르면 후보로 쓰지 않는다.
TOUR_LEISURE = {
    "LS010100": "인라인", "LS010200": "자전거하이킹", "LS010300": "카트", "LS010700": "승마", "LS010800": "스키/스노보드",
    "LS010900": "스케이트", "LS011000": "썰매장", "LS011200": "사격장", "LS011300": "암벽등반", "LS011900": "기타육상레저스포츠",
    "LS020100": "윈드서핑/제트스키", "LS020200": "카약/카누", "LS020300": "요트", "LS020500": "민물낚시", "LS020600": "바다낚시",
    "LS020700": "수영", "LS021400": "기타수상레저스포츠", "LS030300": "헹글라이딩/패러글라이딩", "LS040100": "복합레저스포츠",
    "VE100200": "스포츠센터",
}  # fmt: skip

# 상가정보 소분류(smallUpjongList, 2026-11-20 조회) → (종류, 우리 활동 분류, 식사 여부, 실내외, 상호에 있어야 하는 낱말 정규식 또는 None).
# 여기에 없는 소분류(구내식당, 김밥·분식, 치킨, 주점, 헬스장, PC방, 노래방, 복권 등)는 후보로 쓰지 않는다.
_MEAL = ("meal", "카페·미식", True, "indoor", None)
_CAFE = ("cafe", "카페·미식", False, "indoor", None)
# 상호에 이 낱말이 있어야 공방·놀이 장소로 본다. 2026-11-20 서울 표본에서 '…미술교습소'·'…화실'(강습)과 '○○게임'(성인 게임장)이
# 공방·방탈출 요청의 후보로 뽑혀, 강습·학원 낱말이 있으면 빼고(_NOT_VENUE) '게임'만으로는 받지 않게 좁혔다.
_CRAFT_CUE = r"공방|도자|도예|원데이|클래스|캔들|향수|가죽|목공|플라워|베이킹|쿠킹|반지|공예"
_GAME_CUE = r"방탈출|이스케이프|escape|보드게임|보드카페|보드 게임|오락실|VR|브이알|아케이드|만화카페|만화방"
STORE_KINDS = {
    **{code: _MEAL for code in (
        "I20101", "I20102", "I20103", "I20104", "I20105", "I20106", "I20107", "I20108", "I20109", "I20110", "I20111",
        "I20112", "I20113", "I20199", "I20201", "I20202", "I20301", "I20302", "I20303", "I20399", "I20401", "I20402",
        "I20403", "I20499", "I20501", "I20599", "I20601", "I21003", "I21004",
    )},
    "I21201": _CAFE,
    "I21001": _CAFE,
    "I21008": _CAFE,
    "I21101": ("jazz", "문화·예술", False, "indoor", r"재즈|jazz"),
    "I21103": ("jazz", "문화·예술", False, "indoor", r"재즈|jazz"),
    "I21104": ("jazz", "문화·예술", False, "indoor", r"재즈|jazz"),
    "R10404": ("game", "오락·놀이", False, "indoor", _GAME_CUE),
    "R10405": ("game", "오락·놀이", False, "indoor", _GAME_CUE),
    "R10499": ("game", "오락·놀이", False, "indoor", _GAME_CUE),
    "N11003": ("game", "오락·놀이", False, "indoor", None),
    "P10611": ("workshop", "체험·제작", False, "indoor", _CRAFT_CUE),
    "P10613": ("workshop", "체험·제작", False, "indoor", _CRAFT_CUE),
    "G21301": ("book", "문화·예술", False, "indoor", None),
    "G21802": ("shopping", "오락·놀이", False, "indoor", None),
    "S20801": ("rest", "휴식·힐링", False, "indoor", r"찜질|스파|온천|사우나"),
}  # fmt: skip
# 스포츠 시설 소분류: 종목은 소분류 이름과 상호로 정한다(app/sports.classify). 헬스장·골프 연습장도 상호에 종목이 있으면 쓴다.
STORE_SPORT_CODES = {
    "R10306": "종합 스포츠시설", "R10307": "헬스장", "R10308": "수영장", "R10309": "볼링장", "R10310": "당구장",
    "R10311": "골프 연습장", "R10312": "테니스장", "R10313": "탁구장", "R10314": "기타 스포츠시설 운영업",
    "R10316": "스쿼시/라켓볼장", "R10405": "기타 오락장", "R10408": "낚시터 운영업", "R10409": "수상/해양 레저업",
    "R10499": "기타 오락관련 서비스업",
}  # fmt: skip
# 상가정보를 받는 묶음: (업종 조건들, 좁은 반경 m, 넓은 반경 m). 음식은 대분류 하나로 식당·카페·주점을 한 번에 받는다.
# 업소가 많은 묶음(음식·예술스포츠)만 좁은 반경부터 받고, 드문 업종은 처음부터 한 반경으로 받는다(두 반경이 같으면 한 번만 부른다).
SHEETS = {
    "food": ((("indsLclsCd", "I2"),), 600, 2000),
    "play": ((("indsLclsCd", "R1"),), 1500, 3000),
    "comic": ((("indsSclsCd", "N11003"),), 2000, 2000),
    "craft": ((("indsSclsCd", "P10613"), ("indsSclsCd", "P10611")), 2000, 2000),
    "book": ((("indsSclsCd", "G21301"),), 2000, 2000),
    "gift": ((("indsSclsCd", "G21802"),), 1500, 1500),
    "bath": ((("indsSclsCd", "S20801"),), 3000, 3000),
}
# 요청 활동·부족한 종류 → 상가정보 묶음. 전시·박물관·영화·공연·산책·전망은 상가정보에 없어 관광공사 자료와 카탈로그만 쓴다.
KIND_SHEETS = {
    "meal": ("food",), "cafe": ("food",), "jazz": ("food",), "game": ("play", "comic"), "activity": ("play",),
    "workshop": ("craft",), "book": ("book",), "shopping": ("gift",), "rest": ("bath",),
}  # fmt: skip
_BAD_NAME = re.compile(r"업소명\s*없음|^\W*$")
# 상가정보의 상호는 사업자 등록 이름이라 간판과 다를 수 있다. 회사 이름으로 보이는 상호(지도에서 찾기 어려움)와 강습·학원은 후보에서 뺀다.
_NOT_VENUE = re.compile(
    r"(푸드|에프앤비|F&B|컴퍼니|코리아|엔터테인먼트|유통|상사|식품|글로벌|홀딩스|인터내셔널|본사|물산|산업|개발)$"
    r"|교습소|학원|입시|협회|사무소|사무실",
    re.I,
)
_CORPORATE = re.compile(r"주식회사|유한회사|\(주\)|㈜|\(유\)")


def _key():
    """공공데이터포털 계정 키. .env 에 작은따옴표로 감싸 둔 경우도 받는다."""
    return os.getenv("TOUR_API_KEY", "").strip().strip("'\"")


def enabled():
    return bool(_key())


def is_public(place):
    return isinstance(place, dict) and str(place.get("id") or "").startswith(ID_PREFIX)


def snap(lat, lon):
    return round(round(lat / GRID) * GRID, 4), round(round(lon / GRID) * GRID, 4)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _reserve(api):
    """이 모듈의 하루 호출 상한. 넘으면 False(부르지 않음). 상한 확인이 실패하면 부르는 쪽으로 둔다(시간당 제공자 예산은 따로 있다)."""
    names = {
        "tour": ("DATEMATE_TOUR_CANDIDATE_CALLS_PER_DAY", 600),
        "store": ("DATEMATE_STORE_INFO_CALLS_PER_DAY", 5000),
    }
    env, default = names[api]
    try:
        limit = max(0, int(os.getenv(env, str(default)) or default))
    except ValueError:
        limit = default
    try:
        return store.reserve_budget([("public-api:" + api, limit)], int(time.time() // 86400))
    except Exception:
        log.warning("public_api_budget_check_failed api=%s", api)
        return True


def daily_calls():
    """오늘(UTC 날짜 구간) 이 모듈이 부른 공공 API 수. 운영 확인용."""
    with store.connect() as db:
        rows = db.execute(
            "SELECT scope,calls FROM request_budgets WHERE scope LIKE 'public-api:%' AND bucket=?",
            (int(time.time() // 86400),),
        ).fetchall()
    return {row[0].removeprefix("public-api:"): int(row[1]) for row in rows}


def _hit(name):
    STATS[name + "_cache"] += 1
    from .request_usage import cache_hit

    cache_hit("public_" + name)


# ---------------------------------------------------------------- 한국관광공사


def _tour_image(item):
    """(사진 주소, 공공누리 유형). 공공누리 제1·제3유형이고 관광공사 사진 호스트일 때만(app/tour_places.py 와 같은 규칙)."""
    from .festivals import IMAGE_HOST, festival_image

    upgraded = {
        field: "https://" + str(item[field])[len("http://") :]
        for field in ("firstimage", "firstimage2")
        if str(item.get(field) or "").startswith("http://" + IMAGE_HOST + "/")
    }
    return festival_image(dict(item, **upgraded))


def _tour_row(item):
    """TourAPI 목록 항목 → 캐시에 둘 작은 행. 쓸 수 없으면 None."""
    try:
        lat, lon = float(item["mapy"]), float(item["mapx"])
    except (KeyError, TypeError, ValueError):
        return None
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
    content_id = str(item.get("contentid") or "")
    if not title or not content_id.isdigit() or not (33 <= lat <= 39 and 124 <= lon <= 132):
        return None
    photo, license_type = _tour_image(item)
    return dict(
        id=content_id,
        type=str(item.get("contenttypeid") or ""),
        lcls=str(item.get("lclsSystm3") or ""),
        title=title[:120],
        address=re.sub(r"\s+", " ", str(item.get("addr1") or "")).strip()[:200],
        lat=lat,
        lon=lon,
        photo=photo,
        license=license_type if photo else None,
        modified=str(item.get("modifiedtime") or "")[:8],
    )


def _tour_fetch(kind, url, key, params, ttl=TOUR_SECONDS, pages=1):
    """TourAPI 목록 하나를 공용 캐시를 거쳐 받는다(pages 쪽까지). dict(status, rows, checked_at)."""
    hit = store.cached(key)
    if hit is not None:
        _hit(kind)
        return hit
    if not _key():
        return dict(status="key_missing", rows=[])
    rows = []
    try:
        for page in range(1, pages + 1):
            if not _reserve("tour"):
                STATS[kind + "_limited"] += 1
                if rows:
                    break
                return dict(status="limited", rows=[])
            STATS[kind + "_call"] += 1
            response = observed_http(
                httpx.get,
                url,
                params=dict(
                    params,
                    serviceKey=_key(),
                    MobileOS="ETC",
                    MobileApp="DateMate",
                    _type="json",
                    pageNo=page,
                ),
                timeout=TOUR_TIMEOUT,
            )
            response.raise_for_status()
            if len(response.content) > 4_000_000:
                raise ValueError("oversized_response")
            body = (response.json().get("response") or {}).get("body") or {}
            from .tour_places import _items

            items = _items(response)
            rows.extend(row for row in map(_tour_row, items) if row)
            if (
                page * int(params.get("numOfRows") or 0) >= int(body.get("totalCount") or 0)
                or not items
            ):
                break
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        STATS[kind + "_failed"] += 1
        failed = dict(status="unavailable", rows=[])
        store.cache(key, failed, FAIL_SECONDS)
        return failed
    result = dict(status="available", rows=rows, checked_at=date.today().isoformat())
    store.cache(key, result, ttl)
    return result


def district_parts(code):
    """상가정보 시·군·구 코드(5자리) → TourAPI (lDongRegnCd, lDongSignguCd). 세종은 두 칸 모두 36110 이다(2026-11-20 응답)."""
    code = str(code or "")
    if not re.fullmatch(r"\d{5}", code):
        return None
    return ("36110", "36110") if code.startswith("36") else (code[:2], code[2:])


def districts_near(lat, lon, radius_km):
    """(lat, lon) 반경에 걸친 시·군·구 코드들(상가정보 5자리), 많이 걸친 곳부터 최대 MAX_DISTRICTS. dict(status, districts).

    좌표로 행정구역을 알려 주는 공공 API 를 따로 쓰지 않고, 상가정보 반경 조회로 약국(어디에나 고르게 있는 업종)의 시·군·구 코드를 센다.
    약국이 하나도 없는 외진 곳은 5km 로 한 번 더 본다. 30일 보관(행정구역은 거의 바뀌지 않는다)."""
    slat, slon = snap(lat, lon)
    radius = int(min(max(radius_km * 1000, 1000), 3000) + SNAP_MARGIN_M)
    key = f"public-district-v1:{slat}:{slon}:{radius}"
    hit = store.cached(key)
    if hit is not None:
        _hit("district")
        return hit
    if not _key():
        return dict(status="key_missing", districts=[])
    counts = Counter()
    try:
        for reach in (radius, 5000):
            if not _reserve("store"):
                STATS["district_limited"] += 1
                raise ValueError("daily_limit")
            STATS["district_call"] += 1
            response = observed_http(
                httpx.get,
                STORE_URL,
                params=dict(
                    serviceKey=_key(),
                    radius=reach,
                    cx=slon,
                    cy=slat,
                    type="json",
                    numOfRows=STORE_PAGE_ROWS,
                    pageNo=1,
                    indsSclsCd=PHARMACY_CODE,
                ),
                timeout=STORE_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            code = str((data.get("header") or {}).get("resultCode") or "")
            if code not in ("00", "03"):
                raise ValueError("provider_error")
            for item in (data.get("body") or {}).get("items") or []:
                if isinstance(item, dict) and district_parts(item.get("signguCd")):
                    counts[str(item["signguCd"])] += 1
            if counts:
                break
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        STATS["district_failed"] += 1
        failed = dict(status="unavailable", districts=[])
        store.cache(key, failed, FAIL_SECONDS)
        return failed
    total = sum(counts.values())
    picked = [code for code, n in counts.most_common(MAX_DISTRICTS) if n >= total * DISTRICT_SHARE]
    result = dict(status="available" if picked else "not_found", districts=picked)
    store.cache(key, result, DISTRICT_SECONDS if picked else 86400)
    return result


def tour_district(code, content_type):
    """시·군·구(상가정보 5자리 코드) 하나의 한 관광 타입 목록 전체. dict(status, rows)."""
    parts = district_parts(code)
    if not parts:
        return dict(status="unavailable", rows=[])
    params = dict(
        lDongRegnCd=parts[0],
        lDongSignguCd=parts[1],
        contentTypeId=content_type,
        arrange="A",
        numOfRows=TOUR_PAGE_ROWS,
    )
    return _tour_fetch(
        "tour_district",
        TOUR_AREA_URL,
        f"public-tour-district-v1:{code}:{content_type}",
        params,
        pages=TOUR_MAX_PAGES,
    )


def tour_near(lat, lon, radius_km, types=TOUR_TYPES):
    """(lat, lon) 반경 radius_km 안의 관광공사 항목, 가까운 순. dict(status, rows, districts).

    반경에 걸친 시·군·구(districts_near)의 목록을 타입마다 받아(공용 캐시 7일) 거리로 거른다. 처음 보는 시·군·구는 타입 수만큼 호출이 든다."""
    from concurrent.futures import ThreadPoolExecutor
    from .request_usage import context_map

    found = districts_near(lat, lon, radius_km)
    if not found.get("districts"):
        return dict(
            status=found.get("status") if found.get("status") != "available" else "not_found",
            rows=[],
            districts=[],
        )
    jobs = [(code, content_type) for code in found["districts"] for content_type in types]
    # 이미 받아 둔 목록은 한 번의 DB 조회로 읽고(대부분의 추천이 여기서 끝난다), 없는 것만 나눠 받는다.
    keys = {job: f"public-tour-district-v1:{job[0]}:{job[1]}" for job in jobs}
    known = store.cached_many(keys.values())
    missing = [job for job in jobs if keys[job] not in known]
    for _ in range(len(jobs) - len(missing)):
        _hit("tour_district")
    fetched = {}
    if missing:
        with ThreadPoolExecutor(max_workers=4) as pool:
            fetched = dict(
                zip(missing, context_map(pool, lambda job: tour_district(*job), missing))
            )
    lists = [
        known.get(keys[job]) or fetched.get(job) or dict(status="unavailable", rows=[])
        for job in jobs
    ]
    center, rows, seen = dict(lat=lat, lon=lon), [], set()
    for data in lists:
        for row in data.get("rows") or []:
            if row["id"] in seen:
                continue
            km = distance(center, row)
            if km <= radius_km:
                seen.add(row["id"])
                rows.append((km, row["id"], row))
    statuses = [data.get("status") for data in lists]
    status = (
        "available"
        if "available" in statuses
        else "limited"
        if "limited" in statuses
        else "unavailable"
    )
    return dict(
        status=status,
        rows=[row for _, _, row in sorted(rows, key=lambda r: r[:2])],
        districts=found["districts"],
    )


def _lcls_params(prefix):
    """새 분류 조건: 'FD' / 'FD05' / 'FD050100' → lclsSystm1~3."""
    prefix = str(prefix or "")
    names = (("lclsSystm1", 2), ("lclsSystm2", 4), ("lclsSystm3", 8))
    return {name: prefix[:size] for name, size in names if len(prefix) >= size}


def tour_area(region, content_type=None, lcls=None, rows=60):
    """시·도의 관광공사 항목(수정일 최신순, 대표 사진 있는 것). 둘러보기 기본 목록. content_type·lcls(새 분류 앞부분)로 좁힌다."""
    code = REGION_CODES.get(region)
    if not code:
        return dict(status="unavailable", rows=[])
    params = dict(lDongRegnCd=code, arrange="Q", numOfRows=rows, **_lcls_params(lcls))
    if content_type:
        params["contentTypeId"] = content_type
    return _tour_fetch(
        "tour_area",
        TOUR_AREA_URL,
        f"public-tour-area-v2:{code}:{content_type or 'all'}:{lcls or 'all'}:{rows}",
        params,
        ttl=86400,
    )


def tour_keyword(region, keyword, rows=60):
    """시·도 안에서 이름에 keyword 가 든 관광공사 항목(수정일 최신순). 둘러보기 검색어."""
    code = REGION_CODES.get(region)
    keyword = " ".join(str(keyword or "").split())[:60]
    if not code or len(keyword) < 2:
        return dict(status="unavailable", rows=[])
    digest = hashlib.sha256(keyword.casefold().encode()).hexdigest()[:24]
    params = dict(lDongRegnCd=code, keyword=keyword, arrange="Q", numOfRows=rows)
    return _tour_fetch(
        "tour_keyword",
        TOUR_KEYWORD_URL,
        f"public-tour-keyword-v2:{code}:{digest}:{rows}",
        params,
        ttl=86400,
    )


def tour_place(row, region=None):
    """캐시 행 → 장소. 후보로 쓰지 않는 분류이거나 다른 시·도면 None."""
    from . import sports
    from .regions import region_from_address

    found = region_from_address(row.get("address"))
    if region and found != region:
        return None
    lcls, tags, setting = row.get("lcls") or "", [], None
    if lcls in TOUR_KINDS:
        label, category, meal, keys, setting = TOUR_KINDS[lcls]
        tags = list(keys)
    elif lcls in TOUR_LEISURE:
        label = "레포츠>" + TOUR_LEISURE[lcls]
        sport = sports.classify(label, row["title"])
        if not sport:
            return None
        category, meal, tags = "레저·활동", False, [sport.key]
        setting = sports.setting_of(sport, row["title"] + " " + label)[0]
    else:
        return None
    content_id = row["id"]
    kind = "제1유형" if row.get("license") == "Type1" else "제3유형(변경 금지)"
    return dict(
        id=f"{ID_PREFIX}tour-{content_id}", name=row["title"], address=row.get("address") or None, lat=row["lat"], lon=row["lon"],
        region=found or region, demo=False, category=category, themes=[category], tags=[*tags, label], meal=meal,
        description=label, source=f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={content_id}",
        source_type=TOUR_SOURCE_TYPE, license="공공누리(한국관광공사 관광정보)", public_source="tour",
        tour_content_id=content_id, tour_content_type=row.get("type") or "",
        tour_photo=row.get("photo"), tour_photo_license=("공공누리 " + kind) if row.get("photo") else None,
        checked_at=_now(), discovery_verification="한국관광공사 관광정보의 이름·분류·주소·좌표 · 영업 여부·영업시간은 확인 필요",
        price=None, price_unit="person", hours=None, closed_days=None, breaks=None, last_entry=None, reservation=None,
        stay=None, stay_basis=None, rating=None, setting=setting, photos=[], videos=[],
    )  # fmt: skip


# ---------------------------------------------------------------- 상가정보


def _store_row(item):
    """상가정보 업소 → 캐시에 둘 작은 행. 후보로 쓰지 않는 업종이면 None."""
    code = str(item.get("indsSclsCd") or "")
    if code not in STORE_KINDS and code not in STORE_SPORT_CODES:
        return None
    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    name = re.sub(r"\s+", " ", str(item.get("bizesNm") or "")).strip()
    biz_id = str(item.get("bizesId") or "")
    if (
        not biz_id
        or not name
        or _BAD_NAME.search(name)
        or not (33 <= lat <= 39 and 124 <= lon <= 132)
    ):
        return None
    return dict(
        id=biz_id[:40],
        name=name[:80],
        branch=re.sub(r"\s+", " ", str(item.get("brchNm") or "")).strip()[:40],
        code=code,
        label=str(item.get("indsSclsNm") or "").strip()[:40],
        address=str(item.get("rdnmAdr") or item.get("lnoAdr") or "").strip()[:200],
        lat=lat,
        lon=lon,
    )


def _store_call(params, slat, slon, radius):
    """상가정보 반경 조회 한 조건. (행 목록, 자료 기준 연월, 다 받지 못했는지). 실패하면 예외."""
    rows, month, total = [], None, 0
    for page in range(1, STORE_MAX_PAGES + 1):
        if not _reserve("store"):
            STATS["store_limited"] += 1
            raise ValueError("daily_limit")
        STATS["store_call"] += 1
        response = observed_http(
            httpx.get,
            STORE_URL,
            params=dict(
                params,
                serviceKey=_key(),
                radius=radius,
                cx=slon,
                cy=slat,
                type="json",
                numOfRows=STORE_PAGE_ROWS,
                pageNo=page,
            ),
            timeout=STORE_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        header = data.get("header") or {}
        code = str(header.get("resultCode") or "")
        if code == "03":  # NODATA_ERROR: 반경 안에 그 업종이 없다.
            break
        if code != "00":
            raise ValueError("provider_error")
        body = data.get("body") or {}
        items = body.get("items") or []
        if not isinstance(items, list):
            raise ValueError("invalid_response")
        month = month or str(header.get("stdrYm") or "") or None
        total = int(body.get("totalCount") or 0)
        rows.extend(row for row in map(_store_row, items) if row)
        if page * STORE_PAGE_ROWS >= total or not items:
            break
    return rows, month, total > STORE_MAX_PAGES * STORE_PAGE_ROWS


def store_sheet(sheet, lat, lon, radius_m):
    """상가정보 묶음 하나(격자점 반경 radius_m + 여유)를 공용 캐시를 거쳐 받는다. dict(status, rows, data_month, truncated)."""
    conditions = SHEETS[sheet][0]
    slat, slon = snap(lat, lon)
    radius = int(radius_m + SNAP_MARGIN_M)
    key = f"public-store-v1:{sheet}:{slat}:{slon}:{radius}"
    hit = store.cached(key)
    if hit is not None:
        _hit("store")
        return hit
    if not _key():
        return dict(status="key_missing", rows=[])
    rows, month, truncated = {}, None, False
    try:
        for name, value in conditions:
            found, stamp, cut = _store_call({name: value}, slat, slon, radius)
            rows.update((row["id"], row) for row in found)
            month, truncated = month or stamp, truncated or cut
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        STATS["store_failed"] += 1
        failed = dict(status="unavailable", rows=[])
        store.cache(key, failed, FAIL_SECONDS)
        return failed
    result = dict(
        status="available",
        rows=list(rows.values()),
        data_month=month,
        truncated=truncated,
        checked_at=date.today().isoformat(),
    )
    store.cache(key, result, STORE_SECONDS)
    return result


def stores_near(sheet, lat, lon):
    """묶음의 좁은 반경을 받고, 업소가 드문 곳이면 넓은 반경으로 한 번 더 받는다. (결과, 쓴 반경 m)."""
    _, narrow, wide = SHEETS[sheet]
    found = store_sheet(sheet, lat, lon, narrow)
    if wide <= narrow:
        return found, narrow
    center = dict(lat=lat, lon=lon)
    close = [row for row in found.get("rows", []) if distance(center, row) * 1000 <= narrow]
    if found.get("status") == "available" and len(close) < SPARSE_ROWS:
        return store_sheet(sheet, lat, lon, wide), wide
    return found, narrow


def store_place(row, region=None, month=None):
    """캐시 행 → (종류, 장소). 후보로 쓰지 않는 업소이거나 다른 시·도면 None."""
    from . import sports
    from .regions import region_from_address

    found = region_from_address(row.get("address"))
    if region and found != region:
        return None
    name = (
        row["name"]
        + (" " + row["branch"] if row.get("branch") and row["branch"] not in row["name"] else "")
    ).strip()
    code, label = row["code"], row.get("label") or ""
    if _NOT_VENUE.search(row["name"]):
        return None
    kind = tag = None
    if code in STORE_SPORT_CODES:
        text = (
            "유원지·오락>" if code.startswith("R104") else "스포츠 서비스>"
        ) + STORE_SPORT_CODES[code]
        sport = sports.classify(text, name)
        if sport:
            kind, tag, category, meal = "sport", sport.key, "레저·활동", False
            setting = sports.setting_of(sport, name + " " + text)[0]
    if kind is None:
        if code not in STORE_KINDS:
            return None
        kind, category, meal, setting, cue = STORE_KINDS[code]
        if cue and not re.search(cue, name, re.I):
            return None
        tag = kind
    stamp = (
        f"{month[:4]}년 {int(month[4:])}월 자료"
        if month and re.fullmatch(r"\d{6}", month)
        else "분기 자료"
    )
    place = dict(
        id=f"{ID_PREFIX}store-{row['id']}", name=name, address=row.get("address") or None, lat=row["lat"], lon=row["lon"],
        region=found or region, demo=False, category=category, themes=[category], tags=[tag, label], meal=meal,
        description=label, source=STORE_DATASET_URL, source_type=STORE_SOURCE_TYPE, license="공공데이터(이용허락범위 제한 없음)",
        public_source="store", store_data_month=month, branch=bool(row.get("branch")),
        checked_at=_now(), discovery_verification=f"소상공인 상가정보({stamp})의 상호·업종·주소·좌표 · 영업 여부·영업시간은 확인 필요",
        price=None, price_unit="person", hours=None, closed_days=None, breaks=None, last_entry=None, reservation=None,
        stay=None, stay_basis=None, rating=None, setting=setting, photos=[], videos=[],
    )  # fmt: skip
    return kind, place


def _name_key(name):
    return re.sub(r"[\W_]+", "", _CORPORATE.sub(" ", str(name or ""))).casefold()


def same_venue(a, b):
    """같은 가게로 볼지: 이름(띄어쓰기·기호 무시)이 같고 150m 안, 또는 한쪽 이름이 다른 쪽을 품고(3자 이상) 50m 안."""
    x, y = _name_key(a.get("name")), _name_key(b.get("name"))
    if not x or not y:
        return False
    km = distance(a, b)
    return (x == y and km <= 0.15) or (
        min(len(x), len(y)) >= 3 and (x in y or y in x) and km <= 0.05
    )


def pick_stores(rows, center, caps, taken=(), within_km=None):
    """상가정보 장소 (종류, 장소) 목록에서 종류마다 caps 만큼 고른다: 지점 표기가 없는 곳 먼저, 가까운 순.
    taken(이미 있는 장소)과 같은 가게, 고른 것끼리 같은 가게는 뺀다. sport 는 종목마다 caps['sport'] 곳. (종류, 장소) 목록을 돌려준다."""
    ranked = sorted(
        rows,
        key=lambda pair: (bool(pair[1].get("branch")), distance(center, pair[1]), pair[1]["id"]),
    )
    counts, chosen = Counter(), []
    for kind, place in ranked:
        slot = (kind, place["tags"][0]) if kind == "sport" else kind
        if counts[slot] >= caps.get(kind, 0):
            continue
        if within_km is not None and distance(center, place) > within_km:
            continue
        if any(same_venue(place, other) for other in [*taken, *(p for _, p in chosen)]):
            continue
        counts[slot] += 1
        chosen.append((kind, place))
    return chosen


# ---------------------------------------------------------------- 사용자별 후보 보관


def remember(places, prefix=CANDIDATE_PREFIX):
    """찾은 후보를 이 사용자의 추천 범위에 둔다(24시간, 새 추천 때 비움). catalog.places('real') 이 CANDIDATE_PREFIX 를 합친다."""
    from . import naver_cache

    naver_cache.cache_many(
        [(prefix + place["id"], place, naver_cache.PERSONAL_MAX_SECONDS) for place in places]
    )


def candidates():
    from . import naver_cache

    return list(naver_cache.owned_values(CANDIDATE_PREFIX).values())


def from_owner_plans(place_id):
    """같은 사용자의 저장 코스에 있는 공공 자료 장소. 없으면 None."""
    from . import naver_cache

    owner = naver_cache.current_owner()
    if (
        not owner
        or not str(place_id).startswith(ID_PREFIX)
        or not re.fullmatch(r"[A-Za-z0-9:\-]{1,80}", str(place_id))
    ):
        return None
    with store.connect() as db:
        rows = db.execute(
            "SELECT payload FROM plans WHERE owner=? AND payload LIKE ? ORDER BY created DESC LIMIT 3",
            (owner, '%"id": "' + place_id + '"%'),
        ).fetchall()
    for row in rows:
        try:
            plan = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        for place in plan.get("places") or []:
            if place.get("id") == place_id:
                return place
    return None


def lookup(place_id):
    """추천 후보 밖에서 장소 하나를 id 로 찾는다: 주변 식당으로 보여 준 곳(24시간) → 둘러보기 목록(공용, app/explore.py) → 저장 코스."""
    from . import naver_cache

    if not str(place_id).startswith(ID_PREFIX):
        return None
    return (
        naver_cache.cached(NEARBY_PREFIX + place_id)
        or naver_cache.cached(CANDIDATE_PREFIX + place_id)
        or store.cached("public-place:" + place_id)
        or from_owner_plans(place_id)
    )
