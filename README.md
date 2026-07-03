# advocacy-crm

Patient-advocacy CRM for the ONAPGO education program (Research Catalyst / Parkinson's Community).
Director assigns filtered batches; advocates work a served queue (one card at a time) with Google Voice
click-to-dial and the PRC/MLR-approved discussion guides (SPN.830.2025-0010/-0011/-0012) rendered as
branch-logic forms. Answers populate the database and the director console in real time.

## Architecture

- **FastAPI** app (`main.py`, `ui.py`) on **Cloud Run**, locked behind **Identity-Aware Proxy** (5 allowlisted Google accounts).
- **SQLite** (`app.db`) on a **GCS volume mount** (`/data`). Built locally by `init_db.py` from the master
  database, uploaded with `gcloud storage cp` — see SETUP_GCP.md.
- **Google Voice deep links** for call/text (Workspace GV); clicks + forced dispositions are the activity log;
  monthly GV call-record export reconciles against the app's integrity flags.
- Call program: Initial → capture HCP date → Pre-HCP (window opens HCP−10d, ≤3 serves) → Post-HCP
  (HCP+28d, ≤3 serves) → complete / dq / no_appt / missed_post. New appointment ⇒ new cycle.

## ⚠ Data hygiene — read before committing

**No member data in this repo. Ever.** `.gitignore` blocks `*.db/csv/xlsx/docx/pptx`, but the rule is
behavioral, not just mechanical: the master database, exports, batch CSVs, GV call records, and the
approved guide .docx sources all stay in the local `Database/` working folder or in the private GCS bucket.
The app database also structurally excludes member emails and street addresses (see `init_db.py`).

## Development (Samsung / Legion / Claude)

```
git clone git@github.com:<YOU>/advocacy-crm.git
cd advocacy-crm
pip install -r requirements.txt
python init_db.py "<path to CRM_Master.db>" you@yourorg.com   # local app.db (gitignored)
DEV=1 uvicorn main:app --reload                               # then /?as=you@yourorg.com
```

`DEV=1` bypasses IAP header auth for local work only. Push to `main` deploys via GitHub Actions
(`.github/workflows/deploy.yml`) using Workload Identity Federation — no service-account keys on laptops.

## Files

| File | Purpose |
|---|---|
| `main.py` | API + role enforcement + cadence engine + audit |
| `ui.py` | Director console & advocate queue HTML |
| `guides_seed.py` | Verbatim PRC/MLR discussion guides (script lines, fields, branch logic) |
| `init_db.py` | Builds `app.db` from master DB (PII-minimized) |
| `SETUP_GCP.md` | One-time GCP + GitHub setup, step by step |
| `DEPLOY.md` | Operations: roles, GV notes, disposition sync |
