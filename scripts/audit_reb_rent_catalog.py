#!/usr/bin/env python3
"""R-ONE Seoul apartment surveyed rent-price final verification (READ ONLY).

v1.8.8: validate confirmed official tables A_2024_00064 (mean) and
A_2024_00066 (median) against sale anchor A_2024_00060. Query only R-ONE.
Do not write price data, modify the repository, publish, contact KB,
print request URLs/API secrets, or infer that a partial response is complete.
Existing manual-only audit-reb-rent-catalog.yml can invoke this file unchanged.
"""
from __future__ import annotations

from collections import Counter
import http.client
import json
import math
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://www.reb.or.kr/r-one/openapi/'
ANCHOR = 'A_2024_00060'
RENT_TABLES = (('RENT_AVG', 'A_2024_00064'), ('RENT_MEDIAN', 'A_2024_00066'))
EXPECTED_STAT_ID = 'S234820263'  # previously verified from full 769-row catalog
SEOUL = '500008'
PRICE_ITEM = '100001'
MAX_PAGES = 8
NETWORK_ERRORS = (http.client.RemoteDisconnected, urllib.error.URLError,
                  ConnectionError, TimeoutError, OSError, ssl.SSLError, socket.timeout)


def request(key, service, query, opener=None, sleeper=time.sleep):
    """Read-only GET, one bounded retry for transient transport errors only."""
    if not key or not key.strip():
        return {'status': 'KEY_MISSING', 'total': None, 'rows': []}
    if service not in ('SttsApiTbl', 'SttsApiTblData'):
        raise ValueError('SERVICE_NOT_ALLOWED')
    params = {'KEY': key, 'Type': 'json', 'pIndex': 1, 'pSize': 300}
    params.update(query)
    req = urllib.request.Request(BASE + service + '.do?' + urllib.parse.urlencode(params),
        headers={'Accept': 'application/json', 'User-Agent': 'SeoulAptReadOnlyAudit/1.8.8'})
    for attempt in range(2):
        try:
            with (opener or urllib.request.urlopen)(req, timeout=25) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as err:
            return {'status': 'HTTP_' + str(err.code), 'total': None, 'rows': []}
        except NETWORK_ERRORS as err:
            if attempt == 0:
                sleeper(1.0)
                continue
            return {'status': 'TRANSPORT_' + type(err).__name__, 'total': None, 'rows': []}
        except (ValueError, UnicodeError, TypeError):
            return {'status': 'INVALID_JSON', 'total': None, 'rows': []}
        if not isinstance(payload, dict):
            return {'status': 'INVALID_BODY', 'total': None, 'rows': []}
        if isinstance(payload.get('RESULT'), dict):
            code = str(payload['RESULT'].get('CODE', 'API_ERROR'))
            return {'status': code[:40], 'total': None, 'rows': []}
        blocks = payload.get(service)
        if not isinstance(blocks, list):
            return {'status': 'MISSING_SERVICE', 'total': None, 'rows': []}
        total, rows, status = None, [], 'INFO-000'
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for h in block.get('head', []):
                if isinstance(h, dict):
                    if 'list_total_count' in h:
                        try:
                            total = int(h['list_total_count'])
                        except (ValueError, TypeError):
                            pass
                    if isinstance(h.get('RESULT'), dict):
                        status = str(h['RESULT'].get('CODE', 'UNKNOWN'))[:40]
            rows.extend(r for r in block.get('row', []) if isinstance(r, dict))
        return {'status': status, 'total': total, 'rows': rows}
    raise AssertionError('unreachable')


