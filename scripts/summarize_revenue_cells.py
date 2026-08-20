#!/usr/bin/env python3
"""Validate safe daily aggregates and emit decision-safe revenue metrics.

The input is already aggregated and must not contain event-, visitor-, cookie-,
affiliate-URL-, or query-level data. Unknown maturity and commission remain
JSON null; they are never converted to zero.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from saas_preflight.revenue_cells import (
    RevenueCellDailyAggregate,
    summarize_revenue_cell,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    rows = TypeAdapter(tuple[RevenueCellDailyAggregate, ...]).validate_json(
        args.input.read_text(encoding="utf-8")
    )
    summary = summarize_revenue_cell(rows)
    print(summary.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
