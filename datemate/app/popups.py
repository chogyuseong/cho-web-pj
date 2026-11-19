"""팝업 후보 판정용 순수 함수. 1단계(1a)부터 app/popup_api.py 가 운영 경로에서 쓴다.

입력은 검색 API 가 돌려준 제목·요약·URL·출처 날짜뿐이다. 원문을 읽었다고 가정하지 않는다.
- normalize_text: 태그·엔티티를 텍스트로
- extract_period: 날짜 후보 → 달력 검사 → 행사 기간 문맥 → 연도·범위 불확실성 → 근거 보존
- visit_status: 7절 방문일 상태 표
- match_hubs: 8절 거점 매칭(긴 별칭 우선, 여러 거점이면 단일 장소로 강제하지 않음)
- classify_roundup: 9절 모아 보기 분류
- event_name / group_posts: 행사명 식별과 묶기. 0단계 측정용으로 남겨 두며, 운영 경로(API·화면)에서는 글을 묶거나 이름을 싣는 데 쓰지 않는다
  (1단계 확정 사항: 출처 하나 = 항목 하나). 2026-11-19 부터 event_name 은 대표 사진 검색어를 만드는 데만 쓴다(photo_title_match).

규칙 v1(2026-11-14, 0단계 보고 8절 후보 중 사용자가 고른 것):
- 기간: 괄호 없는 요일("25일 수요일~"), "11월6일에서 11월19일까지", 두 자리 연도 "26년 11월 13일",
  팝업 문맥이 없는 '오픈'·매장 개점일은 행사 기간으로 쓰지 않음.
- 거점: 별칭 안 띄어쓰기 허용("롯데백화점 부산 본점"), "지난번 …에 이어"·"… 이랑은" 같은 지난·비교 문맥의 거점은 단일 매칭에서 뺌,
  지역 검색(좌표 확인)에서 건물 거점은 백화점·쇼핑시설 업종 항목을 먼저 봄.

규칙 v2(2026-11-15, 팝업스토어가 아닌 글이 섞이던 문제: 앱 추천코드 글의 "메인 팝업" 한 마디로 통과한 KFC 사례):
- 팝업 행사 증거(popup_evidence): '팝업' 글자만으로 보여 주지 않고 증거 점수로 정한다. 제목의 행사 표현(팝업스토어·팝업샵·
  팝업존·pop-up store·"팝업 열렸다"·"11월 팝업" 등) 4, 제목의 '팝업' 2, 요약의 행사 표현 2, 요약의 '팝업' 1, 기간 1,
  같은 지역 거점 1, 앱 가입·초대 홍보 낱말(추천코드·친구 초대·회원가입 등) −2.
  2점 이상만 보여 준다. 화면 요소·다른 물건의 '팝업'(메인 팝업, 팝업창, 팝업 차단, 팝업북, 팝업 텐트 등)은 증거로 세지 않는다.
- 뺀 글은 '팝업'이 없는 글과 같이 not_popup 으로 센다. 제목·요약에 '팝업'이 없는 글의 처리(has_popup)는 그대로.

규칙 v3(2026-11-16, 팝업이 글의 주제가 아닌 글이 섞이던 문제: 맛집·카페·주차·뉴스 글 요약에 "근처 팝업스토어를 구경하다가"처럼
지나가듯 나온 '팝업'이 서울의 흔한 거점 낱말(성수·더현대 서울) 점수로 통과한 사례들):
- 제목에 팝업 언급이 없으면 요약의 언급은 글의 주제라는 근거가 있을 때만 센다(없으면 거점 점수로도 구제하지 않음, no_topic).
  근거: 기간이 읽힘, 요약의 행사 서술("팝업 열렸다·진행·운영·으로 들어왔다", "팝업스토어가 진행된다", "11월 팝업"), 요약에서 '팝업' 바로 앞
  두 낱말 중 하나(거점 별칭·시·도 이름·일반 낱말 제외)가 제목에도 있음("올기 찹쌀떡 …" 글의 "#올기 팝업").
- 팝업스토어를 만들거나 나르는 업체 글("팝업스토어 화물 운송", "팝업 제작·시공·인테리어·대행·렌탈", 견적) −4.
- 제목이 다른 시·도 이름에 바로 '팝업'을 붙여 쓰고("부산 팝업스토어 7곳") 검색 시·도 이름은 없으면 다른 지역 글(other_region).

규칙 v4(2026-11-16, v3 배포 뒤 운영 서울 응답에 남은 업체 글: "서울 팝업스토어 장소 대관…", "팝업스토어 간판 시공 | … 원상복구"):
- 제목에 '팝업'과 팝업스토어 상대 업무 낱말(대관·간판·시공·원상복구·철거·렌탈·견적·운송·부스 제작 등)이 함께 있으면 업체 글 −4.

규칙 v5(2026-11-16, v4 배포 뒤 운영 서울 응답: "대형룰렛 렌탈"(요약에만 백화점 팝업스토어), "치이카와 … 일본 팝업스토어"):
- 제목의 업무 낱말은 제목에 '팝업'이 없어도(요약에만 있어도) 업체 글 −4.
- 해외 지명 바로 뒤의 '팝업'("일본 팝업스토어", "도쿄 팝업")은 화면 요소처럼 가려 증거로 세지 않는다. 지명이 다른 낱말에 붙어 있으면("홍콩익스프레스") 가리지 않는다.
"""

import hashlib
import html
import math
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from .regions import ALIASES as REGION_ALIASES
from .regions import normalize_region

# v1.1: 새 표본(2페이지)을 본 뒤 고친 사후 조정(거점: '지난 N월', 여러 시·도 거점이 함께 나온 글). 수치는 보고서에 따로 적는다.
# v2: 팝업 행사 증거 점수(popup_evidence). 원본 검색 캐시 키에 들어가므로 올리면 이전 캐시를 쓰지 않는다.
# v3: 제목에 팝업이 없는 글의 주제 근거, 업체 글 감점, 제목의 다른 시·도 팝업.
# v4: 제목이 팝업스토어 상대 업무(대관·간판·시공·원상복구 등)를 말하는 업체 글 감점.
# v5: 해외 팝업 언급은 증거로 세지 않음, 제목 업무 낱말은 제목에 팝업이 없어도 감점.
RULES_VERSION = "popups-rules-v5"

# ---------------------------------------------------------------- 텍스트


def normalize_text(value):
    """검색 결과의 <b> 같은 태그를 지우고 HTML 엔티티를 글자로 바꾼 뒤 공백을 하나로. 결과는 텍스트로만 쓴다."""
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def has_popup(text):
    """글자 '팝업'이 있는지만 본다(검색 결과의 첫 거름, 캐시 수명). 팝업 행사 글인지는 popup_evidence 가 정한다."""
    return "팝업" in str(text or "")


# ---------------------------------------------------------------- 팝업 행사 증거(v2)

