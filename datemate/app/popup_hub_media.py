"""팝업 거점 사진 (2026-11-24 사용자 요청: '팝업 글만 있어서 보기 안 좋다 — 사진 가져올 방법').

무엇: 팝업 '거점'(우리가 정해 둔 백화점·거리 사전, app/popup_hubs.py) 칸에 한국관광공사 사진 한 장을 붙인다.
- 검색된 팝업 글의 사진이 아니다. 글 페이지를 읽어 사진을 가져오거나(네이버 이용약관 '게시물 수집 금지') 이미지 검색 결과를
  골라 쓰는 것(검색 API 특약 1.2)은 하지 않는다(docs/naver-terms-review-2026-11-19.ko.md, 2026-11-20 결정 Q6).
  그래서 '지금 열리는 팝업 사진'이 아니라 '거점 사진'이라고 화면에 적는다(static/popups.js).
- 사진이 붙는 거점: 좌표를 관광공사 항목 자체로 확인한 거점(source.basis 'entity', ref 'contentid N')만. 입점 매장 주소로
  좌표를 잡은 거점(basis 'tenants')은 관광공사 항목 번호가 없어 사진을 붙이지 않는다(추측으로 다른 항목을 잇지 않는다).
- 사진 규칙은 장소 사진과 같다(app/tour_places.tour_photo_result): 공공누리 제1·제3유형, 관광공사 사진 호스트만, 출처·이용조건을 함께 보여 준다.
  7일 보관, 하루 호출 상한(app/public_places._reserve) 안에서만 부른다. 거점 칸마다 한 장만 준다.
- popup_api.py 와 따로 둔 까닭: 그 모듈은 '받은 글만, 사진 없음'을 테스트로 지킨다(tests/test_popup_api.py). 거점 사진은 글 블록 밖의 일이다.
"""

import re

from fastapi import APIRouter, HTTPException, Path

from .popup_api import NOT_FOUND, enabled
from .popup_hubs import HUBS

router = APIRouter()

_CONTENT_ID = re.compile(r"^contentid (\d+)$")


def hub_content_id(hub):
    """관광공사 항목으로 좌표를 확인한 거점이면 그 contentid, 아니면 None."""
    source = hub.get("source") or {}
    if source.get("basis") != "entity":
        return None
    match = _CONTENT_ID.match(str(source.get("ref") or ""))
    return match[1] if match else None


def hub_media(hub_id):
    hub = next((h for h in HUBS if h["id"] == hub_id), None)
    if hub is None:
        return None
    content_id = hub_content_id(hub)
    if not content_id:
        return dict(hub_id=hub_id, status="not_applicable", photos=[])
    from .tour_places import tour_photo_result

    # 관광공사 목록 항목처럼 넘겨 이름으로 다시 찾지 않게 한다(tour_info → _listed_info, 항목 번호로 사진만 받음).
    place = dict(
        id="popup-hub:" + hub_id,
        name=hub["name"],
        lat=hub["lat"],
        lon=hub["lon"],
        tour_content_id=content_id,
        source=f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={content_id}",
    )
    result = tour_photo_result(place)
    return dict(hub_id=hub_id, status=result["status"], photos=result["photos"][:1])


@router.get("/api/popups/hubs/{hub_id}/media")
def popup_hub_media(hub_id: str = Path(max_length=60, pattern=r"^[a-z0-9-]+$")):
    if not enabled():
        raise HTTPException(404, NOT_FOUND)
    found = hub_media(hub_id)
    if found is None:
        raise HTTPException(404, NOT_FOUND)
    return found
