"""블로그 후기 본문에서 읽은 영업시간·휴무(참고용). 추천 계산에는 쓰지 않고 결과 화면에 '후기 기준'으로만 보인다.

장소 블로그 검색(blog_search.place_blogs, 1시간 캐시)이 고른 글 최대 3개의 공개 본문(course_search.public_body)을 읽는다.
한 글에 여러 장소가 나오므로 장소 이름이 나온 자리 바로 뒤(WINDOW 글자)에서만 '영업·운영·이용 시간 HH:MM~HH:MM'과
휴무 표현을 찾는다. 공원·해변 같은 산책·풍경 장소는 근처 가게의 시간이 잡히기 쉬워 읽지 않는다.
이름과 시간 사이에 다른 시·군·구 주소가 나오면(다른 지점) 버린다.

2026-11-16 측정(인기 동네 6곳 추천 장소 41곳, 글 101개): 위 규칙으로 23곳에서 영업시간을 읽었고, 근거 문장을 사람이 본 판정으로
23곳 모두 그 장소의 시간이었습니다(규칙을 이 표본을 보며 정했으므로 새 표본에서의 정확도는 아님).
"""

import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import store

CACHE_SECONDS = 24 * 3600
EMPTY_SECONDS = 3600
WINDOW = 700
SKIP_CATEGORIES = {"산책·풍경"}
# 상호 앞뒤의 지역·지점 낱말(이름으로 찾을 때 없어도 되는 말).
PLACE_WORDS = re.compile(r"^(?:본점|\d*호점|.{0,8}점)$")
GEO_WORD = re.compile(r"(?:해변|해수욕장|길|동|읍|면|리|역|시장|공원|마을|거리|단지)$")
TIME = r"(?:[01]?\d|2[0-4])\s*:\s*[0-5]\d"
HOURS = re.compile(
    r"(?:영업|운영|이용|오픈|관람)\s*시간[^0-9]{0,20}("
    + TIME
    + r"\s*(?:~|-|–|부터)\s*(?:익일\s*)?"
    + TIME
    + ")"
)
# 시간 바로 앞의 요일 꾸밈("매일", "월~목요일", "평일")은 근거로 함께 보인다.
DAYS = re.compile(
    r"(매일|평일|주말|[월화수목금토일](?:요일)?\s*(?:~|-)\s*[월화수목금토일](?:요일)?)[^0-9]{0,6}$"
)
REST = re.compile(
    r"(?:정기\s*)?휴무(?:일)?\s*[:：]?\s*(?:매주\s*)?[월화수목금토일](?:요일)?"
    r"|[월화수목금토일]요일\s*(?:정기\s*)?휴무|연중\s*무휴"
)
DISTRICT = re.compile(r"([가-힣]{1,4}(?:시|군|구))(?=\s)")
METRO = {"특별시", "광역시", "자치시"}


def name_patterns(place):
    """본문에서 찾을 장소 이름(띄어쓰기 무시). 전체 이름과, 지역·지점 낱말을 뺀 이름."""
    from .regions import ALIASES

    words = [w for w in str(place.get("name") or "").split() if w]
    keep = [w for w in words if w not in ALIASES and not PLACE_WORDS.match(w)] or words
    address = "".join(str(place.get("address") or "").split())
    # 낱말 하나로도 찾되, 지명처럼 보이는 낱말(주소에 들어 있거나 해변·길·동·역 등으로 끝남)은 다른 가게 글에도 흔해 쓰지 않는다.
    alone = (
        {w for w in keep if len(w) >= 3 and w not in address and not GEO_WORD.search(w)}
        if len(keep) > 1
        else set()
    )
    names = {"".join(words), "".join(keep)} | alone
    names = sorted((n for n in names if len(n) >= 2), key=len, reverse=True)
    return [re.compile(r"\s*".join(map(re.escape, n))) for n in names]


def districts(address):
    """주소의 시·군·구 낱말(광역시·특별시 이름은 뺌)."""
    found = set()
    for word in DISTRICT.findall(str(address or "") + " "):
        if not any(word.endswith(m) for m in METRO):
            found.add(word)
    return found


def other_branch(segment, own):
    """이름과 시간 사이에 이 장소의 시·군·구가 아닌 시·군·구만 나오면 다른 지점으로 본다."""
    if not own:
        return False
    seen = districts(segment)
    return bool(seen) and not (seen & own)


def read_post(body, place):
    """한 글 본문에서 (영업시간 문구, 휴무 문구, 근거 문장) 목록."""
    own = districts(place.get("address"))
    starts = sorted({m.start() for pattern in name_patterns(place) for m in pattern.finditer(body)})
    found = []
    for start in starts:
        window = body[start : start + WINDOW]
        hours = HOURS.search(window)
        if hours and not other_branch(window[: hours.start()], own):
            span = re.sub(r"\s+", "", hours.group(1)).replace("–", "~").replace("-", "~")
            days = DAYS.search(window[: hours.start(1)])
            text = (days.group(1).replace(" ", "") + " " if days else "") + span
            evidence = " ".join(window[: hours.end()].split())[-120:]
            rest = REST.search(window)
            found.append((text, " ".join(rest.group(0).split()) if rest else None, evidence))
    return found


def review_facts(place):
    """GET /api/places/{id}/review-facts 의 응답."""
    empty = dict(
        status="not_found",
        hours=None,
        closed=None,
        source=None,
        evidence=None,
        note="블로그 후기에 적힌 정보예요. 지금과 다를 수 있어요.",
    )
    if place.get("demo"):
        return dict(empty, status="demo")
    if place.get("category") in SKIP_CATEGORIES or place.get("hours"):
        return dict(empty, status="skipped")
    from .blog_search import place_blogs

    blogs = place_blogs(place)
    if blogs.get("status") != "available":
        return dict(empty, status=blogs.get("status") or "unavailable")
    posts = blogs["posts"][:3]
    key = (
        "review-facts-v1:"
        + hashlib.sha256(
            repr([place.get("id"), place.get("name"), [p["url"] for p in posts]]).encode()
        ).hexdigest()
    )
    cached = store.cached(key)
    if cached:
        return cached
    from .course_search import public_body
    from .request_usage import context_map
    from .telemetry import prepaid

    with (
        prepaid("https://m.blog.naver.com/", len(posts)),
        ThreadPoolExecutor(max_workers=3) as pool,
    ):
        bodies = context_map(pool, public_body, [p["url"] for p in posts])
    votes, first = Counter(), {}
    for post, body in zip(posts, bodies):
        # 한 글 안에서 이름이 여러 번 나와도 같은 시간은 한 표.
        seen = set()
        for hours, closed, evidence in read_post(body or "", place):
            if hours not in seen:
                seen.add(hours)
                votes[hours] += 1
            first.setdefault(hours, (post, closed, evidence))
    if not votes:
        result = dict(empty, read_posts=sum(1 for b in bodies if b))
        store.cache(key, result, EMPTY_SECONDS)
        return result
    hours, _ = votes.most_common(1)[0]
    post, closed, evidence = first[hours]
    result = dict(
        empty,
        status="available",
        hours=hours,
        closed=closed,
        evidence=evidence,
        agreeing_posts=votes[hours],
        read_posts=sum(1 for b in bodies if b),
        source=dict(
            url=post["url"],
            title=post["title"],
            posted_at=post.get("posted_at"),
            blogger=post.get("blogger"),
        ),
    )
    store.cache(key, result, CACHE_SECONDS)
    return result
