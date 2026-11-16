"""공공데이터포털 '전국주차장정보표준데이터' CSV (+ 서울 열린데이터광장 '서울시 공영주차장 안내 정보' CSV) → datemate/data/public_parking.json.

사용: python scripts/build_public_parking.py <전국 CSV> [<서울 CSV>]
- 공공데이터포털(data.go.kr)에서 '전국주차장정보표준데이터' 파일(CSV)을 내려받아 넣는다. 인코딩은 CP949·UTF-8 모두 읽는다.
- 주차장 칸(app/parking.py)이 요금·운영시간을 붙이는 데 쓰는 열만 남긴다. 좌표가 없거나 대한민국 범위 밖인 행은 뺀다.
- 자료를 다시 내려받으면 같은 명령으로 덮어쓴다. 행마다 데이터기준일자가 남아 화면에 기준일로 보인다.
- 서울 파일(2026-11-16 기준 2,255행): 좌표는 주로 노상 주차장 구간에만 있고 노외 주차장(건물·부지)은 대부분 주소뿐이다.
  좌표가 있는 행은 이름별로 묶어 가운데 점 하나로 넣고, 좌표가 없는 행은 좌표 없이(lat·lon null) 구와 이름만으로 넣는다.
  주소를 좌표로 바꾸는 일괄 지오코딩은 하지 않는다. 좌표 없는 행은 네이버 검색으로 찾은 주차장과 '같은 구 + 이름 핵심'으로만 맞춘다(app/public_parking.by_name).
  전국 자료의 서울 행 가운데 서울 파일의 같은 주차장(50m 안, 같은 이름 핵심)은 뺀다.
"""

import csv
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.public_parking import district, name_core  # noqa: E402  같은 이름 핵심·구 규칙을 앱과 함께 쓴다
OUT = ROOT / "data" / "public_parking.json"
COLUMNS = (
    "id",
    "name",
    "kind",
    "address",
    "lat",
    "lon",
    "fee_kind",
    "base_minutes",
    "base_fee",
    "extra_minutes",
    "extra_fee",
    "day_fee",
    "days",
    "weekday",
    "saturday",
    "holiday",
    "as_of",
    "provider",
    "free_days",
    "district",
)


def read_text(path):
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit("CSV 인코딩을 읽지 못했어요(UTF-8·CP949 아님).")


def number(value):
    text = str(value or "").replace(",", "").strip()
    try:
        return int(float(text)) if text else None
    except ValueError:
        return None


def clock(value):
    """'09:00' 꼴만 남긴다. 빈 값·이상한 값은 None."""
    text = str(value or "").strip()
    if len(text) == 5 and text[2] == ":" and text[:2].isdigit() and text[3:].isdigit():
        hour, minute = int(text[:2]), int(text[3:])
        if 0 <= hour <= 24 and 0 <= minute < 60:
            return text
    return None


def span(start, end):
    start, end = clock(start), clock(end)
    return [start, end] if start and end else None


def convert(rows):
    out, skipped = [], 0
    for r in rows:
        try:
            lat, lon = float(r["위도"]), float(r["경도"])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if not (33.0 <= lat <= 38.7 and 124.5 <= lon <= 132.0):
            skipped += 1
            continue
        address = (r.get("소재지도로명주소") or "").strip() or (r.get("소재지지번주소") or "").strip()
        out.append(
            [
                (r.get("주차장관리번호") or "").strip(),
                " ".join((r.get("주차장명") or "").split()),
                (r.get("주차장구분") or "").strip(),
                address,
                round(lat, 6),
                round(lon, 6),
                (r.get("요금정보") or "").strip(),
                number(r.get("주차기본시간")),
                number(r.get("주차기본요금")),
                number(r.get("추가단위시간")),
                number(r.get("추가단위요금")),
                number(r.get("1일주차권요금")),
                (r.get("운영요일") or "").strip(),
                span(r.get("평일운영시작시각"), r.get("평일운영종료시각")),
                span(r.get("토요일운영시작시각"), r.get("토요일운영종료시각")),
                span(r.get("공휴일운영시작시각"), r.get("공휴일운영종료시각")),
                (r.get("데이터기준일자") or "").strip(),
                (r.get("제공기관명") or "").strip(),
                None,
                district(address),
            ]
        )
    return out, skipped


def hhmm(value):
    text = str(value or "").strip()
    return f"{text[:2]}:{text[2:]}" if len(text) == 4 and text.isdigit() else None


def seoul_span(row, start, end):
    return span(hhmm(row.get(start)), hhmm(row.get(end)))


