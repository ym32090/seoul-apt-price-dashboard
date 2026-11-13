import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update_reb import parse_page, to_prices, build_document, fetch_pages
from import_csv import validate_rows

class ToolsTests(unittest.TestCase):
    def test_official_response_price_unit_and_location(self):
        rows = [dict(STATBL_ID="A_2024_00060", CLS_ID=500008, CLS_NM="서울", ITM_ID=100001,
                     WRTTIME_IDTFR_ID=202609, DTA_VAL=1234567.5, UI_NM="천원")]
        self.assertEqual(to_prices(rows, "A_2024_00060"), {"2026-09": 123456.75})
    def test_reject_other_city(self):
        rows = [dict(STATBL_ID="A_2024_00060", CLS_ID=500001, CLS_NM="전국", ITM_ID=100001,
                     WRTTIME_IDTFR_ID=202609, DTA_VAL=120000, UI_NM="만원")]
        with self.assertRaises(ValueError): to_prices(rows, "A_2024_00060")
    def test_merge_null_median(self):
        doc=build_document({"2026-09": 120000, "2026-10": 121000}, {"2026-10": 111000})
        self.assertIsNone(doc["rows"][0]["median"])
        self.assertEqual(doc["rows"][1]["median"], 111000)
    def test_missing_key_hard_fail(self):
        with self.assertRaises(ValueError): fetch_pages("", "A_2024_00060", "2015", "2026")
    def test_sample_page_structure(self):
        meta = {"SttsApiTblData":[{"head":[{"list_total_count":1},{"RESULT":{"CODE":"INFO-000"}}]}, {"row":[{"DTA_VAL":1234}]}]}
        self.assertEqual(parse_page(meta)[0],1)
        self.assertEqual(len(parse_page(meta)[1]),1)
    def test_top_level_api_error(self):
        with self.assertRaises(RuntimeError): parse_page({"RESULT": {"CODE": "ERROR-100", "MESSAGE": "test"}})
    def test_real_official_api_shape(self):
        data = {"SttsApiTblData": [
            {"head":[{"list_total_count":1},{"RESULT":{"CODE":"INFO-000","MESSAGE":"정상 처리되었습니다."}}]},
            {"row":[{"STATBL_ID":"A_2024_00060", "DTACYCLE_CD":"MM", "WRTTIME_IDTFR_ID":"202606",
                     "CLS_ID":500008, "CLS_NM":"서울", "ITM_ID":100001, "ITM_NM":"가격",
                     "DTA_VAL":1250000, "UI_NM":"천원"}]}]}
        total, rows = parse_page(data)
        self.assertEqual(total, 1)
        self.assertEqual(to_prices(rows,"A_2024_00060"),{"2026-06":125000})
    def test_price_nan_rejected(self):
        rows = [dict(STATBL_ID="A_2024_00060", CLS_ID=500008, CLS_NM="서울", ITM_ID=100001,
                     WRTTIME_IDTFR_ID=202609, DTA_VAL='NaN', UI_NM='천원')]
        with self.assertRaises(ValueError): to_prices(rows, 'A_2024_00060')
    def test_multi_page_reb_official_api_mock(self):
        import json
        class FakeResponse:
            def __init__(self,payload): self.payload=payload
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self,*_): return json.dumps(self.payload).encode('utf-8')
        calls=[]
        def opener(req,timeout=35):
            from urllib.parse import urlparse, parse_qs
            query=parse_qs(urlparse(req.full_url).query)
            calls.append(query)
            n=int(query['pIndex'][0])
            row=dict(STATBL_ID='A_2024_00060', CLS_ID=500008, CLS_NM='서울', ITM_ID=100001,
                     WRTTIME_IDTFR_ID=str(202600+n).replace('00','00'), DTA_VAL=1200000+n*10000, UI_NM='천원')
            row['WRTTIME_IDTFR_ID']='20260'+str(n)
            return FakeResponse({'SttsApiTblData':[{'head':[{'list_total_count':2},{'RESULT':{'CODE':'INFO-000'}}]},{'row':[row]}]})
        rows=fetch_pages('PRIVATE_TEST_KEY','A_2024_00060','2026','2026',page_size=1,opener=opener)
        self.assertEqual(len(rows),2)
        self.assertEqual(len(calls),2)
        self.assertEqual(to_prices(rows,'A_2024_00060'),{'2026-01':121000,'2026-02':122000})
    def test_csv_duplicate_rejected(self):
        data=[{"month":"2026-01","avg":"120000","median":""}, {"month":"2026-01","avg":"123000","median":""}]
        with self.assertRaises(ValueError): validate_rows(data)
    def test_csv_valid_rows(self):
        rows=validate_rows([{"month":"2026-01","region":"서울","avg":"120000","median":"110000"}])
        self.assertEqual(rows['2026-01']['median'],110000)

if __name__=='__main__': unittest.main()
