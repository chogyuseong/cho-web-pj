"""서울시 착한가격업소 메뉴·가격(app/good_price.py): 응답 읽기, 같은 가게 판정, 보관·실패·키 없음, 메뉴 칸 표시. 외부 호출은 모두 가짜.

행 모양은 2026-11-26 실제 키로 받은 응답(ListPriceModelStoreProductService)과 같다(가게 이름·주소는 시험용으로 바꿨다)."""
import re

import httpx
import pytest

from app import good_price, menus, store
from test_functional_audit import audit_page  # noqa: F401  (fixture)


def row(shop_id="00010419", name="포아잉트", address="서울특별시 서울 송파구 오금로 485. 1층", code="004", item="소고기쌀국수", price=9000.0):
    return {"SH_ID": shop_id, "SH_NAME": name, "INDUTY_CODE_SE": code, "INDUTY_CODE_SE_NAME": "기타외식업", "SH_ADDR": address,
            "SH_PHONE": "02-000-0000", "SH_RCMN": 0.0, "IM_NAME": item, "IM_PRICE": price}


def body(rows, total=None, code="INFO-000"):
    return {"ListPriceModelStoreProductService": {"list_total_count": len(rows) if total is None else total,
                                                  "RESULT": {"CODE": code, "MESSAGE": "정상 처리되었습니다"}, "row": rows}}


ROWS = [
    row(item="소고기쌀국수", price=9000.0),
    row(item="양지쌀국수", price=9000.0),
    row(item="양지쌀국수", price=9000.0),  # 같은 품목·가격이 두 번 — 한 번만
    row(item="", price=0.0),  # 이름·가격 없는 품목 — 버림
    row(item="반값", price=4500.5),  # 원 단위가 아닌 값 — 버림
    row(shop_id="2", name="하이얀미용실", code="005", item="커트", price=6000.0),  # 미용 업종 — 쓰지 않음
    row(shop_id="3", name="중계분식", address="서울특별시 서울 노원구 중계동 154-41", item="김밥", price=3000.0),  # 지번 주소 — 쓰지 않음
    row(shop_id="4", name="테스트", address="서울특별시 테스트", item="", price=0.0),
]

PLACE = dict(id="store-1", name="포아잉트", address="서울특별시 송파구 오금로 485", lat=37.5, lon=127.1, meal=True, category="카페·미식")


def test_parse_and_build_keep_food_shops_with_road_addresses():
    rows, total = good_price.parse_page(body(ROWS))
    assert total == len(ROWS) and len(rows) == len(ROWS)
    index = good_price.build(rows)
    assert list(index) == ["오금로|485"]
    shop = index["오금로|485"][0]
    assert shop["district"] == "송파구" and shop["name"] == "포아잉트"
    assert shop["items"] == [dict(name="소고기쌀국수", amount=9000), dict(name="양지쌀국수", amount=9000)]
    for broken in ({}, {"ListPriceModelStoreProductService": {"RESULT": {"CODE": "INFO-000"}}}, body([], code="ERROR-500"), body(ROWS, total="x")):
        with pytest.raises(ValueError):
            good_price.parse_page(broken)


def test_district_reads_mixed_address_forms():
    assert good_price.district("서울특별시 서울 송파구 오금로 485. 1층") == "송파구"
    assert good_price.district("서울 중구 명동10길 29") == "중구"
    assert good_price.district("서울특별시 (논현동)언주로125길 5 B01층") is None


def shops(*rows):
    return good_price.build(list(rows)).get("오금로|485", [])


