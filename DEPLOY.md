# Honest Homes — Deployment Guide

Honest, practical steps to ship this. Read the "Before you deploy" section first —
there are two things that *will* bite you in production if you skip them.

---

## ⚠️ Before you deploy — read this (cofounder honesty)

**1. The frontend currently compiles in the browser (Babel standalone). That's fine
for a demo, slow + fragile for production.**
The `index.html` loads React + Babel from a CDN and transforms `.jsx` on every page
load. It works, but it's ~1–2s slower to first paint and breaks if the CDN hiccups.
For a real launch you'd pre-build the JSX. For a *first* deploy to show people, it's
acceptable — just know it's the first thing to harden. (Mitigation options in step 5.)

**2. Your data is a point-in-time snapshot, and the collector must keep running.**
The site serves `data/snapshots/index/2026-06-02/` (44k projects). That's a *monthly*
snapshot. After deploy you need a plan to (a) run the collector monthly on a server,
and (b) have the API pick up new snapshots. Right now both are manual. Decide who/what
runs the monthly crawl before you promise users "updated monthly."

**3. Honesty about what ships:** every real project shows **N/A** (no score) until the
reputation collector exists. The site is truthful about this ("we won't fake a score").
That's fine to launch — but the dramatic green/amber/red verdicts are the 3 *illustrative*
showcase projects. If a stakeholder expects real scored verdicts, build the reputation
collector first. See "What makes N/A become real scores" below.

---

## What you're deploying

- **Backend:** FastAPI (`api/main.py`) — serves the API + the static frontend.
- **Frontend:** static files in `web/` (HTML/CSS/JSX), served by the same FastAPI app.
- **Data:** JSON snapshots in `data/` (read at startup into memory).

One process serves everything. Simple.

---

## Option A — Fastest real deploy: Render / Railway / Fly.io (recommended first)

These host a Python web service from your Git repo with almost no config.

1. **Push the repo to GitHub** (private is fine).
   - Make sure `data/snapshots/index/2026-06-02/` is committed (it's gitignored by
     default — see note below).
2. **Add a start command** the host will run:
   ```
   uvicorn api.main:app --host 0.0.0.0 --port $PORT
   ```
3. **requirements.txt** is already present — the host installs it automatically.
4. **Pick the host:**
   - **Render** (render.com) → New → Web Service → connect repo → Python → paste start
     command → Deploy. Free tier works for a demo.
   - **Railway** (railway.app) → New Project → Deploy from repo → it autodetects Python.
   - **Fly.io** → `fly launch` → follow prompts.
5. Done — you get a public `https://…` URL.

### The data/gitignore gotcha
`.gitignore` currently ignores `data/`. For deploy you must ship the snapshot. Either:
- Commit just the one snapshot: `git add -f data/snapshots/index/2026-06-02/snapshot.json`
  (the API can read `snapshot.json` alone), **or**
- Remove `data/` from `.gitignore` and commit the whole snapshot folder.
The API needs `data/snapshots/index/<date>/snapshot.json` present at startup.

---

## Option B — A VPS you control (DigitalOcean / EC2 / Hetzner)

More control; you run the monthly collector on the same box.

```bash
# on the server (Ubuntu)
git clone <your-repo> && cd HonestHomes
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# run behind a process manager so it restarts on crash/reboot:
#   systemd unit OR: pip install gunicorn; gunicorn -k uvicorn.workers.UvicornWorker api.main:app
uvicorn api.main:app --host 0.0.0.0 --port 8011
# put nginx in front for TLS (certbot for a free cert) + a domain.
```

Then schedule the monthly collector with cron:
```
# 2am on the 1st of each month, gentle pace
0 2 1 * *  cd /path/HonestHomes && .venv/bin/python -m collector.run_index --min-delay 8 --max-delay 15
```
Restart the API after a successful run so it loads the new snapshot (the store reads the
newest snapshot at startup).

---

## Step 5 — Production hardening (do after the first deploy works)

1. **Pre-build the frontend** so browsers don't run Babel. Quickest: a small build step
   that Babel-transforms the `.jsx` to `.js` ahead of time and swap the `text/babel`
   script tags for plain `<script>`. (Ask me — it's ~30 min of work.)
2. **Lock CORS / hosts** in `api/main.py` if you split frontend and backend domains.
3. **Add a real DB** (SQLite is enough for 44k rows) so search is indexed, not linear,
   and so you can keep multiple monthly snapshots for the month-over-month moat.
4. **Cache headers** on the static files.
5. **Domain + TLS** (honesthomes.in or similar). On Render/Railway this is one click.

---

## What makes the N/A scores become real

This is the product question, not the deploy question. Real green/amber/red verdicts
need the **reputation collector** (complaints, orders, revocations — all captcha-free
MahaRERA pages). Once that data is ingested and `api/shape.py` maps it into the verdict,
every real project gets a defensible score. Build that before promising "scored verdicts".

---

## Honest pre-launch checklist

- [ ] Snapshot committed and present at `data/snapshots/index/<date>/snapshot.json`
- [ ] App boots on the host (`/api/health` returns `projects_loaded > 0`)
- [ ] Decide monthly-collector plan (who runs it, where)
- [ ] Disclaimer + "as of <date>" visible on every verdict (already built — verify live)
- [ ] A lawyer has glanced at the disclaimer wording (you're advising on big purchases)
- [ ] Decide: launch with N/A-only real data, or build reputation collector first
