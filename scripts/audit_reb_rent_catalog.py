#!/usr/bin/env python3
"""R-ONE survey-based Seoul apartment rental price catalog audit (READ ONLY).

Only R-ONE's authenticated official API is queried. No files in the repository,
prices, raw URLs, or credentials are changed or printed. The GitHub summary is
optional output. This does not import any KB data or run KB network requests.
"""
from __future__ import annotations

from collections import Counter
import http.client
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = 'https://www.reb.or.kr/r-one/openapi/'
SALE_ANCHORS = ('A_2024_00060', 'A_2024_00062')
CANDIDATE_LIMIT = 12
NETWORK_ERRORS = (http.client.RemoteDisconnected, urllib.error.URLError,
                  ConnectionError, TimeoutError, OSError, ssl.SSLError, socket.timeout)


def safe(value, max_len=88):
    return re.sub(r'[^\w가-힣 .,/()\-]', '_', str(value or '-'))[:max_len]


def month(value):
    m = str(value or '')
    return m[:4] + '-' + m[4:] if re.fullmatch(r'\d{6}', m) and 1 <= int(m[4:]) <= 12 else None


def response_unpack(value, service):
    if not isinstance(value, dict):
        return dict(status='BAD_SHAPE', total=None, rows=[])
    if isinstance(value.get('RESULT'), dict):
        return dict(status=safe(value['RESULT'].get('CODE')), total=None, rows=[])
    blocks = value.get(service)
    if not isinstance(blocks, list):
        return dict(status='MISSING_BLOCK', total=None, rows=[])
    result = dict(status='INFO-000', total=None, rows=[])
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for h in b.get('head', []):
            if isinstance(h, dict):
                if 'list_total_count' in h:
                    try:
                        result['total'] = int(h['list_total_count'])
                    except (TypeError, ValueError):
                        pass
                if isinstance(h.get('RESULT'), dict):
                    result['status'] = safe(h['RESULT'].get('CODE'))
        result['rows'] += [x for x in b.get('row', []) if isinstance(x, dict)]
    return result


def request(api_key, service, params, opener=None):
    if not api_key or not api_key.strip():
        return dict(status='KEY_MISSING', total=None, rows=[])
    if service not in ('SttsApiTbl', 'SttsApiTblData'):
        raise ValueError('SERVICE_NOT_ALLOWED')
    args = {'KEY': api_key, 'Type': 'json', 'pIndex': 1, 'pSize': 200}
    args.update(params)
    req = urllib.request.Request(ROOT + service + '.do?' + urllib.parse.urlencode(args),
         headers={'Accept':'application/json', 'User-Agent':'SeoulAptRentalReadOnlyAudit/1.0'})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=25) as response:
            content = json.load(response)
    except urllib.error.HTTPError as exc:
        return dict(status='HTTP_' + str(exc.code), total=None, rows=[])
    except NETWORK_ERRORS as exc:
        return dict(status='TRANSPORT_' + type(exc).__name__, total=None, rows=[])
    except (ValueError, UnicodeError, TypeError):
        return dict(status='INVALID_JSON', total=None, rows=[])
    return response_unpack(content, service)


def full_catalog(api_key, requester=request, sleeper=time.sleep):
    """Fetch all catalog pages; partial/repeated pages do not imply absence."""
    rows, total, seen = [], None, set()
    for page in range(1, 16):
        result = requester(api_key, 'SttsApiTbl', {'pIndex': page, 'pSize': 200})
        if result['status'] != 'INFO-000':
            return dict(status=result['status'], total=total, rows=rows, complete=False)
        if total is None:
            total = result['total']
        if total is None or not result['rows']:
            return dict(status='CATALOG_MISSING_ROWS', total=total, rows=rows, complete=False)
        sig = tuple(str(r.get('STATBL_ID', '')) for r in result['rows'])
        if sig in seen:
            return dict(status='REPEATED_CATALOG_PAGE', total=total, rows=rows, complete=False)
        seen.add(sig)
        rows.extend(result['rows'])
        if len(rows) >= total:
            ids = [str(r.get('STATBL_ID', '')) for r in rows]
            if len(rows) != total or len(set(ids)) != len(ids):
                return dict(status='CATALOG_COUNT_OR_ID_MISMATCH', total=total, rows=rows, complete=False)
            return dict(status='INFO-000', total=total, rows=rows, complete=True)
        sleeper(0.25)
    return dict(status='CATALOG_PAGE_LIMIT', total=total, rows=rows, complete=False)


