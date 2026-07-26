"""Offline validation for the frozen JP/ja Keyword Planner input universe.

This module validates a pre-measurement input list.  It does not fetch search
volume, call Google Ads, or turn relative Google Trends indices into demand
evidence.  Raw provider exports remain outside the repository boundary.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


EXPECTED_COLUMNS = (
    "universe_version",
    "country",
    "language",
    "cluster_id",
    "intent",
    "vendor",
    "query",
)
ALLOWED_INTENTS = frozenset(
    {"category", "comparison", "pricing", "alternative", "fit", "brand"}
)
ALLOWED_VENDORS = frozenset(
    {"", "semrush", "se-ranking", "mangools", "serpstat", "hubspot"}
)
_VERSION_PATTERN = re.compile(r"^jp-ja-v[1-9][0-9]*$")
_CLUSTER_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$")
_EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?<!\d)\d{2,4}[-－ー ]\d{2,4}[-－ー ]\d{3,4}(?!\d)")
_LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{7,}(?!\d)")


@dataclass(frozen=True, slots=True)
class KeywordUniverseRow:
    universe_version: str
    country: str
    language: str
    cluster_id: str
    intent: str
    vendor: str
    query: str


@dataclass(frozen=True, slots=True)
class KeywordUniverseSummary:
    universe_version: str
    country: str
    language: str
    keyword_count: int
    cluster_count: int
    vendor_counts: tuple[tuple[str, int], ...]
    intent_counts: tuple[tuple[str, int], ...]
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "cluster_count": self.cluster_count,
            "country": self.country,
            "intent_counts": dict(self.intent_counts),
            "keyword_count": self.keyword_count,
            "language": self.language,
            "sha256": self.sha256,
            "universe_version": self.universe_version,
            "vendor_counts": dict(self.vendor_counts),
        }


def normalize_query(value: str) -> str:
    """Normalize only exact-delivery noise; never remove meaning-bearing words."""

    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def load_keyword_universe(
    path: Path,
    *,
    minimum_keywords: int = 100,
    maximum_keywords: int = 200,
) -> tuple[KeywordUniverseRow, ...]:
    if minimum_keywords < 1 or maximum_keywords < minimum_keywords:
        raise ValueError("keyword count bounds are invalid")

    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ValueError(
                "keyword universe columns must exactly equal "
                + ",".join(EXPECTED_COLUMNS)
            )
        raw_rows = list(reader)

    if not minimum_keywords <= len(raw_rows) <= maximum_keywords:
        raise ValueError(
            f"keyword universe must contain {minimum_keywords}–{maximum_keywords} rows"
        )

    rows: list[KeywordUniverseRow] = []
    seen_queries: set[str] = set()
    for number, raw in enumerate(raw_rows, start=2):
        if any(value is None for value in raw.values()):
            raise ValueError(f"row {number} has a missing column")

        universe_version = raw["universe_version"].strip()
        country = raw["country"].strip()
        language = raw["language"].strip()
        cluster_id = raw["cluster_id"].strip()
        intent = raw["intent"].strip()
        vendor = raw["vendor"].strip()
        query = normalize_query(raw["query"])

        if not _VERSION_PATTERN.fullmatch(universe_version):
            raise ValueError(f"row {number} has an invalid universe version")
        if country != "JP" or language != "ja":
            raise ValueError(f"row {number} must use country=JP and language=ja")
        if not _CLUSTER_PATTERN.fullmatch(cluster_id):
            raise ValueError(f"row {number} has an invalid cluster_id")
        if intent not in ALLOWED_INTENTS:
            raise ValueError(f"row {number} has an unknown intent")
        if vendor not in ALLOWED_VENDORS:
            raise ValueError(f"row {number} has an unknown vendor")
        if intent == "brand" and not vendor:
            raise ValueError(f"row {number} brand intent requires vendor")
        if intent != "brand" and vendor:
            raise ValueError(f"row {number} non-brand intent cannot name a vendor")
        if not 2 <= len(query) <= 120:
            raise ValueError(f"row {number} query length is outside 2–120 characters")
        if (
            _EMAIL_PATTERN.search(query)
            or _URL_PATTERN.search(query)
            or _PHONE_PATTERN.search(query)
            or _LONG_NUMBER_PATTERN.search(query)
        ):
            raise ValueError(f"row {number} query may contain PII, a URL, or an identifier")
        if query in seen_queries:
            raise ValueError(f"row {number} duplicates a normalized query")
        seen_queries.add(query)

        rows.append(
            KeywordUniverseRow(
                universe_version=universe_version,
                country=country,
                language=language,
                cluster_id=cluster_id,
                intent=intent,
                vendor=vendor,
                query=query,
            )
        )

    versions = {row.universe_version for row in rows}
    if len(versions) != 1:
        raise ValueError("keyword universe must use exactly one version")
    return tuple(rows)


def summarize_keyword_universe(
    rows: tuple[KeywordUniverseRow, ...],
) -> KeywordUniverseSummary:
    if not rows:
        raise ValueError("keyword universe cannot be empty")
    versions = {row.universe_version for row in rows}
    countries = {row.country for row in rows}
    languages = {row.language for row in rows}
    if len(versions) != 1 or countries != {"JP"} or languages != {"ja"}:
        raise ValueError("keyword universe scope is inconsistent")

    canonical_rows = sorted(
        (
            {
                "cluster_id": row.cluster_id,
                "country": row.country,
                "intent": row.intent,
                "language": row.language,
                "query": row.query,
                "universe_version": row.universe_version,
                "vendor": row.vendor,
            }
            for row in rows
        ),
        key=lambda item: item["query"],
    )
    canonical = json.dumps(
        canonical_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    vendor_counts = Counter(row.vendor or "generic" for row in rows)
    intent_counts = Counter(row.intent for row in rows)
    return KeywordUniverseSummary(
        universe_version=next(iter(versions)),
        country="JP",
        language="ja",
        keyword_count=len(rows),
        cluster_count=len({row.cluster_id for row in rows}),
        vendor_counts=tuple(sorted(vendor_counts.items())),
        intent_counts=tuple(sorted(intent_counts.items())),
        sha256=hashlib.sha256(canonical).hexdigest(),
    )
