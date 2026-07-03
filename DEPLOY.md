> **Superseded for initial setup:** follow **SETUP_GCP.md** (repo + CI/CD + WIF + IAP). This file remains the operations reference (roles, GV notes, disposition sync).

# Deploying the Advocacy CRM to your GCP project

One-time setup, ~30 minutes. You need: `gcloud` CLI logged into your GCP project, and Google Workspace accounts for you + the 4 advocates.

## 1. Build the app database (on your machine, in this folder)

```
python init_db.py "..\CRM_Master.db" rmandmllc@gmail.com
```

This creates `app.db` containing only what advocates may see. **Emails and street addresses are never imported** — the guard is structural, not a permission. The compromised Mar–Jul 2026 window stays hidden.

## 2. Deploy to Cloud Run

```
gcloud run deploy advocacy-crm --source . --region us-central1 --no-allow-unauthenticated
```

`--no-allow-unauthenticated` is critical: nobody reaches the app without passing Google identity checks.

For persistence across restarts, mount a GCS bucket (Cloud Run volume mounts):

```
gcloud storage buckets create gs://YOURPROJECT-crm-data --location=us-central1
gcloud run services update advocacy-crm --region us-central1 \
  --add-volume name=data,type=cloud-storage,bucket=YOURPROJECT-crm-data \
  --add-volume-mount volume=data,mount-path=/data
```

## 3. Turn on Identity-Aware Proxy (IAP)

Console → Security → Identity-Aware Proxy → enable for the Cloud Run service (via a load balancer, or use Cloud Run's built-in IAP integration if available in your region: `gcloud beta run services update advocacy-crm --iap`).

Grant **IAP-secured Web App User** to exactly five principals: your email + the 4 advocates. Everyone else gets a Google block page — the app itself is never reached.

## 4. Enroll the team

Open the app → you land on the Director console (your email was seeded as director). Panel 4 → add each advocate's Workspace email. They sign in with their normal Google account and see only "My Queue."

## 5. Google Voice notes

- Advocates must be signed into their **Workspace Google Voice** in the same browser profile — the 📞/💬 buttons deep-link into GV with the number pre-loaded.
- Monthly cheat-check: Admin console → Apps → Google Voice → export call records; compare against Batch detail (handle times) and the Integrity flags panel. Flags catch: dispositions < 20s, "Connected" < 60s after dialing, dispositions with no call/text click at all.

## 6. What each role can and cannot do

| | Director (you) | Advocate |
|---|---|---|
| See member emails | ✗ (not in app.db at all) | ✗ |
| Browse/search all members | filter counts only | ✗ — one served card at a time |
| See phone numbers | ✗ (masked to last 4) | last-4 only; full number only inside the GV link |
| Export | tiers/DNC CSVs | ✗ nothing |
| Call/text | — | assigned card only; buttons exist only on the served card |
| Assign/close batches, add users | ✓ | ✗ |
| Audit trail | every serve/click/disposition, IP-stamped by Cloud Run logs | own tally only |

## 7. Writing results back to CRM_Master.db

Dispositions accumulate in `app.db` (`dispositions` + `comm_hist`). Periodically export and merge into the master DB — ask Claude to "sync app dispositions into CRM_Master.db" and it will append them to `communications` with full traceability.
