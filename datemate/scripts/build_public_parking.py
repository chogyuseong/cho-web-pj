"""공공데이터포털 '전국주차장정보표준데이터' CSV → datemate/data/public_parking.json.

사용: python scripts/build_public_parking.py <내려받은 CSV 경로>
- 공공데이터포털(data.go.kr)에서 '전국주차장정보표준데이터' 파일(CSV)을 내려받아 넣는다. 인코딩은 CP949·UTF-8 모두 읽는다.
- 주차장 칸(app/parking.py)이 요금·운영시간을 붙이는 데 쓰는 열만 남긴다. 좌표가 없거나 대한민국 범위 밖인 행은 뺀다.
- 자료를 다시 내려받으면 같은 명령으로 덮어쓴다. 행마다 데이터기준일자가 남아 화면에 기준일로 보인다.
"""

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
            ]
        )
    return out, skipped


def main(path):
    rows = list(csv.DictReader(io.StringIO(read_text(path))))
    if not rows or "주차장명" not in rows[0] or "위도" not in rows[0]:
        raise SystemExit("전국주차장정보표준데이터 CSV 가 아닌 것 같아요(주차장명·위도 열이 없음).")
    converted, skipped = convert(rows)
    payload = dict(
        source="공공데이터포털 전국주차장정보표준데이터",
        columns=list(COLUMNS),
        rows=converted,
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.name}: {len(converted)}곳 저장, 좌표 없음·범위 밖 {skipped}곳 제외 ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
