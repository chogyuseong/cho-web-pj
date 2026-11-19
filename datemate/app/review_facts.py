"""블로그 후기 본문에서 읽은 영업시간·휴무와 메뉴 가격 예(참고용). 추천 계산에는 쓰지 않고 결과 화면에 '후기 기준'으로만 보인다.

장소 블로그 검색(blog_search.place_blogs, 1시간 캐시)이 고른 글 최대 3개의 공개 본문(course_search.public_body)을 읽는다.
한 글에 여러 장소가 나오므로 장소 이름이 나온 자리 바로 뒤(WINDOW 글자)에서만 '영업·운영·이용 시간 HH:MM~HH:MM'과
휴무 표현을 찾는다. 공원·해변 같은 산책·풍경 장소는 근처 가게의 시간이 잡히기 쉬워 읽지 않는다.
이름과 시간 사이에 다른 시·군·구 주소가 나오면(다른 지점) 버린다.

2026-11-16 측정(인기 동네 6곳 추천 장소 41곳, 글 101개): 위 규칙으로 23곳에서 영업시간을 읽었고, 근거 문장을 사람이 본 판정으로
23곳 모두 그 장소의 시간이었습니다(규칙을 이 표본을 보며 정했으므로 새 표본에서의 정확도는 아님).
가격은 같은 표본에서 18곳에 메뉴 가격이 읽혔습니다. 2인 세트·추가 금액이 섞일 수 있어 비용 계산에는 쓰지 않고 '가격 예'로만 보입니다.
"""

import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import naver_cache

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
    # 요일 글자는 띄어쓰기·쌍점·'매주' 뒤에서만 읽는다('휴무일'의 '일'을 일요일로 읽지 않게).
    r"(?:정기\s*)?휴무일?\s*[:：]?\s*(?:매주\s*)?(?<=[\s:：주])(?:[월화수목금토일]요일|[월화수목금토일](?![가-힣]))"
    r"|[월화수목금토일]요일\s*(?:정기\s*)?휴무|연중\s*무휴"
)
# 가격: 장소 이름 뒤 PRICE_WINDOW 글자 안의 '메뉴 이름 N원'. 주차·배달·할인·합계·여러 개 묶음 같은 금액은 뺀다.
PRICE_WINDOW = 1500
AMOUNT = re.compile(r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{4,6})\s*원")
ITEM_WORD = re.compile(r"[가-힣A-Za-z0-9()&+]+")
# 메뉴 이름 앞에서 멈출 낱말: 주소(숫자·길·로·층·호), 안내 낱말, 지점 이름.
ITEM_STOP = re.compile(
    r"^(?:[\d\-]+|\d+원|.*\d+(?:길|로|번길|층|호|동)|메뉴.*|가격.*|주문.*|먹은|각각|기본|대표|인기|추천|티켓|예매|.{2,}점|.*(?:요|다|고|서|며|죠|네)|.*[었았였했])$"
)
NOT_MENU = re.compile(
    r"시간\s*당|분\s*당|최대|하루|합쳐|합계|총|이후|추가\s*요금|\d\s*개|주차|배달|택배|배송|할인|적립|쿠폰|포인트"
    r"|보증금|대여|주유|교통|택시|요금제|월\s*\d|원대|결제|영수증|기본요금|정가|원가"
)
PRICE_RANGE = {"카페·미식": (2500, 60000), "체험·제작": (3000, 150000), "문화·예술": (1000, 50000)}
MAX_PRICES = 4
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


def item_name(before, place_key=""):
    """금액 바로 앞 글에서 메뉴 이름(낱말 최대 3개). 주소·안내 낱말·문장 끝말·지점·장소 이름에서 멈춘다."""
    words = ITEM_WORD.findall(before.split(":")[-1].split("：")[-1])
    picked = []
    for word in reversed(words):
        if ITEM_STOP.match(word) or (len(word) >= 4 and word in place_key):
            break
        picked.insert(0, word)
        if len(picked) == 3:
            break
    name = " ".join(picked).strip(" &+").rstrip("( ")
    if name.count("(") > name.count(")"):
        name += ")"
    return name.lstrip(")")


