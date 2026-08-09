"""Parsers for the supported import formats. Pure functions, no IO."""

import csv
import io
import json
import re
from datetime import UTC, datetime
from typing import TypedDict


class ParsedRow(TypedDict):
    raw: str
    name: str
    type_hint: str | None  # movie | tv | None when unknown
    year: int | None
    watched_at: str | None  # ISO date


class ImportParseError(Exception):
    pass


# "Show: Season 1: Episode name", "Show: Limited Series: ...",
# "Show: Part 2: ...", "Show: Volume 1: ..." and localized variants are the
# common shapes in Netflix viewing-activity exports.
_TV_MARKER = re.compile(
    r":\s*(season|series|limited series|part|volume|chapter|saison|temporada|"
    r"collection|book)\b",
    re.IGNORECASE,
)


def _parse_netflix_date(value: str) -> str | None:
    value = value.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC).date().isoformat()
        except ValueError:
            continue
    return None


def split_netflix_title(raw: str) -> tuple[str, str | None]:
    """Return (name, type_hint). Series episodes collapse to the show name."""
    marker = _TV_MARKER.search(raw)
    if marker:
        return raw[: marker.start()].strip(), "tv"
    # Some episode rows have no season marker but still use two colons.
    parts = [p.strip() for p in raw.split(":")]
    if len(parts) >= 3:
        return parts[0], "tv"
    return raw.strip(), None


def parse_netflix_history(text: str) -> list[ParsedRow]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Title" not in reader.fieldnames:
        raise ImportParseError("This does not look like a Netflix viewing-activity CSV")
    rows: list[ParsedRow] = []
    for record in reader:
        raw = (record.get("Title") or "").strip()
        if not raw:
            continue
        name, type_hint = split_netflix_title(raw)
        rows.append(
            ParsedRow(
                raw=raw,
                name=name,
                type_hint=type_hint,
                year=None,
                watched_at=_parse_netflix_date(record.get("Date") or ""),
            )
        )
    return rows


def parse_netflix_mylist(text: str) -> list[ParsedRow]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Title Name" not in reader.fieldnames:
        raise ImportParseError("This does not look like the MyList.csv from a Netflix export")
    rows: list[ParsedRow] = []
    for record in reader:
        raw = (record.get("Title Name") or "").strip()
        if not raw:
            continue
        name, type_hint = split_netflix_title(raw)
        rows.append(ParsedRow(raw=raw, name=name, type_hint=type_hint, year=None, watched_at=None))
    return rows


def parse_json_payload(text: str) -> list[ParsedRow]:
    """Accepts [{"title": "...", "year": 2017, "type": "movie",
    "watched_at": "2024-01-31"}, ...]; only title is required."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportParseError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ImportParseError("expected a JSON array of titles")
    rows: list[ParsedRow] = []
    for entry in data:
        if not isinstance(entry, dict) or not str(entry.get("title") or "").strip():
            continue
        title = str(entry["title"]).strip()
        type_value = entry.get("type")
        year = entry.get("year")
        rows.append(
            ParsedRow(
                raw=title,
                name=title,
                type_hint=type_value if type_value in ("movie", "tv") else None,
                year=int(year) if isinstance(year, int) else None,
                watched_at=str(entry["watched_at"]) if entry.get("watched_at") else None,
            )
        )
    if not rows:
        raise ImportParseError("no usable titles in the JSON payload")
    return rows