def test_match_needs_same_name_and_same_road_address():
    assert good_price.match(PLACE, shops(*ROWS))["name"] == "포아잉트"
    # 지점 낱말이 붙은 우리 이름(상가정보 '이름 지점')도 같은 가게로 본다. 띄어쓰기·기호는 무시.
    assert good_price.match(dict(PLACE, name="포아 잉트 송파점"), shops(*ROWS))
    # 이름만 같다 — 주소(건물번호)가 다르면 붙이지 않는다.
    assert good_price.match(dict(PLACE, address="서울특별시 송파구 오금로 485-1"), shops(*ROWS)) is None
    assert good_price.match(dict(PLACE, address="서울특별시 송파구 오금로 48"), shops(*ROWS)) is None
    # 주소만 같다 — 이름이 다르거나 한쪽이 다른 쪽을 품기만 하면 붙이지 않는다.
    assert good_price.match(dict(PLACE, name="오금국수"), shops(*ROWS)) is None
    assert good_price.match(dict(PLACE, name="포아잉트커피"), shops(*ROWS)) is None
    assert good_price.match(dict(PLACE, name="포아"), shops(*ROWS)) is None
    # 같은 도로명·번호라도 자치구가 다르면, 우리 주소에 자치구가 없으면 붙이지 않는다.
    assert good_price.match(dict(PLACE, address="서울특별시 강동구 오금로 485"), shops(*ROWS)) is None
    assert good_price.match(dict(PLACE, address="오금로 485"), shops(*ROWS)) is None
    # 같은 주소·이름의 가게가 둘이면 어느 가격인지 몰라 붙이지 않는다.
    twin = row(shop_id="9", item="커피", price=2000.0)
    assert good_price.match(PLACE, shops(*ROWS, twin)) is None


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("SEOUL_OPEN_API_KEY", "test-key")
    filler = [row(shop_id=f"f{i}", name=f"가게{i}", address=f"서울특별시 마포구 독막로 {i}", item="백반", price=8000.0) for i in range(1, 2001)]
    state = dict(calls=[], rows=ROWS + filler, fail=None)

    def get(self, url, **kwargs):
        state["calls"].append(url)
        if state["fail"]:
            raise state["fail"]
        start, end = map(int, re.search(r"/(\d+)/(\d+)/$", url).groups())
        return httpx.Response(200, json=body(state["rows"][start - 1:end], total=len(state["rows"])), request=httpx.Request("GET", "http://x"))

    monkeypatch.setattr(httpx.Client, "get", get)
    return state


def test_refresh_pages_through_everything_and_requests_only_read(fake):
    assert good_price.refresh() is True
    # 2,008줄 → 1,000줄씩 세 번. 주소에 키가 들어가는 서울 API 규칙.
    assert [re.search(r"/(\d+/\d+)/$", u)[1] for u in fake["calls"]] == ["1/1000", "1001/2000", "2001/3000"]
    assert fake["calls"][0].startswith("http://openapi.seoul.go.kr:8088/test-key/json/ListPriceModelStoreProductService/")
    calls = len(fake["calls"])
    menu = good_price.good_price_menu(PLACE)
    assert menu["items"] == [dict(name="소고기쌀국수", amount=9000), dict(name="양지쌀국수", amount=9000)]
    assert menu["source_label"] == "착한가격업소 · 서울시 제공" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", menu["fetched_on"])
    assert good_price.good_price_menu(dict(PLACE, name="다른식당")) is None
    assert len(fake["calls"]) == calls, "메뉴 요청은 서울 API 를 부르지 않는다"


def test_failure_keeps_the_last_copy_and_waits(fake, monkeypatch):
    assert good_price.refresh()
    first = store.cached(good_price.META_KEY)
    fake["fail"] = httpx.ConnectTimeout("blocked")
    assert good_price.refresh() is False
    assert store.cached(good_price.META_KEY) == first and store.cached(good_price.RETRY_KEY)
    assert good_price.good_price_menu(PLACE)["items"], "실패해도 지난 보관분은 그대로 쓴다"
    # 모양이 이상한 응답·빈 자료도 실패로 본다(보관분을 덮지 않는다).
    fake["fail"] = None
    fake["rows"] = []
    assert good_price.refresh() is False and store.cached(good_price.META_KEY) == first


def test_missing_key_or_data_gives_nothing(fake, monkeypatch):
    started = []
    monkeypatch.setattr(good_price, "_start_refresh", lambda: started.append(1))
    # 보관분이 없으면 배경 받기만 맡기고 지금은 착한가격 없이 답한다.
    assert good_price.good_price_menu(PLACE) is None and started == [1] and fake["calls"] == []
    monkeypatch.delenv("SEOUL_OPEN_API_KEY")
    assert good_price.good_price_menu(PLACE) is None and good_price.refresh() is False and started == [1]
    assert not good_price.enabled()


def test_stale_copy_is_used_while_a_new_one_is_fetched(fake, monkeypatch):
    assert good_price.refresh()
    meta = store.cached(good_price.META_KEY)
    store.cache(good_price.META_KEY, dict(meta, fetched_at="2026-01-01T00:00:00+00:00"), 3600)
    started = []
    monkeypatch.setattr(good_price, "_start_refresh", lambda: started.append(1))
    assert good_price.good_price_menu(PLACE)["items"] and started == [1]


