"""레저 종목 목록(한 곳에서 정의)과 요청 문장·장소 이름·업종 분류의 종목 판별 규칙.

- words: 요청 문장에서 알아듣는 낱말. 첫 낱말은 '○○ 요청 반영' 같은 안내에 쓰는 이름이다.
- request: 요청 문장 판별 정규식. place: 장소 이름·업종 판별 정규식(요청보다 좁다).
  넓은 낱말은 혼동 방지 조건을 붙인다: '수영구'(부산 지명)·'쇼핑 카트'·'위스키'·'웹 서핑'·'등산로 입구 카페' 등.
- setting: 기본 실내/실외. varies=True 면 시설에 따라 다르다(이름·업종에 '실내'/'야외' 단서가 있으면 그것을 따른다).
- terms: 사용자가 종목을 직접 요청했을 때의 지역 검색어(최대 2개).
"""

import re
from dataclasses import dataclass, field


def w(word, before=(), after=None):
    """낱말 정규식. before: 바로 앞에 오면 안 되는 말, after: 바로 뒤에 오면 안 되는 말(정규식)."""
    return "".join(f"(?<!{b})" for b in before) + re.escape(word) + (f"(?!{after})" if after else "")


NOT_SCREEN_INDOOR = ("스크린", "스크린 ", "실내", "실내 ")
NOT_HANGUL_BEFORE = "(?<![가-힣])"


@dataclass(frozen=True)
class Sport:
    key: str
    label: str
    setting: str
    varies: bool
    group: str
    terms: tuple
    words: tuple
    request: tuple
    place: tuple = ()
    indoor_cues: tuple = ()
    outdoor_cues: tuple = ()
    request_re: re.Pattern = field(init=False, repr=False, compare=False)
    place_re: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "request_re", re.compile("|".join(self.request), re.I))
        object.__setattr__(self, "place_re", re.compile("|".join(self.place or self.request), re.I))


def simple(*words):
    return tuple(w(x) for x in words)


