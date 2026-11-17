#!/usr/bin/env python3
"""Read-only R-ONE audit: inspect exact tables and year boundaries safely.

No repository/data writes (except optional GitHub Actions step-summary), no raw
prices, no request URLs or API keys printed. Does NOT update dashboard data.
Run only through existing manual-only read-only audit workflow.
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

BASE = 'https://www.reb.or.kr/r-one/openapi/'
TABLES = (
    ('SALE_AVG_SURVEY', 'A_2024_00060', 'sale'),
    ('SALE_MEDIAN_SURVEY', 'A_2024_00062', 'sale'),
    # DIFFERENT statistical family: rental transaction/contract-based average,
    # not validated as equivalent to REB surveyed monthly rental price.
    ('RENT_AVG_DIFFERENT_SERIES_CANDIDATE', 'A_2024_00192', 'rent_other'),
)
NETWORK_ERRORS = (http.client.RemoteDisconnected, ConnectionResetError,
                  ConnectionAbortedError, BrokenPipeError,
                  urllib.error.URLError, TimeoutError, socket.timeout,
                  ssl.SSLError, OSError)
SAFE_CODE = re.compile(r'^[A-Za-z0-9_.-]{1,48}$')
VALID_MONTH = re.compile(r'^\d{6}$')


def token(value):
    v = str(value if value is not None else 'none')
    return v if SAFE_CODE.fullmatch(v) else 'UNKNOWN'


def unwrap(payload, service):
    if not isinstance(payload, dict):
        return {'status':'BAD_JSON_SHAPE', 'total':None, 'rows':[]}
    if isinstance(payload.get('RESULT'), dict):
        return {'status':token(payload['RESULT'].get('CODE')),
                'total':None, 'rows':[]}
    blocks = payload.get(service)
    if not isinstance(blocks, list):
        return {'status':'SERVICE_ARRAY_MISSING', 'total':None, 'rows':[]}
    total, rows, status = None, [], 'INFO-000'
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for head in block.get('head', []):
            if not isinstance(head, dict):
                continue
            if 'list_total_count' in head:
                try: total=int(head['list_total_count'])
                except (TypeError,ValueError): pass
            if isinstance(head.get('RESULT'), dict):
                status=token(head['RESULT'].get('CODE'))
        rows += [r for r in block.get('row', []) if isinstance(r, dict)]
    return {'status':status, 'total':total, 'rows':rows}


def fetch(api_key, service, parameters, opener=None, timeout=20):
    """Low-impact single-page request; catches errors without leaking KEY/URL."""
    if not api_key or not api_key.strip():
        return {'status':'KEY_MISSING','total':None,'rows':[]}
    if service not in ('SttsApiTbl','SttsApiTblData'):
        raise ValueError('Service not allowlisted')
    query={'KEY':api_key,'Type':'json','pIndex':1,'pSize':1000}
    query.update(parameters)
    url=BASE+service+'.do?'+urllib.parse.urlencode(query)
    req=urllib.request.Request(url,headers={
        'Accept':'application/json', 'User-Agent':'SeoulAptDashboardAudit/1.8.4'})
    fn=opener or urllib.request.urlopen
    try:
        with fn(req,timeout=timeout) as response:
            data=json.load(response)
    except urllib.error.HTTPError as e:
        return {'status':'HTTP_'+str(e.code),'total':None,'rows':[]}
    except NETWORK_ERRORS as e:
        return {'status':'TRANSPORT_'+type(e).__name__, 'total':None,'rows':[]}
    except (ValueError,UnicodeError,TypeError):
        return {'status':'INVALID_JSON','total':None,'rows':[]}
    return unwrap(data,service)


def scrutinize(result, stat_id, kind):
    """Read metadata, not prices. A page is partial if total>len(rows)."""
    region_item=[]
    all_months=set()
    counts=Counter()
    names=Counter()
    units=Counter()
    for row in result['rows']:
        if str(row.get('STATBL_ID')) != stat_id:
            counts['wrong_table']+=1
            continue
        ym=str(row.get('WRTTIME_IDTFR_ID',''))
        if VALID_MONTH.fullmatch(ym) and 1<=int(ym[4:])<=12:
            all_months.add(ym[:4]+'-'+ym[4:])
        else:
            counts['bad_date']+=1
        cls=str(row.get('CLS_ID',''))
        itm=str(row.get('ITM_ID',''))
        name=str(row.get('CLS_NM',''))
        unit=str(row.get('UI_NM','')).replace(' ','')
        names[(cls,name)]+=1
        units[unit]+=1
        if cls=='500008' and name in ('서울','서울특별시') and itm=='100001' and ym.isdigit() and len(ym)==6:
            region_item.append(ym[:4]+'-'+ym[4:])
    matched=sorted(set(region_item))
    result={'matched':matched, 'all':sorted(all_months),
            'region_codes':[(k[0],k[1],v) for k,v in names.most_common(4)],
            'units':units.most_common(4),
            'other_table_rows':counts['wrong_table'],
            'partial':result['total'] is not None and len(result['rows'])<result['total']}
    return result


def exact_catalog_line(response, stat_id):
    rows=[r for r in response['rows'] if str(r.get('STATBL_ID'))==stat_id]
    if not rows:
        return 'exact_id=not_returned;catalog_status='+token(response['status'])
    r=rows[0]
    title=str(r.get('STATBL_NM',''))
    return ('exact_id=yes;cycle='+token(r.get('DTACYCLE_CD'))+
            ';end_hint='+token(r.get('DATA_END_YY'))+
            ';has_sale='+str('매매' in title)+
            ';has_rent='+str('전세' in title)+
            ';has_median='+str('중위' in title)+
            ';has_avg='+str('평균' in title))


def make_audit(api_key, requester=fetch, sleeper=time.sleep):
    out=['# R-ONE monthly prices: evidence-only audit v1.8.4',
         'No repository/data file update, no deployments, no raw values/URLs/keys.',
         'Read-only queries; statistics are NOT mixed across survey/transaction types.', '']
    outcomes=[]
    for label,stat_id,kind in TABLES:
        out.append('## '+label+' / '+stat_id)
        meta=requester(api_key,'SttsApiTbl',{'STATBL_ID':stat_id,'pSize':10})
        out.append('CATALOG: '+exact_catalog_line(meta,stat_id))
        sleeper(.2)
        # Equal-year queries are intentionally absent: prior INFO-200 from
        # 2025..2025 was inconclusive, whereas 2000..2026 yielded 2025 rows.
        ranges=(('BASE_2000_2026','2000','2026'),
                ('PLUS_2000_2027','2000','2027'),
                ('WINDOW_2025_2027','2025','2027')) if kind=='sale' else (
                ('RENT_CANDIDATE_2014_2027','2014','2027'),)
        local=[]
        for description,start,end in ranges:
            params={'STATBL_ID':stat_id,'DTACYCLE_CD':'MM',
                    'CLS_ID':'500008','ITM_ID':'100001',
                    'START_WRTTIME':start,'END_WRTTIME':end}
            resp=requester(api_key,'SttsApiTblData',params)
            details=scrutinize(resp,stat_id,kind)
            months=details['matched']
            code=token(resp['status'])
            local.append((description,code,set(months),details))
            first=months[0] if months else '-'
            last=months[-1] if months else '-'
            out.append(f'{description}: status={code} total={resp["total"]} sample={len(resp["rows"])} '
                       f'seoul_valid={len(months)} y2025={sum(m.startswith("2025-") for m in months)} '
                       f'y2026={sum(m.startswith("2026-") for m in months)} first={first} last={last} '
                       f'partial_page={details["partial"]}')
            if code=='INFO-000' and resp['rows'] and not months:
                out.append('  REGION_ITEM_NEEDS_REVIEW: '+str(details['region_codes'][:3]))
            if code=='INFO-000' and resp['rows']:
                out.append('  UNIT_CODES: '+str(details['units'][:3]))
            outcomes.append((label,description,code,months,details))
            sleeper(.2)
        if kind=='sale' and len(local)>=2:
            a,b=local[0:2]
            if a[1]=='INFO-000' and b[1]=='INFO-000' and not a[3]['partial'] and not b[3]['partial']:
                before={m for m in a[2] if m.startswith('2026-')}
                after={m for m in b[2] if m.startswith('2026-')}
                out.append('END_BOUNDARY_COMPARISON: '+('2026_added_with_2027_end' if not before and after
                           else 'no_new_2026_months' if before==after else 'other_difference'))
            else: out.append('END_BOUNDARY_COMPARISON: inconclusive_partial_or_transport')
        if kind=='rent_other':
            out.append('WARNING: Candidate is region-based rent average, likely DIFFERENT statistic '
                       'from nationwide surveyed per-home rent; do not publish as surveyed rent.')
        out.append('')
    sale_found=any(label.startswith('SALE') and any(m.startswith('2026-') for m in months)
                   for label,_,code,months,details in outcomes if code=='INFO-000' and not details['partial'])
    all_sale_complete=all(any(label==target and desc=='PLUS_2000_2027' and code=='INFO-000'
                              and not details['partial'] for label,desc,code,_,details in outcomes)
                          for target in ('SALE_AVG_SURVEY','SALE_MEDIAN_SURVEY'))
    if sale_found:status='2026_SALE_OBSERVATIONS_PRESENT_REVIEW_UNITS'
    elif all_sale_complete:status='NO_2026_IN_TWO_COMPLETE_PLUS_ONE_QUERIES'
    else:status='INCONCLUSIVE_API_OR_TRANSPORT_OR_PARTIAL'
    out.insert(3,'AUDIT_STATUS: '+status)
    out += ['Interpretation:',
            '- A successful workflow is not the same as validated new observations.',
            '- INFO-200 means empty result for those filters, NOT a universal absence.',
            '- total>sample means page was truncated: do NOT infer latest month.',
            '- Catalog DATA_END_YY may lag the actual observations.',
            '- Survey vs transaction-based rent prices must stay separate.',
            '- Never change operating collector until an authenticated response confirms IDs, CLS/ITM, units and months.']
    return '\n'.join(out)+'\n'


def main():
    key=os.getenv('REB_API_KEY','').strip()
    if not key:
        raise SystemExit('Existing REB_API_KEY GitHub Secret is missing')
    output=make_audit(key)
    print(output)
    path=os.getenv('GITHUB_STEP_SUMMARY')
    if path:
        with open(path,'a',encoding='utf-8') as f:
            f.write(output)


if __name__=='__main__':
    main()
