"""검수된 장소별 웹 사진을 원문·저작자·라이선스와 함께 제공한다."""

import json
import re
from urllib.parse import quote, urlsplit, urlencode
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


def unchecked(photos):
    """Photos shown with place matching only, without a content check."""
    return any(
        (photo.get("visual_verification") or {}).get("status") == "unverified" for photo in photos
    )


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
            message=(
                "사진별 장소 설명으로 해당 장소를 확인한 후기 사진이에요. 사진 내용 검사는 하지 않았어요."
                if unchecked(data["photos"])
                else "사진별 장소 설명과 사진 내용을 대조한 후기 사진이에요."
            )
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
    # 2026-11-19: 네이버 화면(업체 사진·블로그 본문)을 자동으로 읽지 않으므로(app/naver_pages.py) 부족한 사진은
    # 한국관광공사 TourAPI 의 같은 장소 사진(좌표 400m 안 + 이름 같음 + 하나뿐, 공공누리 제1·제3유형만, app/tour_places.py)으로 채운다.
    # 2026-11-20: 네이버 이미지 검색 결과에서 사진을 골라 쓰지 않는다(특약 2.2 — 검색 결과를 거르거나 다시 줄 세우지 않음,
    # docs/naver-terms-stage2-design.ko.md 3.4(c)). 등록·관광공사 사진이 없는 가게는 사진 칸에 네이버 지도 링크만 나온다.
    # 2026-11-20: 대표 사진이 없는 관광공사 항목은 detailImage2 의 공공누리 제1·제3유형 사진을 쓰고, 이름 맞추기를 넓혔다(app/tour_places.py).
    official = dict(status="not_found", photos=[])
    if len(photos) < 2 and not place.get("demo"):
        from .tour_places import tour_photo_result

        official = tour_photo_result(place, force)
        extend(official["photos"])
    # '사진 다시 불러오기'는 다시 시도할 뜻이 있을 때만(관광공사 호출 실패) 보인다. 자료에 사진이 없다고 확정되면(없음·키 없음·하루 상한) 숨긴다.
    retry_useful = official.get("status") == "unavailable"
    searched = empty
    if len(photos) < 2 and not prefer_public:
        searched = blog_photos(place, force)
        searched = dict(searched, photos=filter_photos(place, searched["photos"]))
        extend(searched["photos"])
    map_url = "https://map.naver.com/p/search/" + quote(place_query(place))
    if photos:
        only_registry = (
            bool(registered)
            and not public["photos"]
            and not searched["photos"]
            and not official["photos"]
        )
        result = response(
            public,
            photos[:5],
            "등록된 사진을 먼저 표시하고, 부족한 사진은 한국관광공사가 같은 장소로 등록한 사진에서 보충해요."
            + (
                " '내용 미검사' 사진은 장소 일치만 확인했고 사진 내용은 검사하지 않았어요."
                if unchecked(photos[:5])
                else ""
            ),
        )
        result["map_url"] = map_url
        result["photo_source"] = "reviewed_registry" if only_registry else "priority_place_photos"
        # 위키데이터 장소(Q 번호)는 사진이 2장보다 적으면 화면이 Wikidata 대표 사진(P18)을 덧붙여 찾는다(static/wikimedia-photos.js).
        # 2026-11-24: 예전에는 등록 사진만 있을 때만 넘겨, 관광공사 사진이 1장 있으면 위키데이터 사진을 찾지 않았다(사용자 신고 '사진을 못 가져온다').
        result["wikidata_id"] = (
            place["id"]
            if (only_registry or len(photos) < 2) and re.fullmatch(r"Q[1-9][0-9]*", place["id"])
            else None
        )
        result["photo_lookup_incomplete"] = len(photos) < 2
        result["photo_retry"] = False
        if len(photos) < 2:
            result["message"] = (
                "사진이 없는 것이 아니라 추가 사진을 자동으로 확보하지 못했어요. 네이버 지도에서 확인해 주세요."
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
        photo_retry=retry_useful,
        description=place.get("description"),
        search_url="https://search.naver.com/search.naver?"
        + urlencode({"where": "image", "query": place_query(place)}),
        # 사진이 끝내 없으면 화면은 빈칸 대신 이 네이버 지도 링크를 보여 준다(static/place-photos.js).
        map_url=None if place.get("demo") else map_url,
        message="가상 장소이므로 실제 장소 사진을 제공하지 않습니다."
        if place.get("demo")
        else "한국관광공사 사진 자료에 지금 연결하지 못했어요. 잠시 뒤 다시 불러오거나 네이버 지도에서 사진을 확인해 주세요."
        if retry_useful
        # 하루 호출 상한(app/public_places._reserve)에 걸려 관광공사 추가 사진을 묻지 못했다. '없는 곳'이라고 하지 않는다.
        else "오늘은 한국관광공사 사진을 더 확인하지 못했어요. 네이버 지도에서 사진을 확인해 주세요."
        if official.get("status") == "limited"
        # 검색 사진을 없앤 까닭을 한 줄로 알 수 있게 적는다(2026-11-20).
        else "등록 사진이나 한국관광공사 사진이 없는 곳이에요. 네이버 검색 결과에서 사진을 골라 쓰지 않아요. "
        "네이버 지도에서 사진을 확인해 주세요.",
    )
