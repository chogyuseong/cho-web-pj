"""네이버 '페이지' 자동 조회 차단 스위치(2026-11-19 사용자 결정).

무엇을 막나: 공식 Open API 가 아닌 네이버 화면 주소를 서버가 자동으로 읽는 일 전부.
  · search.naver.com 검색 결과 HTML(메뉴 가격 app/menus.py, 업체 사진·업체 번호 app/public_place_photos.py)
  · m.place.naver.com 업체 사진 페이지(app/public_place_photos.py owner_page_photos)
  · m.blog.naver.com 글 본문(블로그 사진 app/blog_photos.py read_post,
    후기 요약 app/review_facts.py — public_body 를 씀)

왜: 네이버 서비스 이용약관(2026-10-01 시행)이 '사전 허락 없이 자동화된 수단(로봇·스크래퍼 등)으로 … 게시물 등을 수집하거나,
  네이버 검색 서비스에서 특정 질의어로 검색하는' 것을 금지하고, search.naver.com·map.naver.com 의 robots.txt 는
  모든 로봇을 막는다(User-agent: * / Disallow: /). '검색결과 수집에 대한 정책'은 robots.txt 로 보호된 자료를
  다른 로봇이 수집하는 것을 불허하며 저작권법·정보통신망법 위반 가능성을 적는다. 2026-11-19 확인, 원문은
  docs/naver-terms-review-2026-11-19.ko.md.

막지 않는 것: 공식 Open API(naverapihub.apigw.ntruss.com 의 지역·블로그 검색, 지도 Directions 등).
  API 결과의 제목·요약문은 API 약관에 따라 쓴다.

대신 쓰는 것: 사진 = 등록 사진 + 한국관광공사 사진(app/media.py, 네이버 이미지 검색은 쓰지 않음), 메뉴 가격 = 네이버 지도 링크만(가격을 읽어 오지 않음,
  app/menus.py), 블로그 글 = API 결과를 받은 그대로 보여 주기만(app/blog_search.py), 같은 업체 확인 = 공공 자료(소상공인 상가정보·행안부 인허가, app/place_identity.py).

되돌리려면: 네이버의 서면 허락(제휴)을 받은 경우에만 ALLOWED 를 True 로 바꾼다. 허락 없이 바꾸지 않는다.
"""

ALLOWED = False


def allowed():
    """네이버 화면(검색 결과·플레이스·블로그 본문)을 자동으로 읽어도 되는가. 지금은 늘 False."""
    return ALLOWED
