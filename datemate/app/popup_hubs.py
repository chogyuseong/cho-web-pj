"""팝업 거점 사전 v2 (2026-11-20, 네이버 검색 API 특약 2단계).

팝업스토어가 자주 열리는 건물·동네를 데이트메이트가 정해 둔 목록이다. 코스 지도의 '팝업' 표시와
'이 장소 주변 코스 추천받기'가 이 목록만으로 그려진다(app/popup_api.py 의 hubs, static/popups.js·maps.js).
검색된 글과는 잇지 않는다: 어느 글이 어느 거점 이야기인지 읽지 않고, 글 수·기간을 거점에 붙이지 않는다
(docs/naver-terms-stage2-design.ko.md 3.3, 결정 Q3). 지금 그곳에서 팝업이 열리는지는 이 목록으로 알 수 없다.

좌표는 네이버 지역 검색 결과를 쓰지 않는다. 한국관광공사 TourAPI(KorService2 searchKeyword2, 이용허락범위 제한 없음)를
2026-11-20 에 이름으로 조회해 얻은 값을 고정해 둔다(요청 때 외부 호출 없음). 받아들인 기준은 둘 중 하나다.
- entity: 제목이 거점(또는 동네 기준 장소) 이름 그대로인 항목의 좌표. source 는 그 항목의 contentid.
- tenants: 제목이 '… {거점 이름}(점)'인 입점 매장 4곳 이상이 같은 도로명 주소·같은 좌표로 등록돼 있고,
  그 주소의 시·군·구가 거점의 시·군·구와 같을 때 그 좌표. source 는 그 도로명 주소.
둘 다 안 되는 거점은 lat·lon 을 None 으로 두고 지도에 그리지 않는다(추측 좌표를 넣지 않는다). v2 는 35곳 모두 확인됐다.
좌표를 다시 확인하면 CHECKED 와 HUBS_VERSION 을 함께 올린다.

v1(hubs-v1.1-2026-11-14)에서 바뀐 것
- 글에서 거점을 찾던 별칭(aliases·not_followed_by)과 지역 검색어(local_query·verify)를 지웠다.
- 동네 거점의 기준 장소를 지하철역에서 관광공사에 등록된 거리·시설로 바꿨다(역은 관광공사 자료에 없음):
  성수역 → 성수동 카페거리, 한강진역 → 블루스퀘어, 압구정로데오역 → 압구정 로데오거리, 홍대입구역 → 홍대걷고싶은거리,
  전포역 → 전포카페거리, 중앙로역 → 동성로거리. 도산공원은 그대로.
- '현대백화점 부산점'은 관광공사 자료에 '커넥트현대'(부산 동구 범일로 125)로 등록돼 있어 이름을 '커넥트현대 부산'으로 바꿨다.

필드: id(안정적인 ID), name(표시 이름), region / district(시·도와 시·군·구), kind('building' 건물 / 'area' 동네),
anchor(동네일 때 좌표의 기준 장소 이름, 건물은 None), lat / lon(WGS84), source(좌표 근거: basis, ref).
"""

HUBS_VERSION = "hubs-v2-2026-11-20"
COORDINATE_PROVIDER = "한국관광공사 TourAPI"
CHECKED = "2026-11-20"


def _hub(id, name, region, district, kind, lat, lon, basis, ref, anchor=None):
    return dict(
        id=id,
        name=name,
        region=region,
        district=district,
        kind=kind,
        anchor=anchor,
        lat=lat,
        lon=lon,
        source=dict(provider=COORDINATE_PROVIDER, basis=basis, ref=ref, checked=CHECKED),
    )


def _building(id, name, region, district, lat, lon, basis, ref):
    return _hub(id, name, region, district, "building", lat, lon, basis, ref)


def _area(id, name, region, district, anchor, lat, lon, ref):
    return _hub(id, name, region, district, "area", lat, lon, "entity", ref, anchor=anchor)