def rental_candidates(catalog_rows):
    anchors = [r for r in catalog_rows if str(r.get('STATBL_ID')) in SALE_ANCHORS]
    survey_stats = {str(r.get('STAT_ID')) for r in anchors if r.get('STAT_ID')}
    matches = []
    for row in catalog_rows:
        name = str(row.get('STATBL_NM', '')).replace(' ', '')
        cycle = str(row.get('DTACYCLE_CD','')).split(',')
        if 'MM' not in cycle or '전세' not in name or not ('평균' in name or '중위' in name):
            continue
        matches.append(dict(id=str(row.get('STATBL_ID', '')), name=str(row.get('STATBL_NM', '')),
                            stat_id=str(row.get('STAT_ID', '')),
                            same_survey=bool(survey_stats and str(row.get('STAT_ID', '')) in survey_stats),
                            actual_apartment='아파트' in name,
                            distinct_family='실거래' in name or '면적' in name or '㎡' in name))
    matches.sort(key=lambda x: (not x['same_survey'], not x['actual_apartment'], x['distinct_family'], x['id']))
    return matches, survey_stats


def summarize_sample(raw, stat_id):
    rows = [r for r in raw['rows'] if str(r.get('STATBL_ID', '')) == stat_id]
    # Data value is intentionally NEVER accessed.
    group = Counter((str(r.get('CLS_ID', '')), str(r.get('CLS_NM', '')),
                     str(r.get('ITM_ID', '')), str(r.get('ITM_NM', '')),
                     str(r.get('UI_NM', ''))) for r in rows)
    seoul = [(cls, name, item, itemname, unit, count) for (cls, name, item, itemname, unit), count
             in group.items() if name.strip() in ('서울','서울특별시')]
    names = [(cls, name, item, itemname, unit, count) for (cls, name, item, itemname, unit), count
             in group.items() if cls == '500008']
    months = sorted({m for r in rows if (m := month(r.get('WRTTIME_IDTFR_ID')))}, reverse=True)
    return dict(sample=len(rows), total=raw['total'], partial=raw['total'] is not None and len(raw['rows']) < raw['total'],
                seoul=sorted(seoul)[:8], code500008=sorted(names)[:8], months=months[:2],
                combinations=len(group))


def audit(api_key, requester=request, sleeper=time.sleep):
    catalog = full_catalog(api_key, requester, sleeper)
    output = ['# R-ONE rental catalog: read-only survey vs transaction audit',
              'No KB calls, no changed files, no published prices, no raw request URLs or secrets.',
              f"CATALOG status={safe(catalog['status'])} loaded={len(catalog['rows'])} total={catalog['total']} complete={catalog['complete']}", '']
    if not catalog['complete']:
        output.append('INCONCLUSIVE: full official catalog not retrieved; no candidate exclusion is valid.')
        return '\n'.join(output)+'\n'
    matches, survey_stats = rental_candidates(catalog['rows'])
    output.append('Sale anchor STAT_ID(s): '+(','.join(sorted(safe(x) for x in survey_stats)) or 'NOT_FOUND'))
    output.append('Monthly rent price catalog candidates: '+str(len(matches)))
    for m in matches:
        output.append('CAT '+safe(m['id'])+' | '+safe(m['name'])+' | STAT_ID='+safe(m['stat_id'])+
                      ' | same_survey='+str(m['same_survey'])+' | apartment_in_title='+str(m['actual_apartment'])+
                      ' | distinct_type_hint='+str(m['distinct_family']))
    output.append('')
    # Probe only same-survey candidates; no automatic choice or publication.
    eligible = [m for m in matches if m['same_survey'] and not m['distinct_family']][:CANDIDATE_LIMIT]
    output.append('Probing same-survey candidates only: '+str(len(eligible)))
    for item in eligible:
        for suffix, filters in [('unfiltered',{}),('code500008',{'CLS_ID':'500008'})]:
            opts={'STATBL_ID':item['id'],'DTACYCLE_CD':'MM',
                  'START_WRTTIME':'2025', 'END_WRTTIME':'2027', 'pSize':200}
            opts.update(filters)
            res = requester(api_key,'SttsApiTblData',opts)
            summary = summarize_sample(res,item['id'])
            output.append('PROBE '+safe(item['id'])+' '+suffix+' status='+safe(res['status'])+
                          ' total='+str(res['total'])+' sampled='+str(summary['sample'])+
                          ' partial='+str(summary['partial'])+' seoul='+safe(summary['seoul'])+
                          ' code500008='+safe(summary['code500008'])+' latest_months='+str(summary['months']))
            sleeper(.25)
    output += ['', 'DECISION: no automatic rental connection; authenticate Seoul region, metric, unit and',
               'monthly coverage using full official response before changing the dashboard.',
               'Surveys and contract-based rent averages must never be mixed.']
    return '\n'.join(output)+'\n'


def main():
    key=os.getenv('REB_API_KEY','').strip()
    if not key:
        raise SystemExit('REB_API_KEY is required only in private GitHub Actions Secret')
    report=audit(key)
    print(report)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as fp:
            fp.write(report)

if __name__ == '__main__':
    main()
