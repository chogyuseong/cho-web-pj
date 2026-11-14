"""팝업 후보 판정용 순수 함수 (0단계: 실측·검증 전용, 라우터·운영 화면 어디에도 연결하지 않음).

입력은 검색 API 가 돌려준 제목·요약·URL·출처 날짜뿐이다. 원문을 읽었다고 가정하지 않는다.
- normalize_text: 태그·엔티티를 텍스트로
- extract_period: 날짜 후보 → 달력 검사 → 행사 기간 문맥 → 연도·범위 불확실성 → 근거 보존
- visit_status: 7절 방문일 상태 표
- match_hubs: 8절 거점 매칭(긴 별칭 우선, 여러 거점이면 단일 장소로 강제하지 않음)
- classify_roundup / event_name: 9절 모아 보기 분류와 행사명 식별
- dedupe_by_url / group_posts: 9절 묶기(보수적, 재현 가능)
"""

import hashlib
import html
import math
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

RULES_VERSION = "popups-rules-v0"

# ---------------------------------------------------------------- 텍스트


def normalize_text(value):
    """검색 결과의 <b> 같은 태그를 지우고 HTML 엔티티를 글자로 바꾼 뒤 공백을 하나로. 결과는 텍스트로만 쓴다."""
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def has_popup(text):
    return "팝업" in str(text or "")


# ---------------------------------------------------------------- 날짜

_DOW = r"(?:\s*\(\s*[월화수목금토일](?:요일)?\s*\))?"
_UNIT_AFTER = re.compile(
    r"\s*(?:배|%|퍼센트|만|천|원|억|kg|g|km|m|cm|mm|ml|l|인치|점|년|대|시간|분|초|세|살|명|개|층|위|호|번|회|차|박|평|v)",
    re.I,
)
# 앞 글자가 숫자·점·영문이면 날짜가 아니다(버전 v2.1, 1.2.3, 소수 12.5.3 의 가운데).
_P_YMD = re.compile(
    r"(?<![\w.])(20\d{2})\s*(?:[./-]|년)\s*(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})(?!\d)(?:\s*일)?\.?"
)
_P_YYMD = re.compile(r"(?<![\w.])'?([2-3]\d)\.(\d{1,2})\.(\d{1,2})(?![\d])\.?")
_P_KMD = re.compile(r"(?<![\w.])(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_P_MD = re.compile(r"(?<![\w.])(\d{1,2})\s*[./]\s*(\d{1,2})(?!\d)(?!\.\d)\.?")
_CONNECT = re.compile(r"\s*(?:~|∼|～|〜|-|–|—|부터)\s*")
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
)
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
        if conn:
            j = conn.end()
            nxt = mentions[i + 1] if i + 1 < len(mentions) else None
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
                cand = dict(
                    type="start_only",
                    s=(m["year"], m["month"], m["day"]),
                    e=None,
                    span=(m["start"], m["end"]),
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
    parts = [re.escape(p) for p in alias.split()]
    return re.compile(r"\s*".join(parts), re.I)


def match_hubs(text, hubs):
    """글에 나온 거점들. 긴 별칭을 먼저 잡고 겹치는 짧은 별칭은 버린다.

    짧은 별칭(공백 제외 3글자 이하)은 앞 글자가 한글이면(지역명 바로 뒤는 허용) 매칭하지 않는다.
    반환: [dict(id, alias, span)] 글 안의 위치 순.
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
            found.append(dict(id=hub["id"], alias=m.group(0), span=(s, e)))
    found.sort(key=lambda r: r["span"])
    return found


def hub_match(text, hubs, region):
    """검색 지역 기준 판정.

    - single: 같은 지역 거점이 정확히 하나 → 그 거점
    - multiple: 같은 지역 거점이 둘 이상 → 단일 장소로 강제하지 않음
    - other_region: 다른 지역 거점만 있음
    - none: 없음
    """
    by_id = {h["id"]: h for h in hubs}
    ids = list(dict.fromkeys(m["id"] for m in match_hubs(text, hubs)))
    same = [i for i in ids if by_id[i]["region"] == region]
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
            )
        )
    if not passed:
        return dict(status="unverified", reason="no_matching_result", point=None, candidates=0)
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


_REGION_WORDS = {
    "서울": ("서울", "서울특별시", "서울시"),
    "부산": ("부산", "부산광역시", "부산시"),
    "대구": ("대구", "대구광역시", "대구시"),
    "대전": ("대전", "대전광역시", "대전시"),
}


def _region_word(word, region):
    return word in _REGION_WORDS.get(region, (region,))


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