# 순서: 기존 여섯 종목 → 새 실내 종목 → 실외 종목. 요청 해석 결과(intents)의 순서도 이 순서를 따른다.
SPORTS = (
    Sport("climbing", "클라이밍", "indoor", False, "실내 활동", ("클라이밍",), ("클라이밍", "볼더링", "암벽"),
          simple("클라이밍", "볼더링", "암벽")),
    Sport("bowling", "볼링", "indoor", False, "실내 게임", ("볼링",), ("볼링",), simple("볼링")),
    Sport("table_tennis", "탁구", "indoor", False, "실내 코트", ("탁구",), ("탁구",), simple("탁구")),
    Sport("badminton", "배드민턴", "indoor", False, "실내 코트", ("배드민턴",), ("배드민턴",), simple("배드민턴")),
    # 서울광장 스케이트장처럼 계절 야외 링크도 있어 시설에 따라 다르다.
    Sport("skating", "아이스 스케이트", "indoor", True, "빙상·롤러", ("스케이트",), ("스케이트", "스케이팅", "아이스링크"),
          (w("스케이트", ("롤러", "롤러 ", "인라인", "인라인 ")), w("스케이팅", ("롤러", "롤러 ", "인라인", "인라인 ")), w("아이스링크"))),
    Sport("screen_golf", "스크린골프", "indoor", False, "스크린", ("스크린골프",), ("스크린골프", "스크린 골프"),
          simple("스크린골프", "스크린 골프")),
    # '빌리어드'는 당구장 상호에 흔하다(장소 판별에만 쓴다).
    Sport("billiards", "당구·포켓볼", "indoor", False, "실내 게임", ("당구장",), ("당구", "포켓볼"), simple("당구", "포켓볼"),
          simple("당구", "포켓볼", "빌리어드")),
    Sport("screen_baseball", "스크린야구", "indoor", False, "스크린", ("스크린야구",), ("스크린야구", "스크린 야구", "배팅센터"),
          simple("스크린야구", "스크린 야구", "배팅센터")),
    Sport("indoor_tennis", "실내 테니스", "indoor", False, "스크린",
          ("실내테니스",), ("실내테니스", "실내 테니스", "스크린테니스", "스크린 테니스"),
          simple("실내테니스", "실내 테니스", "스크린테니스", "스크린 테니스")),
    Sport("archery", "양궁", "indoor", True, "실내 활동", ("실내양궁",), ("양궁", "활쏘기"), simple("양궁", "활쏘기")),
    Sport("shooting", "사격", "indoor", True, "실내 활동", ("사격장",), ("사격",), simple("사격"), outdoor_cues=("클레이",)),
    # '다트'는 상호에 섞일 수 있어(다트머스 등) 뒤에 다른 한글 낱말이 붙으면 다트로 보지 않는다.
    Sport("darts", "다트", "indoor", False, "실내 게임", ("다트",), ("다트",),
          (r"(?<![가-힣])다트(?![가-힣])|다트(?=바|카페|존|게임|펍|장|하러|치러|던지)",),
          (r"다트(?![가-힣])|다트(?=바|카페|존|게임|펍|장)",)),
    Sport("roller", "롤러스케이트", "indoor", True, "빙상·롤러", ("롤러장",), ("롤러스케이트", "롤러 스케이트", "롤러장", "인라인"),
          simple("롤러스케이트", "롤러 스케이트", "롤러장", "롤러스케이팅", "인라인")),
    # '점핑'·'방방'은 운동 강좌·다른 뜻과 겹쳐 넣지 않는다.
    Sport("trampoline", "트램폴린", "indoor", False, "실내 활동", ("트램폴린",), ("트램폴린", "트램펄린", "점핑파크"),
          simple("트램폴린", "트램펄린", "점핑파크")),
    # '수영구'(부산)·'수영로'·'수영강'·사람 이름(김수영)과 겹치지 않게 한다. 장소는 '수영장'만 본다.
    Sport("swimming", "수영", "indoor", True, "물놀이", ("수영장",), ("수영", "수영장"),
          (NOT_HANGUL_BEFORE + r"수영(?!구|로|동|강|만|역|교|초|중|고|여|대)", w("수영장")), (w("수영장"),)),
    Sport("squash", "스쿼시", "indoor", False, "실내 코트", ("스쿼시",), ("스쿼시",), simple("스쿼시")),
    Sport("indoor_surfing", "실내 서핑", "indoor", False, "실내 활동", ("실내서핑",), ("실내서핑", "실내 서핑", "플로우라이더"),
          simple("실내서핑", "실내 서핑", "플로우라이더")),
    Sport("indoor_ski", "실내 스키·스노보드", "indoor", False, "실내 활동", ("실내스키",),
          ("실내스키", "실내 스키", "실내스노보드", "실내 스노보드"),
          simple("실내스키", "실내 스키", "실내스노보드", "실내 스노보드", "스키 시뮬레이터", "스키시뮬레이터")),
    Sport("vr_sports", "VR 스포츠", "indoor", False, "실내 활동", ("VR스포츠",), ("VR스포츠", "VR 스포츠", "스포츠VR"),
          simple("VR스포츠", "VR 스포츠", "스포츠VR", "스포츠 VR")),
    Sport("basketball", "농구 코트", "indoor", True, "실내 코트", ("농구장",), ("농구",),
          (NOT_HANGUL_BEFORE + r"농구(?!공|화)",), (w("농구장"), w("농구 코트"), w("농구코트"), w("농구"))),
    # ---- 실외 ----
    # '자전거로 이동'은 이동 수단이지 활동이 아니다(request_intent 의 이동 수단 해석과 같은 표현).
    Sport("cycling", "자전거·레일바이크", "outdoor", False, "육상 레저", ("자전거 대여", "레일바이크"),
          ("자전거", "라이딩", "레일바이크"),
          (r"자전거(?!\s*(?:로|타고\s*(?:이동|가|갈|와)))", w("라이딩"), w("레일바이크")),
          (w("자전거 대여"), w("자전거대여"), w("레일바이크"), w("바이크 대여"), w("자전거"))),
    Sport("paddle", "카약·카누·패들보드", "outdoor", False, "수상 레저", ("카약", "패들보드"),
          ("카약", "카누", "패들보드", "SUP"),
          (w("카약"), w("카누"), w("패들보드"), w("패들 보드"), r"(?<![A-Za-z])SUP(?![A-Za-z])")),
    Sport("surfing", "서핑", "outdoor", False, "수상 레저", ("서핑",), ("서핑",),
          (w("서핑", ("실내", "실내 ", "웹", "웹 ", "넷", "넷 ")),)),
    Sport("boating", "요트·보트", "outdoor", False, "수상 레저", ("요트", "유람선"), ("요트", "보트", "오리배", "유람선", "크루즈"),
          (NOT_HANGUL_BEFORE + "요트", NOT_HANGUL_BEFORE + "보트", w("오리배"), w("유람선"), w("크루즈"))),
    Sport("water_leisure", "수상레저", "outdoor", False, "수상 레저", ("수상레저",),
          ("수상레저", "수상스키", "웨이크보드", "바나나보트", "제트스키"),
          simple("수상레저", "수상 레저", "수상스키", "웨이크보드", "바나나보트", "제트스키")),
    # '등산로 입구 카페' 같은 상호는 등산 장소가 아니다. 장소는 등산로·등산코스·트레킹만 본다.
    Sport("hiking", "등산·트레킹", "outdoor", False, "육상 레저", ("등산로",), ("등산", "트레킹", "하이킹", "산행"),
          (NOT_HANGUL_BEFORE + r"등산(?!복|화|용품|가방|스틱|객)", w("트레킹"), w("하이킹"), NOT_HANGUL_BEFORE + "산행"),
          (r"등산(?:로|코스)(?!\s*(?:입구)?\s*(?:카페|식당|맛집))", w("트레킹"), w("하이킹"))),
    Sport("tennis", "테니스", "outdoor", True, "야외 코트", ("테니스장",), ("테니스",), (w("테니스", NOT_SCREEN_INDOOR),)),
    Sport("futsal", "풋살", "outdoor", True, "야외 코트", ("풋살장",), ("풋살",), simple("풋살")),
    Sport("horse_riding", "승마", "outdoor", True, "육상 레저", ("승마장",), ("승마",), simple("승마")),
    # '카트'만으로는 쇼핑 카트와 겹친다. 고카트·카트장·카트 타기 같은 표현만 본다.
    Sport("kart_luge", "카트·루지", "outdoor", False, "육상 레저", ("카트장", "루지"),
          ("고카트", "카트레이싱", "카트장", "루지"),
          (w("고카트"), w("카트레이싱"), w("카트 레이싱"), w("카트장"),
           NOT_HANGUL_BEFORE + r"카트\s*(?:타|레이스|체험)", NOT_HANGUL_BEFORE + r"루지(?![가-힣])", r"루지(?=장|체험|파크|타)"),
          (w("고카트"), w("카트레이싱"), w("카트 레이싱"), w("카트장"), w("카트 체험"),
           NOT_HANGUL_BEFORE + r"루지(?![가-힣])", r"루지(?=장|체험|파크)")),
    Sport("zipline", "짚라인", "outdoor", False, "육상 레저", ("짚라인",), ("짚라인", "집라인", "짚와이어", "집와이어"),
          simple("짚라인", "집라인", "짚와이어", "집와이어")),
    # 골프연습장은 넣지 않는다(실내·실외 연습장이 섞이고 데이트 레저 근거가 약하다).
    Sport("golf", "파크골프·골프", "outdoor", False, "육상 레저", ("파크골프장",), ("파크골프", "골프장", "라운딩"),
          (w("파크골프"), w("골프장", ("스크린", "스크린 ")), NOT_HANGUL_BEFORE + "라운딩"),
          (w("파크골프"), w("골프장", ("스크린", "스크린 ")), w("컨트리클럽"))),
    # '위스키'·'스키니'는 스키가 아니다. 실내 스키는 indoor_ski 로 따로 본다.
    Sport("ski", "스키·눈썰매", "outdoor", False, "겨울 레저", ("스키장", "눈썰매장"), ("스키", "스키장", "스노보드", "눈썰매", "썰매장"),
          (NOT_HANGUL_BEFORE + r"(?<!실내 )스키(?!니|드|\s*시뮬)", w("스노보드", ("실내", "실내 ")), w("눈썰매"), w("썰매장"))),
    # '낚시카페'는 실내 낚시다. '낚시성 글' 같은 표현은 낚시로 보지 않는다.
    Sport("fishing", "낚시", "outdoor", True, "수상 레저", ("낚시터",), ("낚시",), (w("낚시", after="성"),),
          indoor_cues=("낚시카페", "실내낚시")),
    Sport("paragliding", "패러글라이딩", "outdoor", False, "하늘 레저", ("패러글라이딩",),
          ("패러글라이딩", "패러 글라이딩", "행글라이딩"), simple("패러글라이딩", "패러 글라이딩", "행글라이딩")),
)
BY_KEY = {s.key: s for s in SPORTS}
KEYS = tuple(BY_KEY)
OUTDOOR_KEYS = frozenset(s.key for s in SPORTS if s.setting == "outdoor")