def test_only_real_seoul_places(fake):
    assert good_price.refresh()
    assert good_price.good_price_menu(dict(PLACE, address="경기도 성남시 분당구 오금로 485")) is None
    assert good_price.good_price_menu(dict(PLACE, demo=True)) is None
    assert good_price.good_price_menu(dict(PLACE, naver_result=True)) is None
    assert good_price.good_price_menu(PLACE)["items"]


def test_menu_panel_data_prefers_good_price(fake):
    assert good_price.refresh()
    data = menus.restaurant_menu(PLACE)
    assert data["status"] == "available" and data["source_kind"] == "seoul_good_price" and data["reason"] == "good_price"
    assert [(i["name"], i["display_price"], i["amount"]) for i in data["items"]] == [("소고기쌀국수", "9,000원", 9000), ("양지쌀국수", "9,000원", 9000)]
    assert data["source_url"] == good_price.SOURCE_URL and data["search_url"].startswith("https://map.naver.com/p/search/")
    # 식당 넣기의 비용 기준 메뉴로도 고를 수 있다(가격 종류는 good_price_menu).
    assert [i["name"] for i in menus.cost_menu_options(data)] == ["소고기쌀국수", "양지쌀국수"]
    other = menus.restaurant_menu(dict(PLACE, id="store-2", name="오금국수"))
    assert other["source_kind"] == "map_link" and other["reason"] == "not_collected"


GOOD = {"status": "available", "source_kind": "seoul_good_price", "reason": "good_price", "menu_images": [],
        "items": [{"name": n, "amount": a, "display_price": f"{a:,}원", "price_scope": "store", "representative": False}
                  for n, a in [("소고기쌀국수", 9000), ("양지쌀국수", 9000), ("아주아주긴이름의특제한우차돌된장찌개정식세트", 12000),
                               ("김밥", 3500), ("라면", 4000), ("만두", 5000), ("공기밥", 1000)]],
        "source_url": "https://data.seoul.go.kr/dataList/OA-1174/S/1/datasetView.do", "source_label": "착한가격업소 · 서울시 제공",
        "good_price": {"fetched_on": "2026-11-26"}, "search_url": "https://map.naver.com/p/search/x",
        "note": "서울시가 공개한 착한가격업소 가격이에요. 지금 매장 가격과 다를 수 있어요."}


@pytest.mark.parametrize("width", [375, 320])
def test_menu_panel_shows_prices_and_source(audit_page, width):  # noqa: F811
    page, _, _ = audit_page
    page.set_viewport_size({"width": width, "height": 800})
    page.route("**/api/places/g1/menu?*", lambda route: route.fulfill(json=GOOD))
    got = page.evaluate("""async ()=>{
      restaurantMenuRequests.delete('g1');
      const card=node('article',undefined,'meal-card');const box=restaurantMenuPanel({id:'g1',name:'포아잉트'});card.append(box);
      document.body.replaceChildren(card);box.scrollIntoView();
      const t=Date.now();while(!box.querySelector('.good-price-source')&&Date.now()-t<5000)await new Promise(r=>setTimeout(r,50));
      return {text:box.textContent,rows:[...box.querySelectorAll('.menu-price-row')].map(r=>r.textContent),
        links:[...box.querySelectorAll('a')].map(a=>a.textContent),buttons:box.querySelectorAll('button').length,
        overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
        wider:[...box.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>innerWidth+0.5).length};
    }""")
    assert got["text"].startswith("메뉴·가격")
    assert got["rows"][:2] == ["소고기쌀국수9,000원", "양지쌀국수9,000원"] and len(got["rows"]) == 6
    assert "외 1개 메뉴" in got["text"]
    assert "착한가격업소 · 서울시 제공 · 2026-11-26 확인" in got["text"]
    assert "가격은 네이버 지도 메뉴 탭에서" not in got["text"] and "모아 두지 않았어요" not in got["text"]
    assert got["links"] == ["출처 ↗", "네이버 지도에서 메뉴보기 ↗"] and got["buttons"] == 0
    assert got["overflow"] <= 0 and got["wider"] == 0
