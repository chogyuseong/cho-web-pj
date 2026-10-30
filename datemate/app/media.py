"""검수된 장소별 웹 사진을 원문·저작자·라이선스와 함께 제공한다."""

import json
import re
from urllib.parse import urlsplit, urlencode
from .search_address_text import place_query
from .config import ROOT
from .image_search import search_enabled


def validated_photo(photo):
    required = (
        "id",
        "url",
        "source",
        "title",
        "author",
        "license",
        "license_url",
        "checked_at",
        "association",
    )
    if not all(isinstance(photo.get(k), str) and photo[k].strip() for k in required):
        return False
    # 서버에서 임의 URL/사설망을 다운로드하지 않는다. 등록부는 운영자가 검수한다.
    image = urlsplit(photo["url"])
    source = urlsplit(photo["source"])
    license = urlsplit(photo["license_url"])
    return (
        image.scheme == "https"
        and image.netloc == "upload.wikimedia.org"
        and image.path.startswith("/wikipedia/commons/")
        and image.path.lower().endswith((".jpg", ".jpeg", ".png"))
        and not image.query
        and source.scheme == "https"
        and source.netloc == "commons.wikimedia.org"
        and license.scheme == "https"
        and license.netloc == "creativecommons.org"
        and bool(re.fullmatch(r"CC BY(?:-SA)? [1-4]\.0|CC0|Public domain", photo["license"]))
    )


def photos_for(place):
    if place.get("demo"):
        return []
    registry = ROOT / "data" / "place_photos.json"
    rows = (
        json.loads(registry.read_text(encoding="utf-8")).get(place["id"], [])
        if registry.exists()
        else []
    )
    # 검수되지 않은 장소 사진이나 가상 장소와 실제 사진을 섞지 않는다.
    result = []
    seen = set()
    for photo in rows:
        if not validated_photo(photo) or photo["url"] in seen:
            continue
        seen.add(photo["url"])
        result.append(photo)
        if len(result) == 5:
            break
    return result


def media_info(place, prefer_public=False, force=False, review_only=False):
    from .public_place_photos import public_place_photos
    from .blog_photos import blog_photos
    from .photo_relevance import filter_photos

    if review_only:
        data = blog_photos(place, force)
        checked = filter_photos(place, data["photos"])
        data = dict(data, photos=checked, status="available" if checked else "not_found")
        return dict(
            data,
            place_id=place["id"],
            wikidata_id=None,
            photo_source="matched_review_photos",
            description=place.get("description"),
            message="사진별 장소 설명과 사진 내용을 대조한 후기 사진이에요."
            if data["photos"]
            else "해당 장소와 사진 내용의 연결을 확인한 후기 사진이 없어요. 원문에서 확인해 주세요.",
            search_url="https://search.naver.com/search.naver?"
            + urlencode({"where": "blog", "query": place_query(place, "후기")}),
        )
    empty = dict(status="not_found", photos=[], photo_source="naver_public_place")
    public = (
        public_place_photos(place, force) if not place.get("demo") and search_enabled() else empty
    )
    public = dict(public, photos=filter_photos(place, public["photos"]))
    owner = [p for p in public["photos"] if p.get("owner_verified") is True]
    registered = photos_for(place)

    def response(data, photos, message):
        return dict(
            data,
            place_id=place["id"],
            photos=photos,
            wikidata_id=None,
            description=place.get("description"),
            status="available",
            message=message,
        )

    from .public_place_photos import photo_identity

    ordered = [*owner, *[dict(p, image_url=p["url"]) for p in registered], *public["photos"]]
    photos = []
    seen = set()

    def extend(rows):
        for photo in rows:
            url = photo.get("image_url") or photo.get("url")
            identity = photo_identity(url) if url else photo.get("id")
            if identity is None:
                identity = id(photo)
            if identity in seen:
                continue
            seen.add(identity)
            photos.append(photo)

    extend(ordered)
    searched = empty
    if len(photos) < 2 and not prefer_public:
        searched = blog_photos(place, force)
        searched = dict(searched, photos=filter_photos(place, searched["photos"]))
        extend(searched["photos"])
    if photos:
        only_registry = bool(registered) and not public["photos"] and not searched["photos"]
        result = response(
            public,
            photos[:5],
            "업체 사진을 먼저 표시하고, 부족한 사진은 같은 업체로 확인된 공개·후기 자료에서 보충해요.",
        )
        result["photo_source"] = "reviewed_registry" if only_registry else "priority_place_photos"
        result["wikidata_id"] = (
            place["id"] if only_registry and re.fullmatch(r"Q[1-9][0-9]*", place["id"]) else None
        )
        result["photo_lookup_incomplete"] = len(photos) < 2
        if len(photos) < 2:
            result["message"] = (
                "사진이 없는 것이 아니라 추가 사진을 자동으로 확보하지 못했어요. 업체 사진 원문에서 확인해 주세요."
            )
        return result
    return dict(
        place_id=place["id"],
        photos=[],
        wikidata_id=place["id"]
        if not place.get("demo") and re.fullmatch(r"Q[1-9][0-9]*", place["id"])
        else None,
        status="demo" if place.get("demo") else "not_found",
        photo_source="identity_checked_sources",
        search_status=searched["status"],
        description=place.get("description"),
        search_url="https://search.naver.com/search.naver?"
        + urlencode({"where": "image", "query": place_query(place)}),
        message="가상 장소이므로 실제 장소 사진을 제공하지 않습니다."
        if place.get("demo")
        else "업체 등록 사진이나 해당 장소가 설명에 명시된 후기 사진을 확보하지 못했어요. 관계를 확인할 수 없는 이미지는 표시하지 않아요.",
    )