# 장소 판별 순서: 더 구체적인 종목을 먼저 본다('롤러스케이트'는 스케이트보다, '스크린골프'는 골프보다 먼저).
FIRST = ("roller", "indoor_tennis", "indoor_surfing", "indoor_ski", "screen_golf", "screen_baseball", "vr_sports")
PRIORITY = tuple(BY_KEY[k] for k in FIRST) + tuple(s for s in SPORTS if s.key not in FIRST)
# 여러 종목을 아우르는 넓은 종목. 업종·상호에서 더 구체적인 종목을 찾지 못했을 때만 고른다.
GENERIC = frozenset({"water_leisure"})

# 레저 업종으로 볼 수 있는 업종 분류 낱말. 업종에 종목 낱말이 없으면 이 낱말이 있어야 상호로 종목을 정한다.
LEISURE_CATEGORY = ("스포츠", "레저", "레포츠", "체육", "오락", "여행", "명소", "관광", "테마", "체험", "수상", "놀이", "공원", "캠핑")
# 잡음: 용품·판매·수리점, 학원·교습소, 협회·사무실, 병원·마사지, 숙박·부동산 등. 확신할 수 없으면 후보에서 뺀다.
NOISE_CATEGORY = ("용품", "판매", "쇼핑", "유통", "도매", "수리", "정비", "제조", "학원", "교습", "교육", "협회", "연맹", "단체",
                  "사무", "기업", "회사", "병원", "의원", "약국", "마사지", "재활", "물리치료", "부동산", "자동차", "주차장", "숙박")