# 행사를 뜻하는 표현(강한 증거). 띄어쓰기·영문 표기를 함께 본다.
_EVENT_SUFFIX = r"(?:스토어|샵|숍|매장|행사|존|오픈|부스|마켓|전시|카페|공간)"
# 행사가 열린다는 서술("지하 1층 팝업 열렸다", "팝업 으로 열린", "11일부터 팝업 을 하는"). 0·1단계 표본에서
# 요약에 '팝업' 한 마디만 있던 진짜 팝업 글이 이 꼴이었다. '열리면'은 화면 창일 수 있어 넣지 않는다.
# v3: "센텀시티에 팝업 으로 들어왔다", "팝업 입점"도 행사 서술.
_NARRATION = (
    r"팝업\s*(?:이|을|으로|도|까지)?\s*"
    r"(?:열렸|열린|열려|열리고|열리는|진행|운영|개최|하는|하고\s*있|들어왔|들어온|들어와|입점)"
)
# "부산 롯데백화점 11월 팝업": 달과 함께 쓴 팝업은 행사.
_MONTH_POPUP = r"\d{1,2}\s*월\s*팝업"
POPUP_EVENT_TERMS = (
    r"팝업\s*" + _EVENT_SUFFIX,
    r"pop[\s-]?up\s*(?:store|shop)",
    _NARRATION,
    _MONTH_POPUP,
)
# 화면 요소나 다른 물건을 뜻하는 '팝업'. 이 자리의 '팝업'은 증거로 세지 않는다(가린 뒤 나머지에서 찾음).
# 예: "추천 코드로 가입하면 메인 팝업을 통해 쿠폰 지급"(앱 화면), "팝업창 차단 해제", "아이 팝업북".
# 앞말로 거르는 꼴은 뒤에 행사 표현이 오면 거르지 않는다("안내 팝업스토어"는 행사).
# '팝업 메뉴'·'팝업 안내'는 팝업스토어의 메뉴·안내로 흔히 쓰여 넣지 않는다.
_NOT_SUFFIX = r"팝업(?!\s*" + _EVENT_SUFFIX + ")"
FOREIGN_PLACES = (
    "일본",
    "도쿄",
    "오사카",
    "교토",
    "후쿠오카",
    "홍콩",
    "중국",
    "상하이",
    "베이징",
    "청두",
    "대만",
    "타이베이",
    "싱가포르",
    "방콕",
    "미국",
    "뉴욕",
    "파리",
    "런던",
    "해외",
)
POPUP_NOT_EVENT = (
    r"(?:메인|레이어|앱|어플|알림|공지|안내|광고)\s*" + _NOT_SUFFIX,
    # '창'은 '창원'(도시)이 뒤따르는 경우를 뺀다.
    r"팝업\s*(?:창(?!원)|광고|차단|알림창|메시지|메세지|화면|닫기|해제|북|카드|텐트|캠퍼)",
    # "팝업이 뜨면", "팝업으로 떠요": 화면에 뜨는 창.
    r"팝업\s*(?:이|으로|가)?\s*(?:뜨(?!거)|떠(?!오)|떴|뜸)",
    # v5: 해외에서 열린 팝업("일본 팝업스토어", "도쿄 팝업"). 지명이 낱말로 따로 있을 때만("홍콩익스프레스 팝업"은 국내 행사).
    r"(?<![가-힣])(?:"
    + "|".join(FOREIGN_PLACES)
    + r")(?![가-힣])\s*팝업(?:\s*"
    + _EVENT_SUFFIX
    + ")?",
)
# 영문 단독 표기(POPUP, POP-UP)는 한글 '팝업' 단독과 같은 약한 증거.
_BARE_EVENT = re.compile(r"팝업|pop[\s-]?up", re.I)
# 앱 가입·초대 홍보 글의 낱말. '쿠폰'·'할인'·'증정'은 팝업스토어 글에도 흔해 넣지 않는다.
POPUP_PROMO_WORDS = (
    r"추천\s*코드",
    r"추천인",
    r"초대\s*코드",
    r"친구\s*초대",
    r"초대\s*보상",
    r"회원\s*가입",
    r"앱\s*(?:설치|다운)",
    r"(?:레|리)퍼럴",
)
# 점수: 제목의 행사 표현은 그것만으로 충분하고(감점이 있어도), 요약에만 있는 '팝업' 한 마디는 기간·거점이 받쳐 줘야 한다.
EVIDENCE_POINTS = dict(
    title_term=4,
    title_bare=2,
    description_term=2,
    description_bare=1,
    period=1,
    hub=1,
)
PROMO_PENALTY = 2
SHOW_THRESHOLD = 2
# v3: 팝업스토어를 만들거나 나르는 업체 글. 제목의 행사 표현(4)을 지울 만큼 감점한다(기간·거점이 둘 다 있어야 남음).
# '팝업' 바로 뒤에 업무 낱말이 오는 꼴만 본다("팝업 굿즈 제작 체험"처럼 행사 안의 제작은 걸리지 않음).
POPUP_VENDOR_WORDS = (
    r"팝업\s*"
    + _EVENT_SUFFIX
    + r"?\s*(?:화물|운송|물류|배차|제작|시공|인테리어|철거|대행|렌탈|대여|견적)",
    r"팝업\s*" + _EVENT_SUFFIX + r"?\s*(?:설치|운영)\s*(?:업체|전문|대행)",
)
VENDOR_PENALTY = 4
# v4: 제목이 팝업스토어를 상대로 하는 업무를 말하는 글("서울 팝업스토어 장소 대관", "팝업스토어 간판 시공 | … 원상복구").
# '팝업'과 업무 낱말 사이에 다른 말이 끼어도 제목에 함께 있으면 업체 글로 본다. '제작'만으로는 보지 않는다(굿즈 제작 체험).
POPUP_VENDOR_TITLE = re.compile(
    r"대관|간판|시공|원상\s*복구|철거|인테리어\s*(?:업체|공사)|렌탈|견적|운송|화물|(?:부스|집기|가구)\s*제작|제작\s*업체|설치\s*업체"
)

_NOT_EVENT = re.compile("|".join(POPUP_NOT_EVENT), re.I)
_EVENT_TERM = re.compile("|".join(POPUP_EVENT_TERMS), re.I)
_PROMO = re.compile("|".join(POPUP_PROMO_WORDS), re.I)
_VENDOR = re.compile("|".join(POPUP_VENDOR_WORDS), re.I)
# 주제 근거로 보는 행사 서술: _NARRATION·_MONTH_POPUP 에 더해 "온라인 팝업스토어 가 진행된다"처럼 행사 표현에 조사와
# 동사가 붙은 꼴. 조사가 없는 명사 나열("첫 단독 팝업 스토어 운영, 구독자 90만 돌파")은 서술로 보지 않는다.
_TERM_NARRATION = (
    r"팝업\s*" + _EVENT_SUFFIX + r"\s*(?:이|가|을|를|도|은|는)\s*"
    r"(?:열렸|열린|열려|열리고|열리는|진행|운영|개최|들어왔|들어온|들어와|입점)"
)
_TOPIC_ANCHOR = re.compile("|".join((_TERM_NARRATION, _NARRATION, _MONTH_POPUP)), re.I)
# 주제 이름을 찾을 때 '팝업' 앞에서 보는 낱말 수와 문장 경계.
TOPIC_WORDS_BEFORE = 2
_SENTENCE_END = re.compile(r"[.!?|·…\n]")
_WORD = re.compile(r"[가-힣A-Za-z0-9&]+")


def popup_mentions(text):
    """(행사 표현, 단독 '팝업', 뺀 표현) 목록. 뺀 표현 자리를 공백으로 가린 뒤 나머지에서 찾는다."""
    text = normalize_text(text)
    excluded = [m.group(0) for m in _NOT_EVENT.finditer(text)]
    masked = _NOT_EVENT.sub(lambda m: " " * len(m.group(0)), text)
    terms = [m.group(0) for m in _EVENT_TERM.finditer(masked)]
    rest = _EVENT_TERM.sub(lambda m: " " * len(m.group(0)), masked)
    bare = [m.group(0) for m in _BARE_EVENT.finditer(rest)]
    return terms, bare, excluded


