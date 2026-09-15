"""Feedback River transformation, privacy, validation, and aggregation pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

REQUIRED_FIELDS = {
    "id": str,
    "created_at": str,
    "country": str,
    "payment_method": str,
    "channel": str,
    "rating": (int, float),
    "comment": str,
}
DIMENSIONS = ("country", "payment_method", "channel")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
URL_RE = re.compile(r"https?://[^\s<>()]+", re.I)
ORDER_RE = re.compile(r"\b(?:order|commande|pedido|bestellung)[\s#:_-]*[A-Z0-9-]{4,}\b", re.I)


class DataValidationError(ValueError):
    """Raised when an adapter response does not match the configured contract."""


def _stable_token(kind: str, value: str, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{kind}:{value.lower()}".encode()).hexdigest()[:10]
    return f"[{kind.upper()}-{digest}]"


def anonymize_text(value: str, salt: str = "feedback-river-public-v1") -> str:
    """Replace common direct identifiers deterministically, preserving readability."""
    value = URL_RE.sub(lambda m: _stable_token("url", m.group(0), salt), value)
    value = EMAIL_RE.sub(lambda m: _stable_token("email", m.group(0), salt), value)
    value = PHONE_RE.sub(lambda m: _stable_token("phone", m.group(0), salt), value)
    value = ORDER_RE.sub(lambda m: _stable_token("order", m.group(0), salt), value)
    return value


def validate_records(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise DataValidationError("Expected a non-empty JSON array of feedback records")
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise DataValidationError(f"Record {index} must be an object")
        missing = [name for name in REQUIRED_FIELDS if name not in record]
        if missing:
            raise DataValidationError(f"Record {index} is missing required fields: {', '.join(missing)}")
        for name, expected in REQUIRED_FIELDS.items():
            if not isinstance(record[name], expected) or (name == "rating" and not 0 <= record[name] <= 5):
                raise DataValidationError(f"Record {index}.{name} has an invalid type or value")
        try:
            datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise DataValidationError(f"Record {index}.created_at must be ISO-8601") from error
        validated.append(dict(record))
    return validated


def transform(records: Iterable[dict[str, Any]], salt: str = "feedback-river-public-v1") -> list[dict[str, Any]]:
    transformed = []
    for record in validate_records(list(records)):
        item = dict(record)
        item["comment"] = anonymize_text(item["comment"], salt)
        for field in ("email", "phone", "order_id", "url"):
            if field in item and item[field] is not None:
                kind = "order" if field == "order_id" else field
                item[field] = _stable_token(kind, str(item[field]), salt)
        transformed.append(item)
    return transformed


def _period_start(period: str, now: date) -> date:
    if period == "daily":
        return now
    if period == "weekly":
        return now - timedelta(days=now.weekday())
    raise ValueError(f"Unsupported period: {period}")


def aggregate(records: list[dict[str, Any]], period: str = "daily", now: date | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).date()
    start = _period_start(period, now)
    selected = []
    for record in records:
        created = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")).date()
        if start <= created <= now:
            selected.append(record)
    counts = Counter(record["rating"] for record in selected)
    by_dimension: dict[str, list[dict[str, Any]]] = {}
    for dimension in DIMENSIONS:
        grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in selected:
            grouped[record[dimension]].append(record)
        by_dimension[dimension] = [
            {"value": value, "count": len(items), "average_rating": round(sum(x["rating"] for x in items) / len(items), 2)}
            for value, items in sorted(grouped.items())
        ]
    average = round(sum(record["rating"] for record in selected) / len(selected), 2) if selected else 0
    highlights = sorted(selected, key=lambda item: (item["rating"], item["created_at"]))[:5]
    return {
        "period": period,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "total": len(selected),
        "average_rating": average,
        "rating_distribution": {str(rating): counts.get(rating, 0) for rating in range(1, 6)},
        "dimensions": by_dimension,
        "highlights": highlights,
    }


def load_fixture(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if isinstance(payload, dict):
        payload = payload.get("feedback")
    return validate_records(payload)


def fetch_medallia(url: str, token: str | None = None) -> list[dict[str, Any]]:
    """Fetch a configured endpoint; mapping is intentionally done by map_medallia_response."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - URL is explicit operator configuration.
        return map_medallia_response(json.load(response))


def map_medallia_response(payload: Any) -> list[dict[str, Any]]:
    """Map an operator-supplied Medallia response to the canonical fields.

    Medallia deployments expose different APIs and response shapes. The default
    contract expects a list (or ``feedback`` list) already using canonical fields.
    Configure a separate adapter here for an approved tenant-specific mapping;
    this code never invents an endpoint or field names.
    """
    if isinstance(payload, dict):
        payload = payload.get("feedback")
    return validate_records(payload)


def build_payload(records: list[dict[str, Any]], generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": generated_at,
        "records": records,
        "daily": aggregate(records, "daily"),
        "weekly": aggregate(records, "weekly"),
    }


def load_source() -> list[dict[str, Any]]:
    fixture = os.environ.get("FEEDBACK_FIXTURE", "data/fixture.json")
    if os.environ.get("MEDALLIA_API_URL"):
        return fetch_medallia(os.environ["MEDALLIA_API_URL"], os.environ.get("MEDALLIA_API_TOKEN"))
    return load_fixture(Path(fixture))
