#!/usr/bin/env python3
"""Fetch official R-ONE Seoul apartment monthly sale mean/median into data/reb.json.

Requires a privately held R-ONE API key (REB_API_KEY environment variable).
Never put the key in HTML or the JSON output.

The average statistical table A_2024_00060 is confirmed against R-ONE.
Median table ID must be independently checked in R-ONE statistics code search;
do not guess it. Set REB_MEDIAN_STATBL_ID when verified.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error

API = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
CATALOG_API = "https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do"
AVERAGE_STATBL_ID = "A_2024_00060"
SEOUL_CLS_ID = "500008"
ITEM_ID = "100001"
SCHEMA = "seoul-apt-price-v1"


def parse_page(payload):
    blocks = payload.get("SttsApiTblData")
    if not isinstance(blocks, list):
        raise ValueError("R-ONE API 응답 형식이 아닙니다")
    total = None
    rows = []
    for block in blocks:
        for meta in block.get("head", []):
            if "list_total_count" in meta:
                total = int(meta["list_total_count"])
            info = meta.get("RESULT", {})
            if info and info.get("CODE") != "INFO-000":
                raise RuntimeError("R-ONE 오류: " + str(info))
        rows.extend(block.get("row", []))
    return total, rows


def fetch_pages(api_key, stat_id, start, end, page_size=1000, opener=None):
    if not api_key or not api_key.strip():
        raise ValueError("REB_API_KEY가 없습니다. 샘플 5건을 전체 이력으로 오인하지 않도록 중단합니다")
    if not stat_id or not stat_id.isascii() or not stat_id.startswith("A_"):
        raise ValueError("통계표 ID를 공식 사이트에서 확인해주세요")
    op = opener or urllib.request.urlopen
    gathered = []
    index = 1
    while True:
        params = {
            "KEY": api_key,
            "Type": "json",
            "STATBL_ID": stat_id,
            "DTACYCLE_CD": "MM",
            "CLS_ID": SEOUL_CLS_ID,
            "ITM_ID": ITEM_ID,
            "START_WRTTIME": start,
            "END_WRTTIME": end,
            "pIndex": index,
            "pSize": page_size,
        }
        req = urllib.request.Request(
            API + "?" + urllib.parse.urlencode(params),
            headers={"Accept": "application/json", "User-Agent": "SeoulAptDashboard/1.1"},
        )
        # Never log request URL: it contains the private API key.
        try:
            with op(req, timeout=35) as resp:
                page = json.load(resp)
        except urllib.error.HTTPError as exc:
            raise RuntimeError("R-ONE API HTTP 오류: " + str(exc.code)) from None
        except urllib.error.URLError:
            raise RuntimeError("R-ONE API 접속 실패 (네트워크/인증키/접근 정책 확인)") from None
        total, rows = parse_page(page)
        if total is None:
            raise ValueError("응답에 총 건수가 없습니다. API 권한 또는 통계표 ID 확인 필요")
        if total == 0:
            raise ValueError("조회 결과가 0건입니다. R-ONE 통계표 ID와 지역코드 확인 필요")
        if not rows:
            raise ValueError("페이지에 데이터가 없습니다. API 응답 확인 필요")
        gathered.extend(rows)
        if len(gathered) >= total:
            break
        if len(rows) < page_size:
            raise ValueError(f"페이지 누락 가능성: {len(gathered)}/{total}건. 샘플 모드 또는 페이지 처리를 확인하세요")
        index += 1
        if index > 20:
            raise ValueError("비정상적인 페이지 수")
    if len(gathered) != total:
        raise ValueError(f"전체 {total}건과 수집 {len(gathered)}건 불일치")
    if len(gathered) <= 5 and int(start[:4]) < int(end[:4]):
        raise ValueError("5건 이하의 응답입니다. 인증키 미적용 샘플모드 가능성 때문에 게시하지 않습니다")
    return gathered


def find_median_table(api_key, opener=None):
    """Discover median table ID from official metadata. Never assume a sequential ID."""
    op = opener or urllib.request.urlopen
    found = []
    page_size = 1000
    for page_idx in range(1, 25):
        params = {"KEY": api_key, "Type": "json", "pIndex": page_idx, "pSize": page_size}
        req = urllib.request.Request(CATALOG_API + "?" + urllib.parse.urlencode(params), headers={"User-Agent":"SeoulAptDashboard/1.1"})
        try:
            with op(req, timeout=35) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            raise RuntimeError("R-ONE 목록 API HTTP 오류: " + str(exc.code)) from None
        except urllib.error.URLError:
            raise RuntimeError("R-ONE 통계목록 API 접속 실패") from None
        blocks = payload.get("SttsApiTbl", [])
        if not isinstance(blocks, list):
            raise ValueError("R-ONE 통계목록 응답 형식 오류")
        total = None
        rows = []
        for block in blocks:
            for meta in block.get("head", []):
                if "list_total_count" in meta: total = int(meta["list_total_count"])
                info = meta.get("RESULT", {})
                if info and info.get("CODE") != "INFO-000": raise RuntimeError("R-ONE 목록 API 오류: " + str(info))
            rows.extend(block.get("row", []))
        for row in rows:
            name = str(row.get("STATBL_NM", "")).replace(" ", "")
            if "중위" in name and "매매" in name and "아파트" in name and "월" in name:
                found.append((str(row.get("STATBL_ID", "")), name))
        if total is None: raise ValueError("R-ONE 목록 총건수 누락")
        if page_idx * page_size >= total: break
        if len(rows)<page_size: raise ValueError("R-ONE 목록이 부분 조회되었습니다")
    unique = sorted(set(x[0] for x in found))
    if len(unique)==1: return unique[0]
    if len(unique)>1:
        print("중위 통계표 후보가 복수입니다. 공식 표 이름 확인 후 REB_MEDIAN_STATBL_ID 지정:", found)
    else:
        print("중위 통계표를 공식 목록에서 유일하게 식별하지 못했습니다. 자동 추측하지 않습니다")
    return None

def to_prices(rows, stat_id):
    out = {}
    for r in rows:
        if str(r.get("STATBL_ID", "")) != stat_id:
            raise ValueError("다른 통계표 행이 혼입됨")
        if str(r.get("CLS_ID", "")) != SEOUL_CLS_ID or str(r.get("CLS_NM", "")) not in ("서울", "서울특별시"):
            raise ValueError("서울 전체가 아닌 지역의 응답이 혼입됨")
        if str(r.get("ITM_ID", "")) != ITEM_ID:
            raise ValueError("다른 항목이 혼입됨")
        ym = str(r.get("WRTTIME_IDTFR_ID", ""))
        if len(ym) != 6 or not ym.isdigit() or not 1 <= int(ym[4:]) <= 12:
            raise ValueError("기준월 형식이 잘못됨: " + ym)
        n = r.get("DTA_VAL")
        if n is None or n == "":
            continue
        n = float(n)
        unit = str(r.get("UI_NM", "")).replace(" ", "")
        if unit in ("천원", "천원/호", "천원/호당"):
            v = n / 10
        elif unit in ("만원", "만원/호", "만원/호당"):
            v = n
        elif unit in ("원", "원/호"):
            v = n / 10000
        else:
            raise ValueError("미지원 가격 단위: " + unit)
        if not 1000 <= v <= 1000000:
            raise ValueError("가격 크기 오류: " + str(v))
        month = f"{ym[:4]}-{ym[4:]}"
        if month in out:
            raise ValueError("월 중복: " + month)
        out[month] = round(v, 4)
    return out


def build_document(avg, median=None, median_table_id=None):
    median = median or {}
    months = sorted(set(avg) | set(median))
    rows = [dict(month=m, avg=avg.get(m), median=median.get(m)) for m in months]
    if not rows:
        raise ValueError("원본 데이터가 없습니다")
    return {
        "schema": SCHEMA,
        "source": "reb",
        "region": "서울",
        "housing_type": "아파트",
        "transaction": "매매",
        "unit": "만원",
        "origin": "한국부동산원 R-ONE 전국주택가격동향조사(월간)",
        "source_url": "https://www.reb.or.kr/r-one/portal/stat/easyStatPage/A_2024_00060.do",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "verification": "R_ONE_OFFICIAL_API_KEY_AUTHENTICATED" if median else "R_ONE_OFFICIAL_API_AVERAGE_ONLY_MEDIAN_UNCONFIRMED",
        "statistics": {"avg_table_id": AVERAGE_STATBL_ID, "median_table_id": median_table_id, "seoul_cls_id": SEOUL_CLS_ID},
        "rows": rows,
    }


def main():
    p = argparse.ArgumentParser(description="한국부동산원 공식 R-ONE 시계열 JSON 갱신")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data/reb.json")
    p.add_argument("--start", default="2015")
    p.add_argument("--end", default=str(dt.datetime.now().year))
    p.add_argument("--median-stat-id", default=os.environ.get("REB_MEDIAN_STATBL_ID", ""))
    args = p.parse_args()
    key = os.environ.get("REB_API_KEY", "")
    if not key:
        p.error("REB_API_KEY 미설정. R-ONE 발급 키를 PC 환경변수 또는 GitHub Actions Secret으로 설정하세요")
    avg = to_prices(fetch_pages(key, AVERAGE_STATBL_ID, args.start, args.end), AVERAGE_STATBL_ID)
    med = {}
    median_stat_id = args.median_stat_id or find_median_table(key)
    if median_stat_id:
        med = to_prices(fetch_pages(key, median_stat_id, args.start, args.end), median_stat_id)
    else:
        print("주의: 중위가격 공식 STATBL_ID를 검증하지 못해 평균값만 갱신합니다")
    document = build_document(avg, med, median_stat_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    print(f"R-ONE JSON 갱신 완료: {len(document['rows'])}개월, 평균 {len(avg)}, 중위 {len(med)} → {args.out}")


if __name__ == "__main__":
    main()
