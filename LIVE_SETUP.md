# Live data activation for ym32090/seoul-apt-price-dashboard

Current observation on 2026-11-13: `main` contains `index.html`, `data/` and `scripts/` only. There is NO `.github/workflows/` directory. `data/reb.json` has zero rows. No REB API key has been verified.

## Objective
Monthly official release -> GitHub Actions refresh -> commit validated `data/reb.json` -> the same workflow **explicitly deploys GitHub Pages**. The GitHub Pages configuration can remain at `main / root`; a `GITHUB_TOKEN` push does **not** trigger Pages by itself. Not a real-time trade ticker. Public website NEVER contains the API key.

## Steps in GitHub UI

1. Open https://github.com/ym32090/seoul-apt-price-dashboard and use `Add file` > `Upload files` to replace `index.html`, `scripts/update_reb.py`, plus `tests/test_tools.py` if desired. The package root contains updated files. **Do not upload ZIP itself**.
2. Create the hidden workflow directory explicitly: **Code > Add file > Create new file**. In `Name your file...` enter `.github/workflows/refresh-reb.yml`. GitHub will create the directory levels as you enter slashes. Copy the contents of the file of the same name from this package, then **Commit changes** to `main`. (Using GitHub Desktop or git push also preserves hidden directories.)
3. Obtain your free API key from R-ONE Open API: https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do . Log in, request a key and confirm that the key is issued/usable. Do not paste the key into ChatGPT, public GitHub files, `index.html` or screenshots.
4. In the repository: **Settings > Secrets and variables > Actions > Secrets > New repository secret**. Name=`REB_API_KEY`; Secret=your actual key; **Add secret**.
5. If R-ONE's official catalog/code search confirms a unique monthly *Seoul apartment sale median* statistical table, configure `Settings > Secrets and variables > Actions > Variables > New repository variable` with Name=`REB_MEDIAN_STATBL_ID` and Value=verified `A_...` code. Without that ID, the script attempts official catalog discovery, but may publish **average only** if unresolved. Never invent a median table ID.
6. Verify **Settings > Actions > General > Workflow permissions** allow the bot to commit to `main` (read/write repository permissions if available). Do not disable branch protections to work around failures.
7. Keep **Settings > Pages > Build and deployment > Source = Deploy from a branch, Branch = main / (root)**. DO NOT switch to GitHub Actions; `GITHUB_TOKEN` commits do not trigger the existing branch build, so `refresh-reb.yml` explicitly deploys the updated static site.
8. Open **Actions** tab, select `Refresh official REB price series`, click **Run workflow**, branch=`main`, then **Run workflow**. Inspect every step. Successful `Fetch validated official R-ONE statistics` and commit are required for actual data integration.
9. Verify the workflow finishes **Publish** / **Deploy Pages** successfully. GitHub documentation says a GitHub Actions `GITHUB_TOKEN` commit does not automatically trigger a branch Pages rebuild, so the workflow explicitly uploads and deploys the site artifact. Verify `data/reb.json` has `rows` with positive count and `verification` marked with official authentication. Inspect the live website; use the `게시된 최신 데이터 다시 확인` button and select `한국부동산원`. If 0 rows remain, do not claim success.

## Automation
Schedule at 16:40 Korea time on the 15th–25th of every month, plus manual dispatch. GitHub scheduled workflows may be delayed and can be disabled by GitHub after prolonged inactivity. A run finding no new data should leave `reb.json` and Git history unchanged. The user must approve enabling external repository operations; this package only prepares the workflow.

## Diagnostics
- If Actions cannot find the workflow, verify `.github/workflows/refresh-reb.yml` exists on the default branch and YAML is syntactically correct.
- If `REB_API_KEY` is empty or invalid, use Secrets to check the key. **Never copy/paste the secret into an issue or log.**
- If API returns 5 samples, key authentication/pagination is not working. Fail closed; do not replace the complete time series.
- If the API says wrong statistic ID, use R-ONE's public statistical code search and update verified table IDs only.
- If failure occurs during median lookup, average-only may be published with clear verification metadata; median data is never fabricated.
- If JSON updates but website still old, inspect the **Deploy Pages** step of `Refresh official REB price series` and hard-refresh the website.
- KB currently has no verified suitable official public automatic time-series API. For KB historical expansion import licensed official Excel/CSV through the existing import script; do not scrape Naver/KB undocumented APIs.