_PLACE_KEYS = None


def _place_keys():
    """주제 이름으로 쓰지 않을 장소 낱말: 거점 별칭·이름과 시·도 이름(name_key 꼴)."""
    global _PLACE_KEYS
    if _PLACE_KEYS is None:
        from .popup_hubs import HUBS

        keys = {name_key(a) for h in HUBS for a in h["aliases"]}
        keys |= {name_key(h["name"]) for h in HUBS} | {name_key(a) for a in REGION_ALIASES}
        _PLACE_KEYS = frozenset(k for k in keys if k)
    return _PLACE_KEYS


def topic_names(title, description):
    """v3: 요약에서 '팝업' 바로 앞 낱말(같은 문장, 최대 TOPIC_WORDS_BEFORE 개) 가운데 제목에도 있는 이름.

    거점 별칭·시·도 이름이 들어간 낱말, 일반 낱말(GENERIC_NAME_WORDS), 두 글자 미만·숫자는 이름으로 보지 않는다.
    "올기 찹쌀떡 가격 …" 글 요약의 "#올기 팝업" → ["올기"]. "#코엑스 팝업스토어"의 '코엑스'는 거점이라 세지 않는다.
    """
    title_key = name_key(normalize_text(title))
    text = normalize_text(description)
    masked = _NOT_EVENT.sub(lambda m: " " * len(m.group(0)), text)
    generic = {name_key(w) for w in GENERIC_NAME_WORDS}
    places = _place_keys()
    names = []
    for m in _BARE_EVENT.finditer(masked):
        head = masked[: m.start()]
        cut = max((s.end() for s in _SENTENCE_END.finditer(head)), default=0)
        for word in _WORD.findall(head[cut:])[-TOPIC_WORDS_BEFORE:]:
            key = name_key(word)
            if len(key) < 2 or key.isdigit() or key in generic:
                continue
            if any(p in key for p in places):
                continue
            if key in title_key and word not in names:
                names.append(word)
    return names


def title_other_region(title, region):
    """v3: 제목이 다른 시·도 이름에 바로 '팝업'을 붙여 쓰고("부산 팝업스토어 7곳") 검색 시·도 이름은 쓰지 않으면 그 시·도."""
    text = normalize_text(title)
    if any(name in text for name, r in REGION_ALIASES.items() if r == region):
        return None
    for m in _REGION_POPUP.finditer(text):
        other = REGION_ALIASES[m.group(1)]
        if other != region:
            return other
    return None


_REGION_POPUP = re.compile(
    r"(?<![가-힣])("
    + "|".join(map(re.escape, sorted(REGION_ALIASES, key=len, reverse=True)))
    + r")\s*(?:팝업|pop[\s-]?up)",
    re.I,
)


def popup_evidence(title, description, has_period, has_hub):
    """팝업 행사 글인지 증거 점수로 판정. has_period·has_hub 는 extract_period·hub_match 결과(부르는 쪽이 계산).

    v3: 제목에 팝업 언급이 없으면 요약 언급은 주제 근거(기간·행사 서술·제목에도 있는 이름)가 있을 때만 보여 준다.
    반환: dict(show, score, evidence, penalties, excluded). evidence·penalties 는 사람이 읽는 근거 문자열.
    """
    t_terms, t_bare, t_excluded = popup_mentions(title)
    d_terms, d_bare, d_excluded = popup_mentions(description)
    points = EVIDENCE_POINTS
    evidence = []
    if t_terms:
        word = ("title_term", t_terms[0])
    elif t_bare:
        word = ("title_bare", t_bare[0])
    elif d_terms:
        word = ("description_term", d_terms[0])
    elif d_bare:
        word = ("description_bare", d_bare[0])
    else:
        word = None
    score = 0
    if word:
        score += points[word[0]]
        evidence.append(f"{word[0]}:{word[1]}")
    if has_period:
        score += points["period"]
        evidence.append("period")
    if has_hub:
        score += points["hub"]
        evidence.append("hub")
    text = normalize_text(title) + " " + normalize_text(description)
    promo = sorted({re.sub(r"\s+", "", m.group(0)) for m in _PROMO.finditer(text)})
    penalties = []
    if promo:
        score -= PROMO_PENALTY
        penalties.append("promo:" + ",".join(promo))
    vendor = sorted({re.sub(r"\s+", "", m.group(0)) for m in _VENDOR.finditer(text)})
    clean_title = normalize_text(title)
    # v5: 제목에 '팝업'이 없고 요약에만 있어도("대형룰렛 렌탈 … 백화점 팝업스토어 등 현장에서") 제목이 업무를 말하면 업체 글.
    if not vendor:
        vendor = sorted(
            {re.sub(r"\s+", "", m.group(0)) for m in POPUP_VENDOR_TITLE.finditer(clean_title)}
        )
    if vendor:
        score -= VENDOR_PENALTY
        penalties.append("vendor:" + ",".join(vendor))
    on_topic = True
    if word and word[0].startswith("description_") and not has_period:
        # v3: 제목에 팝업이 없고 기간도 없으면 요약의 행사 서술이나 제목에도 있는 이름이 있어야 글의 주제로 본다.
        masked = _NOT_EVENT.sub(lambda m: " " * len(m.group(0)), normalize_text(description))
        narration = _TOPIC_ANCHOR.search(masked)
        if narration:
            evidence.append("narration:" + narration.group(0))
        else:
            names = topic_names(title, description)
            if names:
                evidence.append("topic:" + names[0])
            else:
                on_topic = False
                penalties.append("no_topic")
    return dict(
        show=on_topic and score >= SHOW_THRESHOLD,
        score=score,
        evidence=evidence,
        penalties=penalties,
        excluded=t_excluded + d_excluded,
    )


# ---------------------------------------------------------------- 날짜

