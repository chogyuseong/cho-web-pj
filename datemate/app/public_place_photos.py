"""Photos explicitly attached to the uniquely matched public business record."""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode, parse_qs, unquote
import httpx
from . import store
from .menus import states, dictionaries, identified, resolve, fetch_page, _limit
from .image_search import safe_https
from .search_address_text import place_query
from .telemetry import observed_stream


def image_urls(node, state):
    node = resolve(node, state)
    if isinstance(node, list):
        for item in node:
            yield from image_urls(item, state)
    elif isinstance(node, dict):
        for key in (
            "origin",
            "originalUrl",
            "original",
            "imageUrl",
            "url",
            "thumbUrl",
            "thumbnailUrl",
            "thumUrl",
        ):
            value = node.get(key)
            if (
                isinstance(value, str)
                and safe_https(value)
                and (urlsplit(value).hostname or "").endswith(".pstatic.net")
            ):
                yield value
        for key in ("images", "image", "items"):
            value = node.get(key)
            if isinstance(value, (dict, list)):
                yield from image_urls(value, state)


def photo_identity(url):
    """Resized versions of the same original are one photograph."""
    parsed = urlsplit(url)
    if parsed.hostname == "search.pstatic.net":
        original = parse_qs(parsed.query).get("src", [""])[0]
        if safe_https(original):
            parsed = urlsplit(unquote(original))
    return (parsed.hostname or "").lower() + parsed.path


def extract_photo_records(html, place):
    """Only explicit owner metadata qualifies; a CDN host alone proves no uploader."""
    owner_keys = {
        "ownerPhotos",
        "ownerImages",
        "businessPhotos",
        "businessImages",
        "bizPhotos",
        "bizImages",
    }
    review_keys = {"visitorReviewPhotos", "reviewPhotos", "reviewImages", "visitorImages"}

    def collect(node, state, owner=False, review=False, depth=0):
        if depth > 12:
            return
        node = resolve(node, state)
        if isinstance(node, list):
            for item in node:
                yield from collect(item, state, owner, review, depth + 1)
        elif isinstance(node, dict):
            marker = str(
                node.get("uploaderType") or node.get("providerType") or node.get("authorType") or ""
            ).upper()
            owner = (
                owner or node.get("isOwner") is True or marker in {"OWNER", "BUSINESS", "MERCHANT"}
            )
            review = review or marker in {"VISITOR", "REVIEWER", "BLOG"}
            for key in (
                "origin",
                "originalUrl",
                "original",
                "imageUrl",
                "url",
                "thumbUrl",
                "thumbnailUrl",
                "thumUrl",
            ):
                url = node.get(key)
                if (
                    isinstance(url, str)
                    and safe_https(url)
                    and (urlsplit(url).hostname or "").endswith(".pstatic.net")
                ):
                    yield dict(url=url, owner_verified=owner, review_verified=review)
                    break
            for key in (
                "images",
                "image",
                "items",
                "photos",
                "photoList",
                *sorted(owner_keys),
                *sorted(review_keys),
            ):
                if isinstance(node.get(key), (dict, list)):
                    yield from collect(
                        node[key],
                        state,
                        owner or key in owner_keys,
                        review or key in review_keys,
                        depth + 1,
                    )

    matched_pid = None
    for state in states(html):
        bases = [
            (key, base)
            for key, base in state.items()
            if isinstance(base, dict)
            and base.get("__typename") == "PlaceDetailBase"
            and identified(base, place)
        ]
        records = []
        pid = None
        if len(bases) == 1:
            key, base = bases[0]
            pid = str(base["id"])
            for scope in dictionaries(state):
                if scope.get("base") != {"__ref": key}:
                    continue
                for field in ("images", "topPhotos", *sorted(owner_keys), *sorted(review_keys)):
                    records.extend(
                        collect(scope.get(field), state, field in owner_keys, field in review_keys)
                    )
        elif len(bases) > 1:
            return [], None
        if not records:
            rows = {
                str(base["id"]): base
                for base in dictionaries(state)
                if base.get("__typename") == "PlaceListBusinessesItem"
                and identified(base, place, listing=True)
            }
            if len(rows) == 1:
                pid, base = next(iter(rows.items()))
                records = list(collect(base, state))
        if pid:
            matched_pid = pid
            # Normalized image records may be separate from the base-containing scope.
            for node in dictionaries(state):
                linked = str(node.get("placeId") or node.get("businessId") or "")
                if linked == pid and any(
                    word in str(node.get("__typename", "")).lower() for word in ("photo", "image")
                ):
                    records.extend(collect(node, state))
        unique = {}
        for row in records:
            identity = photo_identity(row["url"])
            old = unique.get(identity)
            if old is None or row["owner_verified"]:
                unique[identity] = row
        if unique:
            return sorted(unique.values(), key=lambda row: not row["owner_verified"])[:5], pid
    return [], matched_pid