def convert_seoul(rows):
    """서울시 공영주차장 안내 정보 → 같은 열의 행 목록. 같은 이름은 하나로(좌표 있으면 점들의 가운데)."""
    groups = {}
    for r in rows:
        name = " ".join((r.get("주차장명") or "").split())
        if name:
            groups.setdefault(name, []).append(r)
    out = []
    for name, group in groups.items():
        r = group[0]
        points = []
        for g in group:
            try:
                lat, lon = float(g["위도"]), float(g["경도"])
            except (KeyError, TypeError, ValueError):
                continue
            if 37.0 <= lat <= 38.0 and 126.5 <= lon <= 127.5:
                points.append((lat, lon))
        lat = round(sum(p[0] for p in points) / len(points), 6) if points else None
        lon = round(sum(p[1] for p in points) / len(points), 6) if points else None
        free = [label for key, label in (("토요일 유,무료 구분명", "토요일"), ("공휴일 유,무료 구분명", "공휴일"))
                if (r.get(key) or "").strip() == "무료"]
        paid = (r.get("유무료구분명") or "").strip()
        weekday = seoul_span(r, "평일 운영 시작시각(HHMM)", "평일 운영 종료시각(HHMM)")
        weekend = seoul_span(r, "주말 운영 시작시각(HHMM)", "주말 운영 종료시각(HHMM)")
        holiday = seoul_span(r, "공휴일 운영 시작시각(HHMM)", "공휴일 운영 종료시각(HHMM)")
        days = "+".join(day for day, value in (("평일", weekday), ("토요일", weekend), ("공휴일", holiday)) if value)
        address = "서울특별시 " + " ".join((r.get("주소") or "").split())
        out.append(
            [
                "seoul-" + (r.get("주차장코드") or "").strip(),
                name,
                "공영",
                address,
                lat,
                lon,
                paid if paid in ("유료", "무료") else "",
                number(r.get("기본 주차 시간(분 단위)")),
                number(r.get("기본 주차 요금")),
                number(r.get("추가 단위 시간(분 단위)")),
                number(r.get("추가 단위 요금")),
                number(r.get("일 최대 요금")) or None,
                days,
                weekday,
                weekend,
                holiday,
                (r.get("최종데이터 동기화 시간") or "").strip()[:10],
                "서울특별시",
                "·".join(free) + " 무료" if free and paid == "유료" else None,
                district(address),
            ]
        )
    return out


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111_320, (lon2 - lon1) * 111_320 * math.cos(math.radians(lat1)))


def drop_national_duplicates(national, seoul):
    """전국 자료의 서울 행 가운데 서울 파일에 같은 주차장(50m 안, 같은 이름 핵심)이 있는 행을 뺀다."""
    index = COLUMNS.index
    placed = [r for r in seoul if r[index("lat")] is not None]
    kept = []
    for row in national:
        if str(row[index("address")]).startswith("서울"):
            core = name_core(row[index("name")])
            if any(
                name_core(s[index("name")]) == core
                and metres(row[index("lat")], row[index("lon")], s[index("lat")], s[index("lon")]) <= 50
                for s in placed
            ):
                continue
        kept.append(row)
    return kept


def main(path, seoul_path=None):
    rows = list(csv.DictReader(io.StringIO(read_text(path))))
    if not rows or "주차장명" not in rows[0] or "위도" not in rows[0]:
        raise SystemExit("전국주차장정보표준데이터 CSV 가 아닌 것 같아요(주차장명·위도 열이 없음).")
    converted, skipped = convert(rows)
    seoul = []
    if seoul_path:
        seoul_rows = list(csv.DictReader(io.StringIO(read_text(seoul_path))))
        if not seoul_rows or "주차장코드" not in seoul_rows[0] or "주말 운영 시작시각(HHMM)" not in seoul_rows[0]:
            raise SystemExit("서울시 공영주차장 안내 정보 CSV 가 아닌 것 같아요.")
        seoul = convert_seoul(seoul_rows)
        before = len(converted)
        converted = drop_national_duplicates(converted, seoul)
        print(f"서울 파일 {len(seoul)}곳(좌표 없음 {sum(r[4] is None for r in seoul)}곳), 전국 자료와 겹친 {before - len(converted)}곳 뺌")
        converted += seoul
    payload = dict(
        source="공공데이터포털 전국주차장정보표준데이터" + (" · 서울 열린데이터광장 서울시 공영주차장 안내 정보" if seoul else ""),
        columns=list(COLUMNS),
        rows=converted,
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.name}: {len(converted)}곳 저장, 좌표 없음·범위 밖 {skipped}곳 제외 ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