NOISE_NAME = ("용품", "프로샵", "판매", "수리점", "수리센터", "중고", "학원", "교습소", "협회", "연맹", "사무실", "사무소",
              "마사지", "병원", "의원", "클리닉", "재활", "도매")
INDOOR_CUE = re.compile(r"실내")
OUTDOOR_CUE = re.compile(r"야외|실외|아웃도어|노천")


# 상호의 가게 표현. '스토어'·'샵'·'숍'은 판매점이라 업종이 '당구장'이어도 뺀다(실제 검색에서 'SS빌리어드스토어'가
# 업종 '당구장'으로 잡혔다). '몰'·'마트'는 '○○몰 볼링장'처럼 시설이 든 건물 이름일 수 있어, 업종 끝이 '…장' 시설일 때만 남긴다.
SHOP_NAME = re.compile(r"스토어|샵|숍")
MALL_NAME = re.compile(r"(?<!스)마트|몰(?![가-힣])|쇼핑몰")
FACILITY_CATEGORY = re.compile(r"[가-힣]+장$")


def noise(category, name):
    if any(x in category for x in NOISE_CATEGORY) or any(x in name for x in NOISE_NAME) or SHOP_NAME.search(name):
        return True
    return bool(MALL_NAME.search(name)) and not FACILITY_CATEGORY.search(category.split(">")[-1].strip())


def classify(category, name=""):
    """네이버 지역 검색 업종(category)과 상호(name)로 종목을 고른다. 확신할 수 없거나 잡음이면 None.

    업종에 종목 낱말이 있으면 업종을 따르고, 없으면 업종이 레저·스포츠 계열일 때만 상호로 정한다.
    """
    category = str(category or "")
    name = str(name or "")
    if noise(category, name):
        return None
    specific = [s for s in PRIORITY if s.key not in GENERIC]
    for sport in specific:
        if sport.place_re.search(category):
            return sport
    gate = any(x in category for x in LEISURE_CATEGORY)
    if gate:
        for sport in specific:
            if sport.place_re.search(name):
                return sport
    # '수상레저'처럼 넓은 종목은 더 구체적인 종목(카약 등)이 없을 때만 쓴다.
    for sport in PRIORITY:
        if sport.key in GENERIC and (sport.place_re.search(category) or (gate and sport.place_re.search(name))):
            return sport
    return None


def setting_of(sport, text):
    """(실내/실외, 근거). 근거 'cue' 는 이름·업종의 단서, 'default' 는 종목 기본값."""
    text = str(text or "")
    if INDOOR_CUE.search(text) or any(c in text for c in sport.indoor_cues):
        return "indoor", "cue"
    if OUTDOOR_CUE.search(text) or any(c in text for c in sport.outdoor_cues):
        return "outdoor", "cue"
    return sport.setting, "default"


def mentioned(text):
    """요청 문장에서 종목별 (긍정·부정 판단 전) 일치 위치. request_intent.interpret 가 부정 표현을 판단한다."""
    return {s.key: list(s.request_re.finditer(text)) for s in SPORTS}


def place_text(place):
    return " ".join(
        str(v)
        for v in [place.get("name"), place.get("description"), place.get("cuisine"), *(place.get("tags") or [])]
        if v
    )


def place_sport(place):
    """장소 하나의 종목(Sport) 또는 None.

    - 태그에 종목 키가 있으면 그 종목(검색으로 찾은 장소는 분류할 때 키를 태그로 남긴다).
    - 네이버 지역 검색 결과는 원래 업종(description)과 상호로 classify 한다.
    - 그 밖의 장소는 식사·카페가 아니고 분류가 레저 계열일 때만 상호로 판단한다.
    """
    tags = place.get("tags") or []
    for key in tags:
        if key in BY_KEY:
            return BY_KEY[key]
    if place.get("meal") or str(place.get("id", "")).startswith("food:") or place.get("category") == "카페·미식":
        return None
    if "네이버 지역 검색" in str(place.get("source_type") or ""):
        return classify(place.get("description") or "", place.get("name") or "")
    category = " ".join(str(x) for x in [place.get("category"), *tags] if x)
    return classify(category, place.get("name") or "")