# fmt: off
HUBS = (
    # 서울 · 건물
    _building("seoul-thehyundai", "더현대 서울", "서울", "영등포구", 37.527097, 126.927301, "entity", "contentid 2708109"),
    _building("seoul-ipark-mall", "용산 아이파크몰", "서울", "용산구", 37.529772, 126.964742, "tenants", "서울특별시 용산구 한강대로23길 55"),
    _building("seoul-akplaza-hongdae", "AK플라자 홍대", "서울", "마포구", 37.557746, 126.926498, "tenants", "서울특별시 마포구 양화로 188"),
    _building("seoul-lotteworld-mall", "롯데월드몰", "서울", "송파구", 37.513713, 127.104302, "tenants", "서울특별시 송파구 올림픽로 300"),
    _building("seoul-lotte-jamsil", "롯데백화점 잠실점", "서울", "송파구", 37.511310, 127.098142, "tenants", "서울특별시 송파구 올림픽로 240"),
    _building("seoul-shinsegae-gangnam", "신세계백화점 강남점", "서울", "서초구", 37.503935, 127.002413, "tenants", "서울특별시 서초구 신반포로 176"),
    _building("seoul-hyundai-apgujeong", "현대백화점 압구정본점", "서울", "강남구", 37.527366, 127.027469, "tenants", "서울특별시 강남구 압구정로 165"),
    _building("seoul-galleria", "갤러리아 명품관", "서울", "강남구", 37.528475, 127.040053, "entity", "contentid 273772"),
    _building("seoul-coex-mall", "스타필드 코엑스몰", "서울", "강남구", 37.511824, 127.059159, "tenants", "서울특별시 강남구 영동대로 513"),
    _building("seoul-lotte-main", "롯데백화점 본점", "서울", "중구", 37.564730, 126.981730, "tenants", "서울특별시 중구 남대문로 81"),
    _building("seoul-shinsegae-main", "신세계백화점 본점", "서울", "중구", 37.560919, 126.980979, "tenants", "서울특별시 중구 소공로 63"),
    _building("seoul-ifc-mall", "IFC몰", "서울", "영등포구", 37.525178, 126.924877, "tenants", "서울특별시 영등포구 국제금융로 10"),
    _building("seoul-times-square", "타임스퀘어(영등포)", "서울", "영등포구", 37.517233, 126.903716, "tenants", "서울특별시 영등포구 영중로 15"),
    _building("seoul-lotte-cheongnyangni", "롯데백화점 청량리점", "서울", "동대문구", 37.584197, 127.051145, "entity", "contentid 2911584"),
    # 서울 · 동네(좌표는 기준 장소의 것이라 대략이다)
    _area("seoul-area-seongsu", "성수 일대", "서울", "성동구", "성수동 카페거리", 37.543198, 127.056598, "contentid 2930901"),
    _area("seoul-area-hannam", "한남 일대", "서울", "용산구", "블루스퀘어", 37.540872, 127.002487, "contentid 1439094"),
    _area("seoul-area-dosan", "도산 일대", "서울", "강남구", "도산공원", 37.524500, 127.035400, "contentid 126486"),
    _area("seoul-area-apgujeong-rodeo", "압구정로데오 일대", "서울", "강남구", "압구정 로데오거리", 37.526822, 127.038881, "contentid 126823"),
    _area("seoul-area-hongdae", "홍대 일대", "서울", "마포구", "홍대걷고싶은거리", 37.555999, 126.924307, "contentid 3082405"),
    # 부산
    _building("busan-shinsegae-centum", "신세계 센텀시티", "부산", "해운대구", 35.168818, 129.129523, "tenants", "부산광역시 해운대구 센텀남대로 35"),
    _building("busan-lotte-centum", "롯데백화점 센텀시티점", "부산", "해운대구", 35.169853, 129.131070, "entity", "contentid 2917200"),
    _building("busan-lotte-main", "롯데백화점 부산본점", "부산", "부산진구", 35.156790, 129.056416, "tenants", "부산광역시 부산진구 가야대로 772"),
    _building("busan-lotte-gwangbok", "롯데백화점 광복점", "부산", "중구", 35.097985, 129.036632, "tenants", "부산광역시 중구 중앙대로 2"),
    _building("busan-lotte-dongnae", "롯데백화점 동래점", "부산", "동래구", 35.211708, 129.077480, "entity", "contentid 2917189"),
    _building("busan-hyundai", "커넥트현대 부산", "부산", "동구", 35.141302, 129.058574, "entity", "contentid 3452166"),
    _building("busan-f1963", "F1963", "부산", "수영구", 35.176745, 129.115485, "entity", "contentid 2456767"),
    _building("busan-samjeong-tower", "서면 삼정타워", "부산", "부산진구", 35.153006, 129.059606, "entity", "contentid 3014436"),
    _area("busan-area-jeonpo", "전포 일대", "부산", "부산진구", "전포카페거리", 35.155420, 129.067338, "contentid 1805965"),
    # 대구
    _building("daegu-thehyundai", "더현대 대구", "대구", "중구", 35.866628, 128.590629, "entity", "contentid 3344379"),
    _building("daegu-shinsegae", "대구신세계", "대구", "동구", 35.877941, 128.629190, "tenants", "대구광역시 동구 동부로 149"),
    _building("daegu-lotte", "롯데백화점 대구점", "대구", "북구", 35.875885, 128.596129, "entity", "contentid 2908603"),
    _area("daegu-area-dongseongro", "동성로 일대", "대구", "중구", "동성로거리", 35.870170, 128.594059, "contentid 2599899"),
    # 대전
    _building("daejeon-shinsegae", "대전신세계 Art & Science", "대전", "유성구", 36.375182, 127.381765, "tenants", "대전광역시 유성구 엑스포로 1"),
    _building("daejeon-galleria-timeworld", "갤러리아 타임월드", "대전", "서구", 36.351954, 127.378167, "tenants", "대전광역시 서구 대덕대로 211"),
    # 전북
    _building("jeonbuk-lotte-jeonju", "롯데백화점 전주점", "전북", "전주시", 35.834459, 127.121908, "entity", "contentid 2908845"),
)
# fmt: on
# 그 밖의 시·도는 거점이 없다(팝업이 자주 열리는 곳을 미리 정할 근거가 없음). 그 지역에서는 지도에 팝업 표시가 없다.


def hubs_in(region):
    """그 시·도의 거점 중 좌표가 있는 것(사전 순서 그대로). 화면·지도가 쓰는 필드만 싣는다."""
    return [
        dict(
            hub_id=h["id"],
            name=h["name"],
            kind=h["kind"],
            anchor=h["anchor"],
            region=h["region"],
            district=h["district"],
            lat=h["lat"],
            lon=h["lon"],
        )
        for h in HUBS
        if h["region"] == region and h["lat"] is not None and h["lon"] is not None
    ]
