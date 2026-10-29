"""Field-specific operating evidence, independent of discovery timestamps."""

import json
import os
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit
from .config import ROOT
from .service_time import today

FIELDS = {
    "hours",
    "closed_days",
    "price",
    "reservation",
    "weekly_hours",
    "last_entry_offset",
    "closed_dates",
    "price_unit",
    "menus",
}


def evidence_rows():
    path = ROOT / "data/operating_evidence.json"
    records = json.loads(path.read_text("utf-8")) if path.exists() else {}
    imported = os.getenv("DATEMATE_OPERATING_EVIDENCE_FILE", "").strip()
    if imported:
        extra = json.loads(Path(imported).read_text("utf-8"))
        for pid, fields in extra.items():
            target = records.setdefault(pid, {})
            for key, record in fields.items():
                if key not in target or record["checked_at"] >= target[key]["checked_at"]:
                    target[key] = record
    return records


def apply_evidence(place, records=None):
    records = evidence_rows() if records is None else records
    result = dict(place)
    details = {}
    verified = set(place.get("operations_verified_fields", []))
    for field, record in records.get(place["id"], {}).items():
        if field not in FIELDS or not isinstance(record, dict):
            continue
        days = record.get("valid_days", 30)
        if type(days) is not int or not 1 <= days <= 90 or "value" not in record:
            continue
        if (
            record.get("source_kind") == "merchant"
            and not record.get("permission_reference", "").strip()
        ):
            continue
        parsed = urlsplit(record.get("source", ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            continue
        try:
            age = (today() - date.fromisoformat(record["checked_at"])).days
        except (KeyError, TypeError, ValueError):
            continue
        current = 0 <= age <= days
        details[field] = dict(
            source=record["source"],
            checked_at=record["checked_at"],
            scope=record.get("scope", ""),
            current=current,
            age_days=age,
            source_kind=record.get("source_kind", "official"),
        )
        # An expired review must not overwrite newer or separately maintained data.
        if current:
            result[field] = record["value"]
            verified.add(field)
        else:
            verified.discard(field)
    result.update(operations_evidence=details, operations_verified_fields=sorted(verified))
    if result.get("hours") and result.get("last_entry_offset") is not None:
        result["last_entry"] = result["hours"][1] - result["last_entry_offset"]
    return result


def field_current(place, key):
    record = place.get("operations_evidence", {}).get(key)
    if record is not None:
        return record["current"]
    if key not in place.get("operations_verified_fields", []) or not place.get("operations_source"):
        return False
    try:
        return 0 <= (today() - date.fromisoformat(place["operations_checked_at"][:10])).days <= 90
    except (KeyError, TypeError, ValueError):
        return False
