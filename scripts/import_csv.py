#!/usr/bin/env python3
"""Import a verified monthly CSV into public website JSON (no external network).
Input CSV must have columns: month, avg, median (price unit: 10,000 KRW).
Optional 'region' column must be 서울; no guesswork for other units.
Values are merged by month while preserving any existing non-empty metric.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path


def validate_rows(rows):
    out = {}
    for i, row in enumerate(rows, 2):
        month = (row.get("month") or "").strip()
        if len(month) != 7 or month[4] != "-" or not month[:4].isdigit() or not month[5:].isdigit() or not 1 <= int(month[5:]) <= 12:
            raise ValueError(f"{i}행 기준월 오류: {month}")
        if row.get("region") and row["region"].strip() not in ("서울", "서울특별시"):
            raise ValueError(f"{i}행 서울 전체가 아닌 지역")
        result = {}
        for key in ("avg", "median"):
            raw = str(row.get(key) or "").replace(",", "").strip()
            if not raw:
                result[key] = None
                continue
            number = float(raw)
            if not math.isfinite(number) or not 1000 <= number < 1000000:
                raise ValueError(f"{i}행 가격 오류/단위 확인 필요: {key}={raw}")
            result[key] = number
        if result["avg"] is None and result["median"] is None:
            continue
        if month in out:
            raise ValueError(f"중복 기준월: {month}")
        out[month] = {"month": month, **result}
    if not out:
        raise ValueError("유효한 월별 가격 자료가 없습니다")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True, choices=["kb", "reb"])
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    out_path = args.out or Path(__file__).resolve().parents[1] / "data" / (args.source + ".json")
    with args.csv.open(encoding="utf-8-sig", newline="") as f:
        data = validate_rows(csv.DictReader(f))
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    if payload["source"] != args.source:
        raise ValueError("기존 파일 출처와 입력한 출처가 다릅니다")
    existing = {r["month"]: r for r in payload["rows"]}
    for month, row in data.items():
        old = existing.get(month, {"month": month, "avg": None, "median": None})
        for metric in ("avg", "median"):
            if row[metric] is not None:
                old[metric] = row[metric]
        existing[month] = old
    payload["rows"] = [existing[k] for k in sorted(existing)]
    payload["verification"] = "USER_SUPPLIED_CSV_CHECK_SOURCE_AND_UNIT"
    payload["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CSV {len(data)}개월을 {out_path}에 반영했습니다. 총 {len(existing)}개월")


if __name__ == "__main__":
    main()