def extract_place_photos(html, place):
    records, pid = extract_photo_records(html, place)
    return [row["url"] for row in records], pid


def owner_page_photos(client, pid, place):
    """Try the public business tab once; access limits are respected, never bypassed."""
    if not str(pid or "").isdigit() or store.cached("owner-photo-page-cooldown"):
        return []
    try:
        with observed_stream(
            client,
            "GET",
            "https://m.place.naver.com/place/" + str(pid) + "/photo",
            params={"type": "business"},
        ) as response:
            response.raise_for_status()
            if response.status_code != 200:
                return []
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 4000000:
                    return []
        records, matched_pid = extract_photo_records(body.decode("utf-8", errors="replace"), place)
        if matched_pid != str(pid):
            return []
        return [row for row in records if row["owner_verified"]]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403, 429):
            try:
                delay = max(60, min(86400, int(exc.response.headers.get("Retry-After", "60"))))
            except ValueError:
                delay = 60
            store.cache("owner-photo-page-cooldown", True, delay)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        pass
    return []


def public_place_photos(place, force=False):
    if (
        not place.get("name")
        or place.get("lat") is None
        or place.get("lon") is None
        or place.get("demo")
    ):
        return dict(status="not_found", photos=[], photo_source="naver_public_place")
    fingerprint = hashlib.sha256(
        str([place["name"], place.get("address"), place.get("lat"), place.get("lon")]).encode()
    ).hexdigest()
    key = "public-place-photos-v7:" + fingerprint
    if not force:
        cached = store.cached(key)
        if cached:
            return cached
    result = dict(status="not_found", photos=[], photo_source="naver_public_place")
    if place.get("demo"):
        return result
    if store.cached("public-place-photo-cooldown"):
        return dict(result, status="unavailable")
    district = next(
        (word for word in (place.get("address") or "").split() if word.endswith("구")), "서울"
    )
    query = place_query(place)
    try:
        with _limit, httpx.Client(timeout=8, follow_redirects=False) as client:
            records = []
            pid = None
            # A representative photo alone is not a complete gallery.
            for search_query in dict.fromkeys(
                [query, place["name"] + " " + district, place_query(place, "사진")]
            ):
                try:
                    found, found_pid = extract_photo_records(
                        fetch_page(client, search_query), place
                    )
                except (httpx.HTTPError, ValueError, TypeError, KeyError):
                    if records:
                        break
                    raise
                if found_pid and (pid is None or pid == found_pid):
                    pid = found_pid
                    records.extend(found)
                    unique = {}
                    for row in sorted(records, key=lambda row: not row["owner_verified"]):
                        unique.setdefault(photo_identity(row["url"]), row)
                    records = list(unique.values())
                if len(records) >= 2:
                    break
            if pid and sum(row["owner_verified"] for row in records) < 2:
                owner = owner_page_photos(client, pid, place)
                unique = {}
                for row in [*owner, *records]:
                    unique.setdefault(photo_identity(row["url"]), row)
                records = list(unique.values())[:5]
        source = "https://map.naver.com/p/entry/place/" + pid if pid else None
        if pid:
            result.update(naver_place_id=pid, naver_place_id_verified=True)
        checked = datetime.now(timezone.utc).isoformat()
        for index, record in enumerate(records):
            url = record["url"]
            label = (
                "업체 등록 사진"
                if record["owner_verified"]
                else "방문자 후기 사진"
                if record["review_verified"]
                else "업체 연결 공개 사진 · 등록 주체 미확인"
            )
            result["photos"].append(
                dict(
                    id="public-" + str(index),
                    kind="place_public",
                    provider="네이버 공개 장소 사진",
                    title=place["name"] + " 장소 사진",
                    owner_verified=record["owner_verified"],
                    source_label=label,
                    source_type="business_upload"
                    if record["owner_verified"]
                    else "place_review"
                    if record["review_verified"]
                    else "place_public",
                    image_url=url,
                    url=url,
                    source=source,
                    search_url=source,
                    caption=label + " · 상호·주소 좌표로 연결한 해당 장소의 사진입니다.",
                    author=None,
                    license=None,
                    license_url=None,
                    taken_at=None,
                    checked_at=checked,
                    association="공개 장소 정보의 고유 업체·좌표 대조",
                    image_role="장소 연결 사진",
                )
            )
        if result["photos"]:
            result["status"] = "available"
    except httpx.HTTPStatusError as exc:
        result["status"] = "unavailable"
        if exc.response.status_code in (401, 403, 429):
            store.cache("public-place-photo-cooldown", True, 60)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        result["status"] = "unavailable"
    store.cache(key, result, 3600 if result["photos"] else 60)
    return result
