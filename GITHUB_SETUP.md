# Existing GitHub deployment — v1.2

The repository is already public and Pages works: https://ym32090.github.io/seoul-apt-price-dashboard/

**Use `LIVE_SETUP.md` for the activation steps.** The missing workflow path must be `.github/workflows/refresh-reb.yml` on `main`. `REB_API_KEY` must be a Repository Secret, never in `index.html`. Keep `Settings > Pages > Source: Deploy from a branch > main / (root)`; the workflow includes an explicit Pages deployment because bot commits do not trigger branch publishing.

After upload, verify `Actions > Refresh official REB price series > Run workflow` works, and check actual `data/reb.json` row count, `verification`, website source and tooltip. No automatic updates until you activate the workflow with key and upload the workflow file.