def exact_metadata(key, table, requester=request):
    reply = requester(key, 'SttsApiTbl', {'STATBL_ID': table, 'pSize': 10})
    rows = [r for r in reply['rows'] if str(r.get('STATBL_ID')) == table]
    if reply['status'] != 'INFO-000' or len(rows) != 1:
        return {'ok': False, 'reason': reply['status'] if reply['status'] != 'INFO-000' else 'EXACT_TABLE_NOT_UNIQUE'}
    row = rows[0]
    return {'ok': True, 'stat_id': str(row.get('STAT_ID', '')),
            'title': str(row.get('STATBL_NM', '')),
            'cycle': str(row.get('DTACYCLE_CD', '')),
            'start_hint': str(row.get('DATA_START_YY', '')),
            'end_hint': str(row.get('DATA_END_YY', ''))}


def full_series(key, table, requester=request, sleeper=time.sleep):
    """Fetch all pages for 2000..2027, with strict completeness checks."""
    rows, total, signatures = [], None, set()
    for page in range(1, MAX_PAGES + 1):
        r = requester(key, 'SttsApiTblData', {
            'STATBL_ID': table, 'DTACYCLE_CD': 'MM',
            'CLS_ID': SEOUL, 'ITM_ID': PRICE_ITEM,
            'START_WRTTIME': '2000', 'END_WRTTIME': '2027',
            'pIndex': page, 'pSize': 300})
        if r['status'] != 'INFO-000':
            return {'complete': False, 'reason': r['status'], 'rows': rows, 'total': total}
        if total is None:
            total = r['total']
        if total is None or r['total'] != total or total <= 0 or not r['rows']:
            return {'complete': False, 'reason': 'COUNT_OR_PAGE_INVALID', 'rows': rows, 'total': total}
        signature = tuple((str(x.get('WRTTIME_IDTFR_ID')), str(x.get('CLS_ID')),
                           str(x.get('ITM_ID'))) for x in r['rows'])
        if signature in signatures:
            return {'complete': False, 'reason': 'REPEATED_PAGE', 'rows': rows, 'total': total}
        signatures.add(signature)
        rows.extend(r['rows'])
        if len(rows) == total:
            return {'complete': True, 'reason': 'INFO-000', 'rows': rows, 'total': total}
        if len(rows) > total:
            return {'complete': False, 'reason': 'TOTAL_OVERFLOW', 'rows': rows, 'total': total}
        sleeper(0.65)
    return {'complete': False, 'reason': 'PAGE_LIMIT', 'rows': rows, 'total': total}


def month_number(raw):
    m = str(raw or '')
    if re.fullmatch(r'\d{6}', m) and 1 <= int(m[4:]) <= 12:
        return int(m[:4]) * 12 + int(m[4:]) - 1
    return None


def month_str(n):
    return f'{n // 12:04d}-{n % 12 + 1:02d}'