# 날짜 뒤 요일: 괄호 안("(수)", "(수요일)") 또는 v1 부터 괄호 없이 "수요일".
_DOW = r"(?:\s*\(\s*[월화수목금토일](?:요일)?\s*\)|\s*[월화수목금토일]요일)?"
_UNIT_AFTER = re.compile(
    r"\s*(?:배|%|퍼센트|만|천|원|억|kg|g|km|m|cm|mm|ml|l|인치|점|년|대|시간|분|초|세|살|명|개|층|위|호|번|회|차|박|평|v)",
    re.I,
)
# 앞 글자가 숫자·점·영문이면 날짜가 아니다(버전 v2.1, 1.2.3, 소수 12.5.3 의 가운데).
_P_YMD = re.compile(
    r"(?<![\w.])(20\d{2})\s*(?:[./-]|년)\s*(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})(?!\d)(?:\s*일)?\.?"
)
_P_YYMD = re.compile(r"(?<![\w.])'?([2-3]\d)\.(\d{1,2})\.(\d{1,2})(?![\d])\.?")
# v1: 두 자리 연도 "26년 11월 13일". 네 자리 연도의 뒤 두 자리("2026년")는 앞 글자가 숫자라 걸리지 않는다.
_P_YYKMD = re.compile(r"(?<![\w.])'?([2-3]\d)\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_P_KMD = re.compile(r"(?<![\w.])(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_P_MD = re.compile(r"(?<![\w.])(\d{1,2})\s*[./]\s*(\d{1,2})(?!\d)(?!\.\d)\.?")
_CONNECT = re.compile(r"\s*(?:~|∼|～|〜|-|–|—|부터)\s*")
# v1: "11월6일에서 11월19일까지". '에서' 는 뒤 날짜에 '까지'가 붙을 때만 범위 연결로 본다.
_CONNECT_FROM = re.compile(r"\s*에서\s*")
_DAY_ONLY = re.compile(r"(\d{1,2})(?!\d)(?!\s*[./]\s*\d)\s*일?")
_UNTIL = re.compile(r"\s*(?:일\s*)?까지")
_START_WORD = re.compile(r"\s*(?:부터|오픈|OPEN|open|Open|개막|시작|그랜드\s*오픈)")
# 기간 문맥 단어. 날짜에 더 가까운 쪽을 따른다(같으면 행사 아님 쪽).
EVENT_WORDS = (
    "기간",
    "운영",
    "오픈",
    "open",
    "진행",
    "팝업",
    "개최",
    "열리",
    "열린",
    "열려",
    "일정",
    "전시",
    "행사",
)
OTHER_WORDS = (
    "예약",
    "응모",
    "추첨",
    "당첨",
    "발표",
    "배송",
    "발송",
    "출시",
    "판매",
    "구매",
    "방문",
    "다녀",
    "후기",
    "신청",
    "마감",
    "결제",
    "입고",
    "방송",
    "개점",
)
# v1: '오픈'만 보고 시작일로 읽은 날짜는 팝업 문맥이 있을 때만 쓴다. 매장 개점을 알리는 낱말이 가까이 있으면 쓰지 않는다.
STORE_OPENING_WORDS = ("매장", "개점", "플래그십", "호점", "아울렛")
CONTEXT_BEFORE = 25
CONTEXT_AFTER = 15
MAX_SPAN_DAYS = 400


def _valid(year, month, day):
    """달력에 있는 날짜인지. 연도가 없으면 윤년(2024) 기준으로 2월 29일까지 허용."""
    try:
        return date(year or 2024, month, day)
    except ValueError:
        return None


def _mentions(text):
    """겹치지 않는 날짜 표현 목록. 연도가 있는 형식을 먼저 잡는다."""
    found = []
    taken = []

    def free(s, e):
        return all(e <= a or s >= b for a, b in taken)

    for kind, pattern in (
        ("ymd", _P_YMD),
        ("yymd", _P_YYMD),
        ("yymd", _P_YYKMD),
        ("kmd", _P_KMD),
        ("md", _P_MD),
    ):
        for m in pattern.finditer(text):
            s, e = m.span()
            if not free(s, e):
                continue
            groups = [int(g) for g in m.groups()]
            if kind == "ymd":
                y, mo, d = groups
            elif kind == "yymd":
                y, mo, d = 2000 + groups[0], groups[1], groups[2]
            else:
                y, (mo, d) = None, groups
            if kind == "md" and _UNIT_AFTER.match(text, e):
                continue
            if not _valid(y, mo, d):
                continue
            found.append(dict(kind=kind, year=y, month=mo, day=d, start=s, end=e))
            taken.append((s, e))
    return sorted(found, key=lambda x: x["start"])


def _context(text, s, e):
    """날짜 표현(s:e) 주변에서 가장 가까운 문맥 단어로 event / other / unknown."""
    lo = max(0, s - CONTEXT_BEFORE)
    hi = min(len(text), e + CONTEXT_AFTER)
    window = text[lo:hi].casefold()
    best = None
    for label, words in (("other", OTHER_WORDS), ("event", EVENT_WORDS)):
        for word in words:
            for m in re.finditer(re.escape(word.casefold()), window):
                a, b = lo + m.start(), lo + m.end()
                dist = s - b if b <= s else (a - e if a >= e else 0)
                dist = max(dist, 0)
                # 같은 거리면 other 가 이긴다(먼저 넣었고 < 비교).
                if best is None or dist < best[0]:
                    best = (dist, label, word)
    return (best[1], best[2]) if best else ("unknown", None)


def _resolve_range(sy, sm, sd, ey, em, ed):
    """(시작 연도, 종료 연도) 정하기. 한쪽만 연도가 있으면 같은 문맥에서 이어지는 연도만 쓴다(연말·연초 넘김 포함)."""
    if sy and ey:
        return sy, ey
    if sy and not ey:
        return sy, sy if (em, ed) >= (sm, sd) else sy + 1
    if ey and not sy:
        return (ey if (sm, sd) <= (em, ed) else ey - 1), ey
    return None, None


def _date_or_none(y, m, d):
    if not y:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _skip_dow(text, i):
    m = re.compile(_DOW).match(text, i)
    return m.end() if m else i


def date_candidates(text):
    """날짜 후보(범위·시작만·종료만·단일)와 문맥. 상태 판정에 쓸지는 extract_period 가 정한다."""
    text = str(text or "")
    mentions = _mentions(text)
    out = []
    used = set()
    for i, m in enumerate(mentions):
        if i in used:
            continue
        after = _skip_dow(text, m["end"])
        conn = _CONNECT.match(text, after)
        cand = None
        nxt = mentions[i + 1] if i + 1 < len(mentions) else None
        via = _CONNECT_FROM.match(text, after)
        if via and nxt and nxt["start"] == via.end():
            # "…에서 …까지": 뒤 날짜에 '까지'가 붙어야 범위로 본다("성수에서" 같은 장소 '에서'와 구분).
            e_end = _skip_dow(text, nxt["end"])
            u = _UNTIL.match(text, e_end)
            if u:
                used.add(i + 1)
                cand = dict(
                    type="range",
                    s=(m["year"], m["month"], m["day"]),
                    e=(nxt["year"], nxt["month"], nxt["day"]),
                    span=(m["start"], u.end()),
                )
        if cand is None and conn:
            j = conn.end()
            if nxt and nxt["start"] == j:
                used.add(i + 1)
                e_end = _skip_dow(text, nxt["end"])
                u = _UNTIL.match(text, e_end)
                cand = dict(
                    type="range",
                    s=(m["year"], m["month"], m["day"]),
                    e=(nxt["year"], nxt["month"], nxt["day"]),
                    span=(m["start"], u.end() if u else nxt["end"]),
                )
            else:
                d = _DAY_ONLY.match(text, j)
                if (
                    d
                    and not _UNIT_AFTER.match(text, d.end(1))
                    and _valid(m["year"], m["month"], int(d.group(1)))
                ):
                    cand = dict(
                        type="range",
                        s=(m["year"], m["month"], m["day"]),
                        e=(m["year"], m["month"], int(d.group(1))),
                        span=(m["start"], d.end()),
                        end_day_only=True,
                    )
                elif conn.group(0).strip() == "부터":
                    cand = dict(
                        type="start_only",
                        s=(m["year"], m["month"], m["day"]),
                        e=None,
                        span=(m["start"], conn.end()),
                    )
        if cand is None:
            before = text[max(0, m["start"] - 3) : m["start"]]
            until = _UNTIL.match(text, after)
            if re.search(r"[~∼～〜]\s*$", before):
                # '2026.2.30~2026.3.5' 처럼 앞쪽이 달력에 없는 날짜였던 범위는 종료일만 따로 쓰지 않는다.
                if re.search(r"\d\.?\s*(?:\([^)]{1,4}\))?\s*[~∼～〜]\s*$", text[: m["start"]]):
                    continue
                cand = dict(
                    type="end_only",
                    s=None,
                    e=(m["year"], m["month"], m["day"]),
                    span=(m["start"], m["end"]),
                )
            elif until:
                cand = dict(
                    type="end_only",
                    s=None,
                    e=(m["year"], m["month"], m["day"]),
                    span=(m["start"], until.end()),
                )
            elif _START_WORD.match(text, after):
                word = _START_WORD.match(text, after).group(0).strip().casefold()
                cand = dict(
                    type="start_only",
                    s=(m["year"], m["month"], m["day"]),
                    e=None,
                    span=(m["start"], m["end"]),
                    by_open_word=word.endswith("오픈") or word == "open",
                )
            elif m["kind"] == "md" and after == m["end"]:
                # 연도도 '일'도 요일도 없는 단독 M.D 는 버전·번호일 수 있어 날짜로 보지 않는다.
                continue
            else:
                cand = dict(
                    type="single",
                    s=(m["year"], m["month"], m["day"]),
                    e=None,
                    span=(m["start"], m["end"]),
                )
        if cand["type"] == "range":
            (sy, sm, sd), (ey, em, ed) = cand["s"], cand["e"]
            if cand.get("end_day_only") and ed < sd:
                continue
            ry_s, ry_e = _resolve_range(sy, sm, sd, ey, em, ed)
            cand["years"] = (ry_s, ry_e)
            if ry_s and ry_e:
                a, b = _date_or_none(ry_s, sm, sd), _date_or_none(ry_e, em, ed)
                if not a or not b or b < a or (b - a).days > MAX_SPAN_DAYS:
                    continue
            elif not sy and not ey:
                # 연도 없는 범위: 시작 > 종료면 연말·연초를 넘는 것으로만 본다(연도는 여전히 모름).
                cand["crosses_year"] = (em, ed) < (sm, sd)
        label, word = _context(text, *cand["span"])
        if cand.get("by_open_word"):
            s, e = cand["span"]
            window = text[max(0, s - CONTEXT_BEFORE) : min(len(text), e + CONTEXT_AFTER)]
            store = next((w for w in STORE_OPENING_WORDS if w in window), None)
            if store or "팝업" not in window:
                # 매장 개점일("[대전 이케아] 11월 19일 오픈!")은 팝업 기간이 아니다.
                label, word = "other", store or "오픈(팝업 문맥 없음)"
        cand.update(
            context=label,
            context_word=word,
            evidence=text[cand["span"][0] : cand["span"][1]].strip(),
        )
        out.append(cand)
    return out


def _period_from(cand):
    """후보 하나를 상태 판정용 기간으로. 연도가 없으면 월·일만 남기고 날짜는 None."""
    t = cand["type"]
    s = cand.get("s")
    e = cand.get("e")
    if t == "range":
        ys, ye = cand.get("years", (None, None))
        start = _date_or_none(ys, s[1], s[2])
        end = _date_or_none(ye, e[1], e[2])
    elif t == "start_only":
        start, end = _date_or_none(s[0], s[1], s[2]), None
    else:
        start, end = None, _date_or_none(e[0], e[1], e[2])
    return dict(
        kind=t,
        start=start,
        end=end,
        start_md=(s[1], s[2]) if s else None,
        end_md=(e[1], e[2]) if e else None,
        year_known=(start is not None or not s) and (end is not None or not e),
        crosses_year=cand.get("crosses_year", False),
        evidence=cand["evidence"],
    )


def _period_key(p):
    return (p["kind"], p["start_md"], p["end_md"], p["start"], p["end"])


def extract_period(title, description=""):
    """글 하나의 행사 기간 판정.

    status:
    - "period": 기간 문맥의 후보가 하나(연도 확인 여부는 year_known)
    - "conflict": 기간 문맥의 서로 다른 후보가 둘 이상(넓은 기간으로 합치지 않음)
    - "none": 기간 문맥의 후보 없음(다른 문맥의 날짜만 있거나 날짜가 없음)
    """
    text = normalize_text(title) + " \n " + normalize_text(description)
    cands = date_candidates(text)
    adopted = [
        c
        for c in cands
        if c["context"] == "event" and c["type"] in ("range", "start_only", "end_only")
    ]
    periods = []
    seen = set()
    for c in adopted:
        p = _period_from(c)
        k = _period_key(p)
        if k not in seen:
            seen.add(k)
            periods.append(p)
    rejected = [
        dict(
            type=c["type"],
            context=c["context"],
            word=c["context_word"],
            evidence=c["evidence"],
        )
        for c in cands
        if c not in adopted
    ]
    if not periods:
        return dict(status="none", period=None, periods=[], rejected=rejected)
    if len(periods) > 1:
        return dict(status="conflict", period=None, periods=periods, rejected=rejected)
    return dict(status="period", period=periods[0], periods=periods, rejected=rejected)


def counterfactual_period(period, source_date):
    """채택하지 않는 가정: 연도 없는 월·일을 출처 날짜의 연도로 읽는다(보고용 반사실 수치에만 씀)."""
    if not period or period["year_known"] or not source_date:
        return period
    y = source_date.year
    p = dict(period)
    if p["start_md"] and p["start"] is None:
        p["start"] = _date_or_none(y, *p["start_md"])
    if p["end_md"] and p["end"] is None:
        ey = y
        if p["start_md"] and p["end_md"] < p["start_md"]:
            ey = y + 1
        p["end"] = _date_or_none(ey, *p["end_md"])
    p["year_known"] = True
    p["assumed_year"] = True
    return p


# ---------------------------------------------------------------- 방문일 상태

STATUS_LABELS = {
    "ongoing": "진행 중",
    "upcoming": "오픈 예정",
    "ended": "종료",
    "unknown": "기간 미확인",
}


def visit_status(period, visit):
    """7절 표. 시작·종료일 포함, 날짜는 Asia/Seoul 달력 날짜(호출하는 쪽이 date 로 넘김).

    반환: dict(status, end_only) — status 는 ongoing / upcoming / ended / unknown.
    """
    if not period:
        return dict(status="unknown", end_only=False, reason="no_period")
    start, end = period.get("start"), period.get("end")
    if period.get("start_md") and start is None or period.get("end_md") and end is None:
        return dict(status="unknown", end_only=False, reason="year_unknown")
    if start and end:
        if visit < start:
            return dict(status="upcoming", end_only=False, reason="range")
        if visit > end:
            return dict(status="ended", end_only=False, reason="range")
        return dict(status="ongoing", end_only=False, reason="range")
    if start:
        if visit < start:
            return dict(status="upcoming", end_only=False, reason="start_only")
        return dict(status="unknown", end_only=False, reason="start_only")
    if end:
        if visit > end:
            return dict(status="ended", end_only=True, reason="end_only")
        return dict(status="unknown", end_only=True, reason="end_only")
    return dict(status="unknown", end_only=False, reason="no_period")


def post_status(extraction, visit):
    """글 하나의 상태. 기간 충돌·추출 실패는 기간 미확인."""
    if extraction["status"] == "conflict":
        return dict(status="unknown", end_only=False, reason="conflict")
    return visit_status(extraction["period"], visit)


# ---------------------------------------------------------------- 거점

_REGION_PREFIX = ("서울", "부산", "대구", "대전", "인천", "광주", "울산", "#")


def _alias_pattern(alias):
    """별칭의 띄어쓴 자리는 공백 0개 이상. v1: 공백 제외 4글자 이상인 별칭은 글자 사이 공백 한 칸도 허용
    ("롯데백화점 부산본점" ↔ "롯데백화점 부산 본점", "신세계백화점 대구점" ↔ "신세계백화점 대구 점")."""
    words = alias.split()
    if len("".join(words)) >= 4:
        parts = [r"\s?".join(re.escape(ch) for ch in word) for word in words]
    else:
        parts = [re.escape(word) for word in words]
    return re.compile(r"\s*".join(parts), re.I)


# v1: 지난 장소·비교로 언급한 거점은 이번 행사 장소로 보지 않는다.
# 예: "지난번 신세계백화점 센텀시티에 이어 이번에는 …", "더현대 서울 이랑은 차원이 다르게 …".
# v1.1(사후 조정): "지난 10월 신세계백화점 대구 점과 …에 이어" 처럼 '지난 N월'도 지난 장소로 본다.
_PAST_BEFORE = re.compile(
    r"(?:지난\s?번|저번|지난해|작년|예전|이전|지난\s?\d{1,2}\s?월)\s*(?:에는|엔|의)?\s*$"
)
_COMPARE_AFTER = re.compile(
    r"^\s*(?:에\s?이어|보다|(?:이)?랑은|(?:이)?랑\s?비교|[와과]\s?비교|[와과]\s?달리|[와과]는\s?달리|에\s?비해)"
)
PAST_WINDOW = 12


def mention_context(text, span):
    """거점 언급의 문맥: 'past'(지난 장소·비교 대상) 또는 'current'."""
    s, e = span
    if _PAST_BEFORE.search(text[max(0, s - PAST_WINDOW) : s]):
        return "past"
    if _COMPARE_AFTER.match(text[e : e + 12]):
        return "past"
    return "current"


def match_hubs(text, hubs):
    """글에 나온 거점들. 긴 별칭을 먼저 잡고 겹치는 짧은 별칭은 버린다.

    짧은 별칭(공백 제외 3글자 이하)은 앞 글자가 한글이면(지역명 바로 뒤는 허용) 매칭하지 않는다.
    반환: [dict(id, alias, span, context)] 글 안의 위치 순. context 는 mention_context.
    """
    text = normalize_text(text)
    rows = []
    for hub in hubs:
        for alias in hub["aliases"]:
            rows.append((len(alias.replace(" ", "")), alias, hub))
    rows.sort(key=lambda r: (-r[0], r[2]["id"], r[1]))
    taken = []
    found = []
    for size, alias, hub in rows:
        for m in _alias_pattern(alias).finditer(text):
            s, e = m.span()
            if any(not (e <= a or s >= b) for a, b in taken):
                continue
            if size <= 3 and s > 0 and re.match(r"[가-힣]", text[s - 1]):
                if not any(text[:s].endswith(p) for p in _REGION_PREFIX):
                    continue
            if any(text.startswith(word, e) for word in hub["not_followed_by"]):
                continue
            taken.append((s, e))
            found.append(
                dict(
                    id=hub["id"],
                    alias=m.group(0),
                    span=(s, e),
                    context=mention_context(text, (s, e)),
                )
            )
    found.sort(key=lambda r: r["span"])
    return found


def hub_match(text, hubs, region):
    """검색 지역 기준 판정. 지난 장소·비교로만 언급한 거점(v1)은 세지 않는다(past_ids 에 따로 남김).

    - single: 같은 지역 거점이 정확히 하나 → 그 거점
    - multiple: 같은 지역 거점이 둘 이상 → 단일 장소로 강제하지 않음
    - other_region: 다른 지역 거점만 있음
    - none: 없음
    """
    by_id = {h["id"]: h for h in hubs}
    mentions = match_hubs(text, hubs)
    current = [m["id"] for m in mentions if m["context"] == "current"]
    ids = list(dict.fromkeys(current))
    past = [i for i in dict.fromkeys(m["id"] for m in mentions) if i not in ids]
    result = _hub_verdict(ids, by_id, region)
    result["past_ids"] = past
    return result


def _hub_verdict(ids, by_id, region):
    same = [i for i in ids if by_id[i]["region"] == region]
    other = [i for i in ids if by_id[i]["region"] != region]
    if len(same) == 1 and other:
        # v1.1(사후 조정): 검색 지역 거점과 다른 지역 거점을 함께 적은 글(여러 지점 순회, 다른 지역 행사 글에 덧붙인 언급)은
        # 어느 쪽이 이번 행사 장소인지 요약만으로 알 수 없어 단일 장소로 정하지 않는다(다른 지역 글로 빼지도 않음).
        return dict(status="multiple", hub_id=None, ids=ids, mixed_regions=True)
    if len(same) == 1:
        return dict(status="single", hub_id=same[0], ids=ids)
    if len(same) > 1:
        return dict(status="multiple", hub_id=None, ids=ids)
    if ids:
        return dict(status="other_region", hub_id=None, ids=ids)
    return dict(status="none", hub_id=None, ids=[])


def verify_local_result(hub, items):
    """지역 검색 결과에서 거점 좌표 고르기. 첫 결과를 무조건 쓰지 않는다.

    상호(공백 제거·소문자)에 verify 문자열이 있고, 주소가 거점의 시·도와 시·군·구로 시작해야 한다.
    통과한 결과가 서로 300m 넘게 떨어져 있으면 모호 → 위치 미확인.
    좌표는 mapx(경도)·mapy(위도) × 10^7 정수(공식 문서: WGS84)로 보고 도 단위로 바꾼다.
    """
    passed = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s+", "", normalize_text(item.get("title"))).casefold()
        address = normalize_text(item.get("roadAddress") or item.get("address"))
        if not any(v.casefold() in name for v in hub["verify"]):
            continue
        words = address.split()
        if (
            len(words) < 2
            or not _region_word(words[0], hub["region"])
            or words[1] != hub["district"]
        ):
            continue
        point = local_point(item)
        if not point:
            continue
        passed.append(
            dict(
                name=normalize_text(item.get("title")),
                address=address,
                lat=point[0],
                lon=point[1],
                shopping=any(w in str(item.get("category") or "") for w in SHOPPING_CATEGORY_WORDS),
            )
        )
    if not passed:
        return dict(status="unverified", reason="no_matching_result", point=None, candidates=0)
    # v1: 건물 거점은 입점 매장 항목보다 건물 자체(백화점·쇼핑시설 업종) 항목을 먼저 본다.
    if hub["kind"] == "building" and any(p["shopping"] for p in passed):
        passed = [p for p in passed if p["shopping"]]
    for p in passed:
        p.pop("shopping")
    first = passed[0]
    if any(distance_km(first, other) > 0.3 for other in passed[1:]):
        return dict(
            status="ambiguous",
            reason="results_far_apart",
            point=None,
            candidates=len(passed),
        )
    level = "building" if hub["kind"] == "building" else "area_anchor"
    return dict(status="verified", level=level, point=first, candidates=len(passed))


SHOPPING_CATEGORY_WORDS = ("백화점", "쇼핑몰", "쇼핑센터", "복합쇼핑", "쇼핑복합", "아울렛")


def _region_word(word, region):
    """주소 첫 낱말이 그 시·도인지(app/regions.py 의 17개 시·도 별칭표)."""
    return normalize_region(word) == region


def local_point(item):
    """mapx·mapy → (lat, lon). 한국 범위(위도 33~39, 경도 124~132) 밖이면 None."""
    try:
        lon, lat = float(item["mapx"]), float(item["mapy"])
    except (KeyError, TypeError, ValueError):
        return None
    if abs(lon) > 180:
        lon /= 10_000_000
    if abs(lat) > 90:
        lat /= 10_000_000
    if not (33 <= lat <= 39 and 124 <= lon <= 132):
        return None
    return lat, lon


def distance_km(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


# ---------------------------------------------------------------- 모아 보기·행사명

ROUNDUP_WORDS = (
    "총정리",
    "모음",
    "모아보기",
    "모아 보기",
    "best",
    "베스트",
    "top",
    "리스트",
    "정리",
    "가볼만한",
    "가볼 만한",
    "이번주",
    "이번 주",
    "주말 팝업",
    "팝업 일정",
    "추천",
)
_COUNT_PLACES = re.compile(r"\d+\s*(?:곳|선|군데|개\s*팝업)|top\s*\d+", re.I)


def classify_roundup(title, description, hubs):
    """roundup(모아 보기) / ambiguous(신호만 있음) / single.

    신호 단어 하나만으로는 모아 보기로 보지 않는다. 여러 행사·장소를 소개한다는 근거
    (거점 둘 이상, 서로 다른 기간 후보 둘 이상, 'N곳'·'TOP N', 따옴표 이름 둘 이상)가 함께 있어야 한다.
    """
    t = normalize_text(title)
    text = t + " \n " + normalize_text(description)
    low = text.casefold()
    signal = [w for w in ROUNDUP_WORDS if w in low]
    counted = bool(_COUNT_PLACES.search(text))
    hubs_found = {m["id"] for m in match_hubs(text, hubs)}
    periods = {c["evidence"] for c in date_candidates(text) if c["type"] == "range"}
    quoted = set(_quoted_names(text))
    multi = len(hubs_found) >= 2 or len(periods) >= 2 or len(quoted) >= 2
    if counted or (signal and multi):
        return dict(kind="roundup", signals=signal, counted=counted, multi=multi)
    if signal:
        return dict(kind="ambiguous", signals=signal, counted=False, multi=multi)
    return dict(kind="single", signals=[], counted=False, multi=multi)


_QUOTES = (
    r"「([^」]{2,40})」",
    r"『([^』]{2,40})』",
    r"“([^”]{2,40})”",
    r'"([^"]{2,40})"',
    r"‘([^’]{2,40})’",
    r"'([^']{2,40})'",
    r"〈([^〉]{2,40})〉",
    r"《([^》]{2,40})》",
    r"<([^<>]{2,40})>",
)
GENERIC_NAME_WORDS = {
    "팝업",
    "팝업스토어",
    "팝업존",
    "후기",
    "리뷰",
    "방문",
    "방문후기",
    "추천",
    "정리",
    "총정리",
    "일정",
    "이번주",
    "이번",
    "주말",
    "신상",
    "요즘",
    "인기",
    "핫한",
    "무료",
    "신규",
    "오픈",
    "그랜드오픈",
    "대형",
    "데이트",
    "겨울",
    "크리스마스",
    "연말",
    "백화점",
    "더현대",
    "신세계",
    "롯데",
    "현대백화점",
    "현대",
    "이색",
    "한정",
    "체험",
    "굿즈",
    "캐릭터",
    "브랜드",
    "새로운",
    "다양한",
    "최신",
    "11월",
    "12월",
    "오늘",
    "내일",
    "근처",
    "실내",
    "가볼만한곳",
    "가볼만한",
    "놀거리",
    "볼거리",
    "전시",
    "행사",
    "여기",
    "이곳",
    "첫",
    "단독",
    "공식",
    "국내",
    "최초",
    "국내최초",
    "아시아",
    "서울",
    "부산",
    "대구",
    "강원",
    "전북",
    "대전",
    "인천",
    "경기",
    "광주",
    "전주",
    "강릉",
    "춘천",
    "원주",
    "속초",
}


def name_key(name):
    """안전한 범위의 정규화: 소문자, 공백·일부 기호 제거."""
    return re.sub(r"[\s·・ㆍ.,'\"’‘“”!?~\-_/()\[\]]+", "", str(name or "")).casefold()


def _quoted_names(text):
    out = []
    for pattern in _QUOTES:
        for m in re.finditer(pattern, text):
            out.append(m.group(1).strip())
    return out


def _is_generic(candidate, hub_aliases):
    key = name_key(candidate)
    if len(key) < 2 or key.isdigit():
        return True
    if key in {name_key(w) for w in GENERIC_NAME_WORDS}:
        return True
    if key in hub_aliases:
        return True
    # 지역·동네 꼴(…동, …역, …구, …점)과 날짜 꼴
    if re.fullmatch(r"[가-힣]{1,4}(?:동|역|구|점|시|군)", key):
        return True
    if re.search(r"\d{1,2}[./월]\d{1,2}", key):
        return True
    return False


def event_name(title, hubs):
    """제목에서 명시적으로 식별되는 행사명. 못 찾거나 후보가 둘 이상이면 None.

    1) 따옴표·홑화살괄호 안의 이름(끝의 '팝업/팝업스토어'는 뗌)
    2) 제목에서 '팝업' 바로 앞 낱말(라틴 문자 낱말은 최대 3개 이어 붙임)
    거점 이름·지역·일반 낱말은 이름으로 쓰지 않는다. 글 제목 전체를 이름으로 쓰지 않는다.
    """
    t = normalize_text(title)
    aliases = {name_key(a) for h in hubs for a in h["aliases"]} | {
        name_key(h["name"]) for h in hubs
    }
    names = []
    for raw in _quoted_names(t):
        cand = re.sub(r"\s*(?:팝업\s*스토어|팝업스토어|팝업)\s*$", "", raw).strip()
        if cand and not _is_generic(cand, aliases) and len(cand) <= 30:
            names.append(dict(name=cand, how="quoted"))
    if not names:
        for m in re.finditer(r"팝업", t):
            head = t[: m.start()]
            # 붙여 쓴 경우(무신사팝업)도 앞 낱말로 본다.
            tokens = re.findall(r"[가-힣A-Za-z0-9&'’]+", head)
            if not tokens:
                continue
            last = tokens[-1]
            last = re.sub(r"(?:의|에서|에)$", "", last) if re.search(r"[가-힣]", last) else last
            if re.fullmatch(r"[A-Za-z0-9&'’]+", last):
                latin = [last]
                for tok in reversed(tokens[:-1]):
                    if re.fullmatch(r"[A-Za-z0-9&'’]+", tok) and len(latin) < 3:
                        latin.insert(0, tok)
                    else:
                        break
                last = " ".join(latin)
            if last and not _is_generic(last, aliases):
                names.append(dict(name=last, how="before_popup"))
    keys = {name_key(n["name"]) for n in names}
    if len(keys) != 1:
        return dict(
            name=None,
            key=None,
            how=None,
            reason="none" if not names else "several",
            candidates=[n["name"] for n in names],
        )
    n = names[0]
    return dict(
        name=n["name"],
        key=name_key(n["name"]),
        how=n["how"],
        reason=None,
        candidates=[n["name"]],
    )


# ---------------------------------------------------------------- 대표 사진(2026-11-19 사용자 결정)
# 팝업 글 소개 옆에 작은 대표 사진 한 장을 둔다(app/popup_api.post_photos). 행사명(event_name)은 사진 검색어를 만드는 데만 쓰고
# 항목에 이름 필드로 싣거나 글을 묶지 않는다(출처 하나 = 항목 하나는 그대로).
# 사진 제목 거르기(photo_title_match) — 애매하면 쓰지 않는다:
#   · 행사명이 제목에 있다(공백·기호 무시). 두 글자 이하 이름은 '이름+팝업'처럼 바로 붙어 있어야 한다.
#   · 제목에 '팝업'(pop-up)이 있다.
#   · 제목이 말하는 거점이 우리 거점 하나뿐이다(다른 거점·다른 시·도 팝업이면 다른 행사 사진).
#   · 여러 팝업을 모은 제목(N곳·TOP N·모음·총정리·정리 등)이 아니다.
#   · 제목의 연도(20NN)는 방문 연도여야 한다(1~2월 방문은 전년도 허용). 같은 이름의 지난 행사 사진을 막는다.
PHOTO_ROUNDUP = re.compile(r"\d+\s*(?:곳|선|군데|개)|(?<![a-z])(?:top|best)(?![a-z])|베스트|모음|모아|총정리|정리|리스트|일정", re.I)
_YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def photo_title_match(title, name, hub, region, visit, hubs):
    """이미지 검색 결과 제목이 이 팝업(이름·거점)의 사진인지. hub 는 HUBS 의 거점 dict."""
    t = normalize_text(title)
    key, compact = name_key(name), name_key(t)
    if len(key) < 2 or key not in compact:
        return False
    if "팝업" not in compact and "popup" not in compact:
        return False
    if len(key) <= 2 and key + "팝업" not in compact and key + "popup" not in compact:
        return False
    if PHOTO_ROUNDUP.search(t) or _COUNT_PLACES.search(t):
        return False
    if title_other_region(t, region):
        return False
    current = {m["id"] for m in match_hubs(t, hubs) if m["context"] == "current"}
    if current != {hub["id"]}:
        return False
    years = {int(y) for y in _YEAR.findall(t)}
    allowed = {visit.year} | ({visit.year - 1} if visit.month <= 2 else set())
    return years <= allowed


# ---------------------------------------------------------------- URL 중복 제거·묶기


def canonical_url(url):
    """URL 비교용: 스킴·호스트 소문자, m.blog.naver.com → blog.naver.com, 끝 '/' 와 조각(#) 제거."""
    try:
        p = urlsplit(str(url or "").strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    host = p.hostname.lower()
    if host == "m.blog.naver.com":
        host = "blog.naver.com"
    path = p.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, p.query, ""))


def dedupe_by_url(posts, field="url"):
    """처음 나온 글을 남긴다. URL 이 없거나 http(s) 가 아니면 버린다."""
    seen = set()
    out = []
    for post in posts:
        key = canonical_url(post.get(field))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(post)
    return out


def _span(p):
    """비교용 (시작, 종료). 연도를 모르면 월·일만으로 비교."""
    if p["year_known"]:
        return ("y", p["start"], p["end"])
    return ("md", p["start_md"], p["end_md"])


def _overlap(a, b):
    """같은 축(연도 확인/월·일)에서 두 기간이 겹치는지. 한쪽 끝이 없으면 판단하지 않음(None)."""
    sa, sb = _span(a), _span(b)
    if sa[0] != sb[0] or None in (sa[1], sa[2], sb[1], sb[2]):
        return None
    if a["crosses_year"] or b["crosses_year"]:
        return None
    return not (sa[2] < sb[1] or sb[2] < sa[1])


def card_id(hub_id, key, period):
    raw = "|".join(
        [
            str(hub_id),
            str(key),
            repr(_span(period)) if period else "none",
        ]
    )
    return "popup:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def group_posts(posts):
    """보수적인 묶기. 입력 글: dict(url, hub_id, name_key, period(or None), conflict(bool)).

    - 거점 ID 와 이름 키가 같아야 같은 무리 후보
    - 같은 기간 → 한 카드
    - 기간이 서로 겹치지 않음 → 다른 회차, 다른 카드
    - 기간이 겹치지만 다름, 비교할 수 없음 → 한 카드에 두되 conflict(출처마다 기간이 달라요). 넓은 기간으로 합치지 않음
    - 기간 없는 글: 그 이름의 기간 카드가 정확히 하나일 때만 붙이고, 둘 이상이면 따로 '기간 미확인' 카드
    - 거점·이름이 없는 글은 묶지 않는다(호출하는 쪽이 보류로 셈)
    결과 순서는 (거점, 이름 키, 기간, 카드 ID) 로 재현 가능.
    """
    by_key = {}
    for post in sorted(
        posts,
        key=lambda p: (
            str(p["hub_id"]),
            str(p["name_key"]),
            canonical_url(p["url"]) or "",
        ),
    ):
        if not post.get("hub_id") or not post.get("name_key"):
            continue
        by_key.setdefault((post["hub_id"], post["name_key"]), []).append(post)
    cards = []
    for (hub_id, key), rows in sorted(by_key.items()):
        dated = [r for r in rows if r.get("period") and not r.get("conflict")]
        undated = [r for r in rows if not r.get("period") or r.get("conflict")]
        groups = []  # 각 무리: dict(periods=[...], posts=[...])
        for r in dated:
            placed = False
            for g in groups:
                if any(_span(r["period"]) == _span(p) for p in g["periods"]):
                    g["posts"].append(r)
                    placed = True
                    break
            if placed:
                continue
            for g in groups:
                rel = [_overlap(r["period"], p) for p in g["periods"]]
                if all(x is False for x in rel):
                    continue
                g["periods"].append(r["period"])
                g["posts"].append(r)
                placed = True
                break
            if not placed:
                groups.append(dict(periods=[r["period"]], posts=[r]))
        if len(groups) == 1 and undated:
            groups[0]["posts"].extend(undated)
            undated = []
        for g in groups:
            conflict = len({_span(p) for p in g["periods"]}) > 1 or any(
                p.get("conflict") for p in g["posts"]
            )
            first = sorted(g["periods"], key=lambda p: repr(_span(p)))[0]
            cards.append(
                dict(
                    id=card_id(hub_id, key, first),
                    hub_id=hub_id,
                    name_key=key,
                    periods=g["periods"],
                    conflict=conflict,
                    urls=sorted(canonical_url(p["url"]) for p in g["posts"]),
                )
            )
        if undated:
            cards.append(
                dict(
                    id=card_id(hub_id, key, None),
                    hub_id=hub_id,
                    name_key=key,
                    periods=[],
                    conflict=any(p.get("conflict") for p in undated),
                    urls=sorted(canonical_url(p["url"]) for p in undated),
                )
            )
    cards.sort(
        key=lambda c: (
            c["hub_id"],
            c["name_key"],
            repr([_span(p) for p in c["periods"]]),
            c["id"],
        )
    )
    return cards


def group_status(card, visit):
    """카드 상태: 기간 충돌이면 기간 미확인(종료로 숨기지 않음)."""
    if card["conflict"] or len(card["periods"]) != 1:
        return dict(
            status="unknown",
            end_only=False,
            reason="conflict" if card["conflict"] else "no_period",
        )
    return visit_status(card["periods"][0], visit)
