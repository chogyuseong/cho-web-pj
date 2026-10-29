"""Validate local operator-reviewed facts; never fetch submitted URLs."""

import json
import ipaddress
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, parse_qsl
from pydantic import BaseModel, Field, model_validator
from .service_time import today


class Submission(BaseModel):
    place_id: str = Field(min_length=1, max_length=150)
    source: str
    checked_at: date
    source_kind: Literal["official", "merchant"]
    reviewer: str = Field(min_length=1, max_length=80)
    permission_reference: str = Field(default="", max_length=300)
    scope: str = Field(min_length=5, max_length=500)
    valid_days: int = Field(default=30, ge=1, le=90)
    fields: dict

    @model_validator(mode="after")
    def valid(self):
        url = urlsplit(self.source)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.fragment
        ):
            raise ValueError("출처는 인증정보·프래그먼트 없는 HTTPS 원문 주소여야 합니다.")
        forbidden = {
            "apikey",
            "appkey",
            "token",
            "accesstoken",
            "clientsecret",
            "password",
            "signature",
            "authorization",
        }
        if any(
            key.lower().replace("_", "").replace("-", "") in forbidden
            for key, _ in parse_qsl(url.query)
        ):
            raise ValueError("출처에 비밀키나 인증 토큰을 넣지 마세요.")
        if url.hostname in ("localhost",) or url.hostname.endswith((".local", ".internal")):
            raise ValueError("공개 원문 주소를 사용하세요.")
        try:
            address = ipaddress.ip_address(url.hostname)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError("공개 원문 주소를 사용하세요.")
        if self.checked_at > today():
            raise ValueError("확인일은 미래일 수 없습니다.")
        if self.source_kind == "merchant" and not self.permission_reference.strip():
            raise ValueError("업체 제공 자료는 제공·사용 동의 증빙 위치를 적어주세요.")
        allowed = {
            "hours",
            "closed_days",
            "price",
            "reservation",
            "last_entry_offset",
            "price_unit",
            "menus",
            "closed_dates",
            "weekly_hours",
        }
        if not self.fields or set(self.fields) - allowed:
            raise ValueError("지원되는 운영 정보 필드만 입력하세요.")
        for key, value in self.fields.items():
            if key in ("hours", "price"):
                if (
                    not isinstance(value, list)
                    or len(value) != 2
                    or any(type(v) is not int or v < 0 for v in value)
                    or value[0] > value[1]
                ):
                    raise ValueError(key + " 범위를 확인하세요.")
                if key == "hours" and (value[0] >= value[1] or value[1] > 1440):
                    raise ValueError("영업시간은 같은 날 분 단위 범위여야 합니다.")
                if key == "price" and value[1] > 5000000:
                    raise ValueError("가격 범위를 확인하세요.")
            elif key == "closed_days" and (
                not isinstance(value, list)
                or any(type(v) is not int or not 0 <= v <= 6 for v in value)
            ):
                raise ValueError("휴무 요일은 월요일 0부터 일요일 6까지입니다.")
            elif key == "reservation" and type(value) is not bool:
                raise ValueError("예약 여부는 true/false입니다.")
            elif key == "last_entry_offset" and (type(value) is not int or not 0 <= value <= 240):
                raise ValueError("입장 마감 분을 확인하세요.")
            elif key == "price_unit" and value not in ("person", "group"):
                raise ValueError("가격 단위는 person/group입니다.")
            elif key == "closed_dates":
                if not isinstance(value, list) or len(value) > 366:
                    raise ValueError("휴무 날짜는 366개 이내입니다.")
                for item in value:
                    date.fromisoformat(item)
            elif key == "weekly_hours":
                if not isinstance(value, dict) or any(
                    k not in {str(i) for i in range(7)}
                    or not isinstance(v, list)
                    or len(v) != 2
                    or any(type(n) is not int for n in v)
                    or not 0 <= v[0] < v[1] <= 1440
                    for k, v in value.items()
                ):
                    raise ValueError("요일별 영업시간을 확인하세요.")
            elif key == "menus":
                if not isinstance(value, list) or not 1 <= len(value) <= 20:
                    raise ValueError("메뉴는 1~20개입니다.")
                for item in value:
                    if (
                        not isinstance(item, dict)
                        or set(item) - {"name", "amount", "representative"}
                        or not isinstance(item.get("name"), str)
                        or not 1 <= len(item["name"].strip()) <= 80
                        or type(item.get("amount")) is not int
                        or not 1 <= item["amount"] <= 5000000
                    ):
                        raise ValueError("메뉴명과 양의 원 단위 가격을 확인하세요.")
                    if "representative" in item and type(item["representative"]) is not bool:
                        raise ValueError("대표 메뉴 여부는 true/false입니다.")
        if "price" in self.fields and "price_unit" not in self.fields:
            raise ValueError("가격에는 person/group 단위가 필요합니다.")
        return self


def import_file(source, output, known_ids):
    output = Path(output)
    if output.exists():
        raise ValueError("기존 파일을 덮어쓰지 않습니다. 새 출력 파일을 선택하세요.")
    submissions = [
        Submission.model_validate(row) for row in json.loads(Path(source).read_text("utf-8"))
    ]
    result = {}
    for row in submissions:
        if row.place_id not in known_ids:
            raise ValueError("먼저 업체 이름·주소·좌표를 카탈로그에서 확인하세요: " + row.place_id)
        target = result.setdefault(row.place_id, {})
        for field, value in row.fields.items():
            if field in target:
                raise ValueError("동일 장소·필드가 중복되었습니다: " + row.place_id + "/" + field)
            target[field] = dict(
                value=value,
                source=row.source,
                checked_at=row.checked_at.isoformat(),
                scope=row.scope,
                valid_days=row.valid_days,
                source_kind=row.source_kind,
                reviewer=row.reviewer,
                permission_reference=row.permission_reference,
                verification_method="운영자 제공 검토 기록 · 자동 독립 검증 아님",
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return dict(places=len(result), fields=sum(len(r) for r in result.values()), output=str(output))
