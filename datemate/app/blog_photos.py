"""Use only images captioned for the venue, never every image in a matching post."""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
import httpx
from . import store
from .image_search import safe_https, title_matches, image_aliases, search_enabled
from .request_usage import context_map
from .telemetry import observed_stream
from .public_place_photos import photo_identity


class CaptionImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.root = 0
        self.component = 0
        self.skip = 0
        self.current = None
        self.previous = ""
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "div":
            self.depth += 1
            if "se-main-container" in classes:
                self.root = self.depth
            if self.root and "se-component" in classes and not self.current:
                self.component = self.depth
                self.current = {"text": [], "images": [], "previous": self.previous}
        if tag == "img" and self.root and self.current and not self.skip:
            url = attrs.get("data-lazy-src") or attrs.get("data-src") or attrs.get("src", "")
            host = urlsplit(url).hostname if safe_https(url) else ""
            if (
                host
                and host.endswith(".pstatic.net")
                and host
                not in {
                    "ssl.pstatic.net",
                    "storep-phinf.pstatic.net",
                    "blogpfthumb-phinf.pstatic.net",
                }
                and not re.search(r"\.(?:svg|gif)(?:$|\?)", url, re.I)
            ):
                self.current["images"].append((url, attrs.get("alt", "")))

    def handle_data(self, data):
        if self.root and self.current and not self.skip:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "div":
            if self.current and self.depth == self.component:
                self.blocks.append(self.current)
                self.previous = (
                    " ".join(self.current["text"])[-160:] if not self.current["images"] else ""
                )
                self.current = None
                self.component = 0
            if self.depth == self.root:
                self.root = 0
            self.depth = max(0, self.depth - 1)


def extract_blog_images(html, place, review_title=""):
    parser = CaptionImages()
    parser.feed(html)
    aliases = image_aliases(place)
    focused_review = bool(
        review_title
        and title_matches(place, review_title, aliases)
        and not re.search(
            r"데이트\s*코스|코스\s*추천|카페\s*투어|맛집\s*모음|여러\s*곳|총\s*\d+곳", review_title
        )
    )
    branch = set(re.findall(r"[가-힣A-Za-z0-9]+점", place.get("name", "")))
    result = []
    seen = set()
    food = place.get("meal") or bool(
        re.search(r"카페|음식|미식|식당|베이커리", place.get("category", ""))
    )
    for block in parser.blocks:
        for url, alt in block["images"]:
            context = " ".join([alt, *block["text"], block["previous"]])
            caption_match = title_matches(place, context, aliases)
            facility_context = bool(
                re.search(
                    r"내부|외관|전경|시설|공간|매장|입구|정원|테라스|암벽|홀드|레인|코트|클라이밍|볼링|탁구|배드민턴|전시|메뉴|음식|디저트",
                    context,
                )
            )
            if not caption_match and not (focused_review and facility_context):
                continue
            own_context = " ".join([alt, *block["text"]])
            mentioned = set(re.findall(r"[가-힣A-Za-z0-9]+점", own_context)) - {
                "장점",
                "단점",
                "관점",
                "시점",
                "이점",
                "지점",
            }
            compact_name = re.sub(r"\s+", "", place.get("name", ""))
            if branch and any(
                not compact_name.endswith(word) and not any(word.endswith(b) for b in branch)
                for word in mentioned
            ):
                continue
            if re.search(r"다른\s*(?:가게|업체|지점|카페|식당)|다음\s*(?:장소|카페|식당)", context):
                continue
            if re.search(
                r"광고|배너|영수증|지도|길찾기|주차권|쿠폰|이벤트\s*안내|예약\s*화면|캡처|스크린샷|셀카|자료\s*사진|예시|참고용|인스타그램|Instagram|팔로워|체크인|이\s*장소의\s*다른\s*글",
                context,
            ):
                continue
            if not food and re.search(
                r"음식|메뉴|디저트|커피|파스타|삼겹살|점심|저녁밥|셀카|맛집", context
            ):
                continue
            if not re.search(
                r"내부|외관|전경|시설|공간|매장|암장|클라이밍|볼링|탁구|배드민턴|스케이트|골프|전시|산책|정원|공원|풍경|메뉴|음식|디저트",
                context,
            ):
                continue
            identity = photo_identity(url)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(
                dict(
                    url=url,
                    caption=(context.strip() or review_title)[:500],
                    match_basis="사진별 설명·업체명·지점명 대조"
                    if caption_match
                    else "업체·지점 일치 단독 후기와 사진 인접 시설 설명 대조",
                )
            )
            if len(result) == 5:
                return result
    return result


