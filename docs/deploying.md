# Deploying this project publicly

This project was built and verified entirely in a local sandbox (SQLite dev fallback, no
Docker/PostgreSQL available — see `docs/architecture.md`'s "lessons carried over" and the
Database section of `README.md`). This doc is a runbook for taking it public: **backend + a
real Postgres on Render, frontend as a static build on Vercel.** Neither has actually been
exercised against a real account from this environment — verify each step against the real
dashboards as you go, and treat exact click-paths/UI labels as approximate.

Swap Render→Railway/Fly.io or Vercel→Netlify freely; the concepts (env vars, CORS origin,
persistent data) are the same everywhere. A single VPS with the existing `docker-compose.yml`
is the other documented option (more control, more maintenance) — not covered step-by-step here.

> Reminder: this is a **research platform on historical data, not a live trading system** (see
> the disclaimer in `README.md` and served by `/health`). Making it public doesn't change that
> — it's still fine to deploy as-is; just keep the disclaimer visible, which it already is on
> both the API and the login page.

## 0. Prerequisites

- A GitHub repo with this project pushed to it (Render and Vercel both deploy from git). If you
  don't have one yet:
  ```bash
  git remote add origin https://github.com/<you>/<repo>.git
  git push -u origin main
  ```
- A Render account and a Vercel account (both have free tiers sufficient for a demo).

## 1. Backend + database (Render)

This repo includes `render.yaml` (a [Blueprint](https://render.com/docs/blueprint-spec)) that
defines the API service and a Postgres instance together. The web service is on Render's
**Starter plan (~$7/mo)**, not free — free-tier web services don't support persistent disks at
all, and this project needs one so `data/`/`models/` survive restarts and redeploys instead of
needing to be regenerated from scratch every time the service spins down from inactivity.

1. Render dashboard → **New +** → **Blueprint** → connect the GitHub repo → Render reads
   `render.yaml` and proposes the `market-intelligence-platform-api` web service (Starter plan)
   plus the `market-intelligence-platform-db` Postgres database (free plan — Postgres itself
   doesn't need a disk to persist, so it can stay free; see the note below on its own limits).
   Apply it.

   **Two real failures hit on the first actual deploy, both already fixed in `render.yaml`,
   left here in case a future change reintroduces either:**
   - `mkdir: cannot create directory '/data': Read-only file system` during the build step —
     Render's build runs in a separate, sandboxed builder that doesn't have the persistent disk
     attached; it only attaches once the service actually starts. Fixed by moving the disk
     symlink setup from `buildCommand` into `startCommand`.
   - Render defaulted to Python 3.14.3 (visible in the build log's "Using Python version..."
     line), new enough that some pinned dependencies risk not having prebuilt wheels yet. Fixed
     by pinning `PYTHON_VERSION` to `3.13.14` — the exact version this project was built and
     tested against locally.
2. Render auto-generates `JWT_SECRET` and wires `DATABASE_URL` to the new Postgres instance
   (see `render.yaml`'s `envVars`) — you don't set these by hand.
3. **`CORS_ALLOWED_ORIGINS`** is intentionally left blank (`sync: false` in the blueprint) since
   it depends on step 2's Vercel URL, which doesn't exist yet. Come back to this after Step 2.
4. First deploy will succeed and `/health` will respond, but every data endpoint will 404 —
   `data/` and `models/` (Phases 2–12's output) don't exist yet. Open a shell on the service
   (Render dashboard → the service → **Shell**) and run the pipeline once, in order:
   ```bash
   cd backend
   python -m app.services.ingestion
   python -m app.services.cleaning
   python -m app.features.feature_engineering
   python -m app.ml.target
   python -m app.ml.models
   python -m app.validation.walk_forward
   python -m app.regime.pipeline
   python scripts/generate_sample_news.py
   python -m app.sentiment.pipeline
   python -m app.explainability.pipeline
   python -m app.backtesting.pipeline
   ```
   This can take a while (Phase 10's FinBERT inference and Phase 7/8's SVM fits are the slow
   steps — see `docs/model_card.md` for real timings observed locally). Output lands under the
   `/data` persistent disk (symlinked to `data/`/`models/` — see `render.yaml`'s comment), so it
   survives future redeploys; you only need to re-run this if you want to refresh the data.
5. Verify: `curl https://<your-service>.onrender.com/api/market-analysis/EURUSD/D1` should
   return real bars, not a 404.

## 2. Frontend (Vercel)

1. Vercel dashboard → **Add New** → **Project** → import the same GitHub repo.
2. **Root Directory**: set to `frontend` (this is a monorepo — Vercel needs to know the app
   isn't at the repo root). Framework preset should auto-detect as Vite.
3. **Environment Variables** → add `VITE_API_BASE_URL` = `https://<your-service>.onrender.com`
   (the Render URL from Step 1, no trailing slash).
4. Deploy. Vercel gives you a URL like `https://<project>.vercel.app` (and a preview URL per
   branch/PR — both are worth allowing in CORS, see below).

## 3. Connect the two: CORS

Back in Render → the API service → **Environment** → set `CORS_ALLOWED_ORIGINS` to your real
Vercel URL(s), comma-separated, e.g.:

```
https://your-app.vercel.app,https://your-app-git-main-yourteam.vercel.app
```

Save → Render redeploys the service automatically. `backend/app/main.py` reads this at startup
(`app.config.SETTINGS.cors_allowed_origins`); without it, the deployed frontend's requests will
fail in the browser console with a CORS error even though the API itself is healthy.

## 4. Verify end to end

Open the Vercel URL, register an account, log in, and click through all 9 pages — the same
manual verification this project has done after every phase (see `docs/testing.md`). Check the
browser console for errors; a CORS error means Step 3 needs another look, a 401 on `/api/auth/me`
after a fresh login means `JWT_SECRET` isn't stable across requests (shouldn't happen on Render,
since it's set once as an env var, not regenerated per request).

## Costs and limits worth knowing before you commit to this path

- The web service runs on Render's Starter plan (~$7/mo) specifically for persistent-disk
  support — see the note at the top of Step 1. It does not spin down from inactivity the way
  the free tier does, so no cold-start delay either.
- Render's free Postgres instances expire after a fixed period (historically 30 days on Render's
  free database plan) — check current terms on Render's pricing page. If you want the database
  itself to be long-lived and not just the disk, budget for a paid Postgres plan too; this
  project's `render.yaml` currently leaves the database on the free plan since only the web
  service actually required the paid tier (for the disk).
- Vercel's free tier is generous for a static SPA like this one; no concerns there.
- Nothing here touches real money or live trading — the highest-stakes secret is `JWT_SECRET`
  (Render generates and stores it for you) and whatever email/password real users register with,
  which is why `app/config.py` now refuses to start with `APP_ENV=production` and the dev-default
  secret (see the guard at the bottom of that file, added alongside this doc).
