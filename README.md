# Seoul Apartment Price Dashboard v1.2

Dashboard for **Seoul-wide apartment sale average and median prices**, with month range controls, source selection, hover/touch tooltips, percent change, CSV/XLSX import, and explicit last-published-data reload.

## Most important

- **Live site already exists:** https://ym32090.github.io/seoul-apt-price-dashboard/
- **Current real data:** KB secondary-reported values for 2026-06 through 2026-10, **not yet verified against the KB original bulk file**.
- **Current official REB history:** `data/reb.json` is **0 rows**, because no R-ONE API key has been validated in the repo.
- **Historical data is not invented.** REB/KB months are not marked synchronized until official fetching succeeds.
- **RECOMMENDED NEXT STEPS:** Read `LIVE_SETUP.md` for exact GitHub UI and safe official API automation setup.
- **Repository external writes / schedule enabling:** NOT performed here. User approves and applies those steps.

## Data source policy

REB (`data/reb.json`): monthly surveyed prices, source https://www.reb.or.kr/r-one/portal/stat/easyStatPage/A_2024_00060.do . Official average table ID confirmed. Monthly median table ID requires **independent official confirmation**; `scripts/update_reb.py` attempts a cautious lookup and never fabricates it.

KB (`data/kb.json`): official datahub https://data.kbland.kr/ . No verified public API for automatic long-form average/median available in the current investigation. Can import authorized CSV/XLSX manually into browser or into the JSON using `scripts/import_csv.py`.

MOLIT transaction records are not comparable directly with institutionally surveyed average/median prices (different transaction mix); Naver is not connected through undocumented scraping endpoints.

## Running locally

Python 3.9+ standard library only, no packages required:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/` with a browser. Double-clicking HTML under `file://` may not load `data/*.json`, although built-in five KB points still render.

## Unit tests

```bash
python -m unittest discover -s tests -v
```

Do not put credentials in HTML, JSON, CSV, README, GitHub issues, or screenshots. Store only as GitHub Repository Secret `REB_API_KEY`.

## Deployment architecture

`GitHub Actions` (scheduled 15–25th, 16:40 KST; plus manual) -> official R-ONE API with secret -> validate region, item, unit, date and full page count -> write `data/reb.json` -> commit changes -> **explicitly upload/deploy Pages artifact**. Bot commits using `GITHUB_TOKEN` alone do not trigger a Pages branch build. Existing Pages Source `Deploy from branch -> main / root` may be retained; the explicit Pages deployment uses the main source branch. See https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## Key files

- `index.html`: browser application, all filenames English.
- `data/reb.json`: official authenticated REB series once added.
- `data/kb.json`: KB provisional reference data.
- `scripts/update_reb.py`: R-ONE importer with strict checks and no secret logging.
- `scripts/import_csv.py`: import an authorized CSV into public JSON (you must commit resulting JSON to publish).
- `.github/workflows/refresh-reb.yml`: scheduled/manual, safe update and explicit deployment. Hidden `.github` path must exist in GitHub repository.
- `LIVE_SETUP.md`: actions and GitHub UI instructions.
- `VALIDATION.md`: status of tested vs not tested.

Official average/median price observations are not a robust house price appreciation index: sample design and composition vary. If analyzing investment returns, use a standardized sale-price index separately.
