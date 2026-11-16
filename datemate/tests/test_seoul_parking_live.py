"""서울시 공영주차장 실시간 주차 대수: 응답 읽기, 캐시, 실패, 주차장 칸에 붙이기. 외부 호출은 모두 가짜."""
import httpx
import pytest

from app import parking, public_parking, seoul_parking_live, store

# 2026-11-16 17:04 사용자가 휴대폰으로 받은 실제 응답에서 한 행(필요한 열만).
ROW = {"PKLT_CD": "171721", "PKLT_NM": "세종로 공영주차장(시)", "PRK_STTS_YN": "1", "TPKCT": 1260.0,
       "NOW_PRK_VHCL_CNT": 713.0, "NOW_PRK_VHCL_UPDT_TM": "2026-11-16 17:04:43"}


def body(*rows):
    return {"GetParkingInfo": {"list_total_count": len(rows), "RESULT": {"CODE": "INFO-000"}, "row": list(rows)}}


def test_parse_keeps_fresh_rows_only():
    stale = dict(ROW, PKLT_CD="2", PRK_STTS_YN="3")
    broken = dict(ROW, PKLT_CD="3", TPKCT=0)
    over = dict(ROW, PKLT_CD="4", NOW_PRK_VHCL_CNT=2000.0)
    live = seoul_parking_live.parse(body(ROW, stale, broken, over))
    assert live == {"171721": dict(now=713, total=1260, updated="2026-11-16 17:04:43"),
                    "4": dict(now=1260, total=1260, updated="2026-11-16 17:04:43")}
    assert seoul_parking_live.parse({"RESULT": {"CODE": "INFO-200"}}) == {}


@pytest.fixture
def fake(monkeypatch):
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key=?", (seoul_parking_live.CACHE_KEY,))
    monkeypatch.setenv("SEOUL_OPEN_API_KEY", "test-key")
    state = dict(calls=[], answer=lambda: httpx.Response(200, json=body(ROW), request=httpx.Request("GET", "http://x")))

    def get(self, url, **kwargs):
        state["calls"].append(url)
        return state["answer"]()

    monkeypatch.setattr(httpx.Client, "get", get)
    yield state
    with store.connect() as db:
        db.execute("DELETE FROM cache WHERE key=?", (seoul_parking_live.CACHE_KEY,))


def test_one_call_is_cached(fake):
    assert seoul_parking_live.live_counts()["171721"]["now"] == 713
    assert seoul_parking_live.live_counts()["171721"]["total"] == 1260
    assert len(fake["calls"]) == 1 and fake["calls"][0].startswith("http://openapi.seoul.go.kr:8088/test-key/json/GetParkingInfo/")


def test_failure_and_missing_key_give_nothing(fake, monkeypatch):
    fake["answer"] = lambda: (_ for _ in ()).throw(httpx.ConnectTimeout("blocked"))
    assert seoul_parking_live.live_counts() == {}
    monkeypatch.delenv("SEOUL_OPEN_API_KEY")
    assert seoul_parking_live.live_counts() == {} and not seoul_parking_live.enabled()


def test_attach_live_to_seoul_lots_and_hide_the_code(monkeypatch):
    monkeypatch.setattr(seoul_parking_live, "live_counts", lambda: {"171721": dict(now=713, total=1260, updated="2026-11-16 17:04:43")})
    seoul = public_parking.details(dict(id="seoul-171721", name="세종로", fee_kind="유료", kind="공영", as_of="2026-11-02"), None)
    other = public_parking.details(dict(id="P-1", name="다른 곳", fee_kind="무료"), None)
    stops = [dict(lots=[dict(public=seoul), dict(public=other), dict(public=None)])]
    diagnostics = {}
    parking.attach_live(stops, diagnostics)
    assert seoul["live"]["now"] == 713 and "_seoul_code" not in seoul
    assert "live" not in other and diagnostics == dict(live_candidates=1, live_attached=1)
