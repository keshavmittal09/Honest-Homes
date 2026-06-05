# Honest Homes — The Honest Verdict on a Builder

A B2C property-buyer trust platform for Maharashtra that searches a builder/project and returns an honest, sourced verdict based on official MahaRERA records.

## What's Included

- **44,279 real projects** from MahaRERA (registered as of 2026-06-02)
- **4,536 complaint-promoters** and **450 revoked/deregistered projects** (reputation as of 2026-06-04)
- **FastAPI backend** with live verdict scoring
- **React 18 frontend** with search, browse, and detailed verdict screens
- **Design system** with light/dark themes and advanced UI/UX

## How It Works

1. **Search** a builder or project name
2. **Get a verdict**: Green (safe), Amber (caution), or Red (serious flags) based on:
   - RERA registration status
   - Number of complaints filed
   - Revocation/deregistration status
   - **All sourced from official MahaRERA records**

## Getting Started

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API
python -m uvicorn api.main:app --host 127.0.0.1 --port 8011

# Open in browser
# http://127.0.0.1:8011
```

### Deploy to Production

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions:
- **Render.com** (recommended, 10 minutes)
- **Railway.app** (5 minutes)
- **Your own VPS** (full control, includes monthly collector setup)

## Data

All data is sourced from public MahaRERA records (no scraping, no captcha bypass):
- **Index data**: Public project list (captcha-free)
- **Reputation data**: Complaints and revocations (captcha-free)

Monthly snapshots are collected and ingested to keep verdicts current.

## Architecture

```
Frontend (React 18 in-browser)
    ↓
API (FastAPI @ /api/hh/*)
    ↓
Verdict Engine (reputation + registration signals)
    ↓
Data Stores (project index + reputation snapshots)
```

## Features

- ✅ Search 44k+ projects by name, builder, district
- ✅ Real green/amber/red verdicts with sourced signals
- ✅ Detailed verdict screen with complaint count, timeline, builder track record
- ✅ Print-ready report (PDF/Print button)
- ✅ Light/dark theme toggle
- ✅ Mobile-responsive design

## Legal & Disclaimer

This tool provides information based on official MahaRERA records. It is not legal or financial advice. Always verify with MahaRERA and consult a lawyer before making property decisions.

## Future Roadmap

- Phase 2: Integrate IGR price data for market comparison
- Phase 2: Historical delay tracking (month-over-month snapshots)
- Phase 3: Broker network integration (CP Circle)

## Built With

- **Backend**: FastAPI, Python 3.11
- **Frontend**: React 18, Babel (in-browser JSX)
- **Data**: MahaRERA public records
- **Design**: Source Serif 4, Hanken Grotesk, custom design system

---

**Made with honesty.** For questions or feedback, contact propelloai.mmr@gmail.com