def read_prices(body, place):
    """한 글 본문에서 (메뉴 이름, 금액) 목록. 이름을 읽지 못한 금액은 버린다."""
    own = districts(place.get("address"))
    low, high = PRICE_RANGE.get(place.get("category"), (2000, 100000))
    starts = sorted({m.start() for pattern in name_patterns(place) for m in pattern.finditer(body)})
    found, used = [], set()
    place_key = "".join(str(place.get("name") or "").split())
    for start in starts:
        window = body[start : start + PRICE_WINDOW]
        for match in AMOUNT.finditer(window):
            at = start + match.start()
            if at in used:
                continue
            used.add(at)
            if other_branch(window[: match.start()], own):
                break
            amount = int(match.group(1).replace(",", ""))
            before = body[max(0, at - 25) : at]
            if not low <= amount <= high or NOT_MENU.search(before + match.group(0)):
                continue
            name = item_name(before, place_key)
            if len(re.sub(r"[^가-힣A-Za-z]", "", name)) >= 2:
                found.append((name, amount))
    return found


def review_facts(place):
    """GET /api/places/{id}/review-facts 의 응답."""
    empty = dict(
        status="not_found",
        hours=None,
        closed=None,
        source=None,
        evidence=None,
        prices=[],
        note="블로그 후기에 적힌 정보예요. 지금과 다를 수 있어요.",
    )
    if place.get("demo"):
        return dict(empty, status="demo")
    if place.get("category") in SKIP_CATEGORIES:
        return dict(empty, status="skipped")
    from .naver_pages import allowed

    if not allowed():
        # 후기 본문을 읽지 않으므로(app/naver_pages.py) 블로그 검색 요약만으로는 영업시간·가격을 읽지 않는다.
        # 2026-11-20: 공용 캐시를 없앤 뒤 사용자마다 나가는 쓸모없는 블로그 검색 호출을 하지 않는다.
        return dict(empty, status="not_found", read_posts=0)
    from .blog_search import place_blogs

    blogs = place_blogs(place)
    if blogs.get("status") != "available":
        return dict(empty, status=blogs.get("status") or "unavailable")
    posts = blogs["posts"][:3]
    key = (
        "review-facts-v3:"
        + hashlib.sha256(
            repr([place.get("id"), place.get("name"), [p["url"] for p in posts]]).encode()
        ).hexdigest()
    )
    cached = naver_cache.cached(key)
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
    # 가격: 여러 글에 나온 메뉴 이름(띄어쓰기 무시)마다 첫 금액, 많이 나온 순으로 MAX_PRICES 개.
    menu, menu_votes = {}, Counter()
    for post, body in zip(posts, bodies):
        for name, amount in read_prices(body or "", place):
            key_ = "".join(name.split())
            menu_votes[key_] += 1
            menu.setdefault(
                key_,
                dict(item=name, amount=amount, url=post["url"], posted_at=post.get("posted_at")),
            )
    prices = [menu[k] for k, _ in menu_votes.most_common(MAX_PRICES)]
    votes, first = Counter(), {}
    # 영업시간이 이미 확인된 장소는 후기 영업시간을 보이지 않는다(가격만).
    known_hours = bool(place.get("hours"))
    for post, body in zip(posts, bodies):
        if known_hours:
            break
        # 한 글 안에서 이름이 여러 번 나와도 같은 시간은 한 표.
        seen = set()
        for hours, closed, evidence in read_post(body or "", place):
            if hours not in seen:
                seen.add(hours)
                votes[hours] += 1
            first.setdefault(hours, (post, closed, evidence))
    read = sum(1 for b in bodies if b)
    if not votes and not prices:
        result = dict(empty, prices=[], read_posts=read)
        naver_cache.cache(key, result, EMPTY_SECONDS)
        return result
    result = dict(empty, status="available", prices=prices, read_posts=read)
    if votes:
        hours, _ = votes.most_common(1)[0]
        post, closed, evidence = first[hours]
        result.update(
            hours=hours,
            closed=closed,
            evidence=evidence,
            agreeing_posts=votes[hours],
            source=dict(
                url=post["url"],
                title=post["title"],
                posted_at=post.get("posted_at"),
                blogger=post.get("blogger"),
            ),
        )
    naver_cache.cache(key, result, CACHE_SECONDS)
    return result