def read_post(post, place):
    try:
        parsed = urlsplit(post.get("url", ""))
    except ValueError:
        return []
    if parsed.scheme != "https" or parsed.netloc not in ("blog.naver.com", "m.blog.naver.com"):
        return []
    target = "https://m.blog.naver.com" + parsed.path + ("?" + parsed.query if parsed.query else "")
    try:
        with httpx.Client(timeout=4, follow_redirects=False) as client:
            with observed_stream(client, "GET", target) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    return []
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1500000:
                        return []
        return [
            dict(row, post=post)
            for row in extract_blog_images(
                data.decode("utf-8", errors="replace"), place, post.get("title", "")
            )
        ]
    except (httpx.HTTPError, ValueError, TypeError):
        return []


def photo_search_place(place):
    """Keep brand AND branch, without requiring generic business-type words."""
    if place.get("image_keywords"):
        return place
    parts = place.get("name", "").split()
    if len(parts) < 2 or not parts[-1].endswith("점"):
        return place
    branch = parts[-1][:-1]
    brand = "".join(
        word for word in parts[:-1] if word not in {"티하우스", "카페", "커피", "센터", "클럽"}
    )
    brand = re.sub(r"(?:티하우스|카페|센터|클럽)$", "", brand)
    if len(brand) < 2 or len(branch) < 2:
        return place
    return dict(place, image_keywords=[brand, branch])


def blog_photos(place, force=False):
    empty = dict(status="not_found", photos=[], photo_source="matched_blog_photos")
    if place.get("demo") or not search_enabled():
        return empty
    key = (
        "caption-blog-photos-v6:"
        + hashlib.sha256(
            json.dumps(
                [
                    place.get(k)
                    for k in ("id", "name", "address", "image_aliases", "image_keywords")
                ],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
    )
    if not force:
        cached = store.cached(key)
        if cached:
            return cached
    from .blog_search import place_blogs

    search_place = photo_search_place(place)
    posts = place_blogs(search_place)
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = context_map(
            pool, lambda post: read_post(post, search_place), posts.get("posts", [])[:3]
        )
    photos = []
    seen = set()
    for batch in batches:
        for row in batch:
            identity = photo_identity(row["url"])
            if identity in seen:
                continue
            seen.add(identity)
            post = row["post"]
            photos.append(
                dict(
                    id="blog-" + str(len(photos)),
                    kind="place_public",
                    provider="네이버 블로그",
                    source_type="blog_review",
                    source_label="블로그 후기 사진",
                    owner_verified=False,
                    title=place["name"] + " 후기 사진",
                    image_url=row["url"],
                    url=row["url"],
                    source=post["url"],
                    search_url=post["url"],
                    caption=row["caption"],
                    author=post.get("blogger"),
                    license=None,
                    license_url=None,
                    taken_at=None,
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    association=row.get("match_basis", "해당 장소 사진 설명 대조"),
                    image_role="장소 설명 연결 사진",
                )
            )
    result = dict(
        empty, status="available" if photos else posts.get("status", "not_found"), photos=photos[:5]
    )
    if not photos and result["status"] == "available":
        result["status"] = "not_found"
    store.cache(key, result, 3600 if photos else 60)
    return result
