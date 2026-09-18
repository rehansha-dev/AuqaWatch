# AquaWatch — Community Water-Borne Illness & Outbreak Early Warning

**Track 2: Social Impact**

A web app where community members / health workers report water-borne illness
symptoms, and public-health admins get a real-time dashboard that flags
emerging outbreak clusters *early* — before they'd normally be noticed.

## What it does

- **Public reporting form** (`/`) — anyone can report symptoms, water source,
  onset date, and severity for their village/area, in under 2 minutes, no
  login needed.
- **Outbreak detection** — for every area, the backend compares the number
  of reports in a rolling **7-day window** against that area's own **30-day
  baseline** rate. If the window count is well above what's expected, the
  area is flagged:
  - 🟢 **Normal** — in line with baseline
  - 🟡 **Watch** — meaningfully above baseline
  - 🔴 **Outbreak Alert** — sharply above baseline (or absolute thresholds
    for areas with no baseline history yet — "cold start")
  - Each flagged area also shows a **trend** (rising/falling/steady) and its
    most commonly implicated **water source**, to help responders prioritize.
- **Admin dashboard** (`/dashboard`) — login required:
  - Live risk map (color/size-coded clusters, powered by Leaflet + OpenStreetMap)
  - Stat cards (total reports, today's reports, active alerts, areas on watch)
  - Area-by-area status/alert panel
  - Time-series chart of reports (last 14 days)
  - Symptom distribution and suspected-water-source breakdown charts
  - Filterable table of recent reports
  - Auto-refreshes every 30 seconds

## Tech stack

- Backend: Flask + Flask-SQLAlchemy (SQLite — zero setup)
- Frontend: Jinja2 templates + plain CSS (no build step) + Leaflet.js + Chart.js (via CDN)
- No JavaScript framework/bundler needed — just open your browser

## Run it locally

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows (PowerShell: venv\Scripts\Activate.ps1)
# source venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app (auto-creates the SQLite DB and seeds demo data on first run)
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

- Public report form: `http://127.0.0.1:5000/`
- Admin dashboard: `http://127.0.0.1:5000/dashboard`
  - **Username:** `admin`
  - **Password:** `admin123`
  - ⚠️ Demo credentials only — change `ADMIN_USERNAME` / `ADMIN_PASSWORD` in
    `app.py` before any real deployment, and swap the hardcoded check for
    hashed multi-user auth.

The app seeds itself with ~8 demo villages/areas and realistic report
history on first run — including a deliberate spike in one area
("Kondapalli") so you immediately see the outbreak-detection algorithm flag
a real alert when you open the dashboard.

### Resetting demo data

Delete `instance/outbreak.db` and restart the app — it will reseed
automatically.

## Project structure

```
outbreak_watch/
├── app.py                  # Flask app: models, routes, outbreak-detection logic
├── seed.py                 # Demo data generator
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── index.html          # Public report form
│   ├── report_success.html
│   ├── login.html
│   └── dashboard.html      # Admin dashboard
├── static/
│   ├── css/style.css
│   └── js/dashboard.js     # Fetches APIs, renders map + charts + table
└── instance/                # SQLite DB created here at runtime
```

## Outbreak-detection algorithm (for your pitch/demo)

For each area, on every dashboard load:

1. Count reports with symptom onset in the **last 7 days** (`window_count`).
2. Compute the area's **baseline daily rate** from reports in the preceding
   30 days (days 8–37 ago), then scale it to a 7-day `expected` count.
3. Compare:
   - `window_count ≥ expected × 3.0` → **Outbreak Alert**
   - `window_count ≥ expected × 1.8` → **Watch**
   - otherwise → **Normal**
   - Areas without enough history yet fall back to absolute thresholds
     (≥6 reports/week = Alert, ≥3 = Watch) so new areas are still monitored
     from day one ("cold start" handling).
4. A simple **trend** signal (rising/falling/steady) compares the first vs.
   second half of the 7-day window, and the **dominant water source** among
   recent reports is surfaced to help investigators act fast.

This is intentionally explainable (no black-box ML) — good for a hackathon
demo and for public-health responders who need to trust and act on an alert
quickly. It can be extended with proper spatial clustering (e.g. DBSCAN on
lat/lng + time) or Poisson-based anomaly detection if you want to go
further.

## Ideas for extending (if you have time before judging)

- SMS/WhatsApp reporting via Twilio for areas with low smartphone penetration
- District/state-level rollup view
- Exportable PDF outbreak report for health authorities
- Multi-language report form (Telugu/Hindi toggle)
- Push/email notification to health workers when an area crosses "Alert"