def validate_series(data, table):
    """Validate metadata/values without returning or displaying prices."""
    errors = Counter()
    stamps = set()
    fields = Counter()
    for r in data['rows']:
        fields[(str(r.get('CLS_ID')), str(r.get('CLS_NM')),
                str(r.get('ITM_ID')), str(r.get('ITM_NM')), str(r.get('UI_NM')))] += 1
        if str(r.get('STATBL_ID')) != table:
            errors['FOREIGN_TABLE'] += 1
        if (str(r.get('CLS_ID')) != SEOUL or
            str(r.get('CLS_NM', '')).strip() not in ('서울', '서울특별시')):
            errors['NOT_SEOUL'] += 1
        if str(r.get('ITM_ID')) != PRICE_ITEM or str(r.get('ITM_NM', '')).strip() != '가격':
            errors['NOT_PRICE_ITEM'] += 1
        if str(r.get('UI_NM', '')).replace(' ', '') != '천원':
            errors['NOT_KRW_THOUSAND'] += 1
        m = month_number(r.get('WRTTIME_IDTFR_ID'))
        if m is None:
            errors['INVALID_MONTH'] += 1
        elif m in stamps:
            errors['DUPLICATE_MONTH'] += 1
        else:
            stamps.add(m)
        try:
            price = float(str(r.get('DTA_VAL', '')).replace(',', '').strip())
            if not math.isfinite(price) or not 10000 <= price / 10 <= 1000000:
                errors['PRICE_OUT_OF_RANGE'] += 1
        except (ValueError, TypeError):
            errors['PRICE_NOT_NUMERIC'] += 1
    if not stamps:
        errors['NO_MONTHS'] += 1
    else:
        missing = set(range(min(stamps), max(stamps) + 1)) - stamps
        if missing:
            errors['MISSING_MONTHS'] += len(missing)
    if not data['complete']:
        errors['PARTIAL_PAGE'] += 1
    months = sorted(stamps)
    return {'valid': not bool(errors), 'errors': dict(errors),
            'count': len(stamps), 'total': data['total'],
            'first': month_str(months[0]) if months else 'none',
            'last': month_str(months[-1]) if months else 'none',
            'y2026': sum(1 for m in stamps if m//12 == 2026),
            'months': stamps, 'field_groups': fields.most_common(5)}


def audit(key, requester=request, sleeper=time.sleep):
    out = ['# R-ONE v1.8.8 exact Seoul surveyed-rent final audit (READ ONLY)',
           'No data files, GitHub commits, Pages deployments, KB requests or secret/price output.', '']
    anchor = exact_metadata(key, ANCHOR, requester)
    out.append('SALE_ANCHOR exact=' + str(anchor['ok']) +
               ' STAT_ID=' + (anchor.get('stat_id') if anchor['ok'] else anchor['reason']))
    results = []
    for label, table in RENT_TABLES:
        metadata = exact_metadata(key, table, requester)
        out.append('')
        out.append(f'## {label} / {table}')
        if not metadata['ok']:
            out.append('METADATA_FAILED: ' + metadata['reason'])
            results.append(None)
            continue
        same_survey = anchor['ok'] and metadata['stat_id'] == anchor['stat_id'] == EXPECTED_STAT_ID
        title = metadata['title'].replace(' ', '')
        expected_word = '평균전세가격_아파트' if label == 'RENT_AVG' else '중위전세가격_아파트'
        title_ok = expected_word in title and '단위' not in title
        cycle_ok = metadata['cycle'] == 'MM'
        out.append(f"METADATA: title={metadata['title']} STAT_ID={metadata['stat_id']} "
                   f"same_survey={same_survey} monthly={cycle_ok} expected_title={title_ok} "
                   f"start_hint={metadata['start_hint']} end_hint={metadata['end_hint']}")
        data = full_series(key, table, requester, sleeper)
        check = validate_series(data, table)
        out.append(f"DATA: status={data['reason']} complete={data['complete']} "
                   f"returned={len(data['rows'])} total={data['total']} "
                   f"unique_months={check['count']} first={check['first']} last={check['last']} "
                   f"y2026={check['y2026']} month_continuity={'MISSING_MONTHS' not in check['errors']}")
        out.append('FIELDS: ' + repr(check['field_groups']))
        out.append('VALIDATION_ERRORS: ' + repr(check['errors']))
        results.append((same_survey and title_ok and cycle_ok and check['valid'], check))
        sleeper(0.65)
    if (len(results) == 2 and all(r is not None and r[0] for r in results)
        and results[0][1]['months'] == results[1][1]['months']):
        out.append('\nRESULT: FULL_HISTORY_VALIDATED_FOR_FUTURE_INTEGRATION')
        out.append('Both surveyed rent prices have the same Seoul calendar; prices were validated but not published.')
    else:
        out.append('\nRESULT: INCONCLUSIVE_OR_MISMATCH; DO_NOT_IMPORT')
    out.append('No rent price JSON or dashboard UI is changed by this audit.')
    return '\n'.join(out) + '\n'


def main():
    key = os.getenv('REB_API_KEY', '').strip()
    if not key:
        raise SystemExit('Missing private REB_API_KEY GitHub Actions Secret')
    report = audit(key)
    print(report)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(report)


if __name__ == '__main__':
    main()
