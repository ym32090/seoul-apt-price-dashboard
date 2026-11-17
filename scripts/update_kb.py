#!/usr/bin/env python3
"""KB Seoul apartment average/median, sales/rent: guarded, full-history refresh.

The endpoint is reverse-documented in third-party PublicDataReader, not an
officially licensed public API. Using it may be subject to KB's terms. This
script is opt-in, and can never modify GitHub itself. It only creates a
candidate JSON file; an independent workflow controls any publication.

Run locally with --fixture-dir to test without network; --live deliberately
requires the KB_AUTO_FETCH_ENABLED=true flag set by the operator. Publication
is a separate GitHub Actions workflow gate.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/"
SOURCE_GROUPS = (
    ("sale_avg", "avgPrc", "01", "rows", "avg"),
    ("sale_median", "mdpsPrc", "01", "rows", "median"),
    ("rent_avg", "avgPrc", "02", "rental.rows", "avg"),
    ("rent_median", "mdpsPrc", "02", "rental.rows", "median"),
)
VALID_SCHEMA = "seoul-apt-price-v1"
OVERLAP_TOLERANCE_10K_KRW = 0.50  # 0.5 만원, for 4-decimal baseline rounding
MIN_OVERLAP = 12


class InvalidKBData(ValueError):
    """Refuse to publish ambiguous or inconsistent source data."""


def month_normalized(s):
    x = str(s).strip()
    if re.fullmatch(r"\d{6}", x):
        x = x[:4] + "-" + x[4:]
    if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", x):
        raise InvalidKBData("BAD_MONTH")
    return x


def price_normalized(v):
    if v is None or str(v).strip().lower() in ("", "-", "null", "nan"):
        return None
    try:
        f = float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        raise InvalidKBData("NON_NUMERIC_PRICE") from None
    if not math.isfinite(f) or f < 1000 or f > 1000000:
        raise InvalidKBData("PRICE_RANGE_OR_UNIT_ERROR")
    return round(f, 4)


def parse_response(payload):
    """A unique 서울 row, aligned monthly header, prices in expected 만원 magnitude.

    Actual KB endpoint output must be compared to the supplied XLSX baseline
    before the result is trusted; this function alone does NOT prove units.
    """
    body = payload.get("dataBody") if isinstance(payload, dict) else None
    if not isinstance(body, dict) or str(body.get("resultCode")) != "11000":
        raise InvalidKBData("BAD_KB_RESULT_CODE")
    data = body.get("data")
    if not isinstance(data, dict):
        raise InvalidKBData("NO_KB_DATA")
    dates, regions = data.get("날짜리스트"), data.get("데이터리스트")
    if not isinstance(dates, list) or not isinstance(regions, list):
        raise InvalidKBData("BAD_KB_SHAPE")
    candidates = [r for r in regions if isinstance(r, dict)
                  and str(r.get("지역명", "")).strip() in ("서울", "서울특별시")]
    if len(candidates) != 1:
        raise InvalidKBData("NON_UNIQUE_SEOUL")
    values = candidates[0].get("dataList")
    if not isinstance(values, list) or len(values) != len(dates):
        raise InvalidKBData("DATE_VALUE_MISMATCH")
    result = {}
    for date, value in zip(dates, values):
        m = month_normalized(date)
        if m in result:
            raise InvalidKBData("DUPLICATE_MONTH")
        result[m] = price_normalized(value)
    if len(result) < 12 or not any(v is not None for v in result.values()):
        raise InvalidKBData("TOO_FEW_OBSERVATIONS")
    return dict(sorted(result.items()))


def _month_index(m):
    return int(m[:4]) * 12 + int(m[5:])


def _dict_rows(rows):
    if not isinstance(rows, list):
        raise InvalidKBData("BAD_BASELINE_ROWS")
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            raise InvalidKBData("BAD_BASELINE_ROW")
        m = month_normalized(r.get("month", ""))
        if m in out:
            raise InvalidKBData("DUPLICATE_BASELINE_MONTH")
        out[m] = copy.deepcopy(r)
    return out


def merge_candidate(reference, new_series, checked_at=None):
    """Never revise known prices; only add previously unavailable month/value.

    All four series must pass baseline checks before even writing a candidate.
    If KB revises historical prices, fail and request human review rather than
    silently overwriting the verified history.
    """
    if not isinstance(reference, dict) or any(reference.get(k) != v for k, v in {
        "schema": VALID_SCHEMA, "source": "kb", "region": "서울",
        "housing_type": "아파트", "unit": "만원", "transaction": "매매"}.items()):
        raise InvalidKBData("BAD_BASELINE_SCHEMA")
    if not isinstance(reference.get("rental"), dict):
        raise InvalidKBData("BASELINE_RENT_MISSING")
