# Validation v1.2 — 2026-11-13 KST

- Live public Pages URL checked; repository current tree has only `data/`, `index.html`, `scripts/`. `.github/workflows` is MISSING.
- Current REB JSON: 0 months; current KB JSON: 5 reported months with one missing median, no official KB full file.
- R-ONE official API documentation checked: accepts `SttsApiTblData.do`, `CLS_ID`, `ITM_ID`, `DTACYCLE_CD` and `KEY`; missing key uses sample mode; CORS blocked. Official average table `A_2024_00060` was found on government data portal.
- Python unit and mocked integration tests: 11/11 passed.
- JavaScript syntax check: pass in Node 22.
- Browser: tested via Chromium Playwright `set_content`. KB 5 months, REB empty state, tooltips and source switching verified. `fetch()` static files were mocked from bundled JSON because this runtime blocks browser access to localhost; NOT an external browser network test.
- No external repository update / scheduled activation / paid API call performed.
- Actual authenticated REB API call NOT performed (no key). Median table identification also pending official lookup.
- Workflow configured to explicitly deploy Pages after authorized activation (GitHub Actions bot commits do not build Pages automatically).
