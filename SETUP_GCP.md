# One-time setup: GitHub repo + GCP deployment

Run on the Samsung machine (PowerShell), signed into `gh` (GitHub CLI) and `gcloud` (your GCP project).
Placeholders: `<PROJECT>` = GCP project ID · `<YOU>` = GitHub username/org · region assumed `us-central1`.

## 1 · Create the private repo and push the code

```powershell
cd "C:\Users\RMand\Desktop\Claude Supernus\Database\crm_app"
git init -b main
git add .
git status          # VERIFY: no .db / .csv / .docx / .pptx files listed — .gitignore must hold
git commit -m "Advocacy CRM: served queue, PRC/MLR guides, cadence engine"
gh repo create advocacy-crm --private --source . --push
```

Both machines then just `git clone`. This repo stays separate from your 3 app repos — different
lifecycle, different secrets, and it must never share history with anything that might go public.

## 2 · GCP project plumbing (once)

```powershell
gcloud config set project <PROJECT>
gcloud services enable run.googleapis.com iap.googleapis.com storage.googleapis.com iamcredentials.googleapis.com cloudbuild.googleapis.com
gcloud storage buckets create gs://<PROJECT>-crm-data --location=us-central1 --uniform-bucket-level-access
```

## 3 · Workload Identity Federation (keyless deploys from GitHub Actions)

```powershell
gcloud iam service-accounts create crm-deployer
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:crm-deployer@<PROJECT>.iam.gserviceaccount.com" --role="roles/run.admin"
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:crm-deployer@<PROJECT>.iam.gserviceaccount.com" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:crm-deployer@<PROJECT>.iam.gserviceaccount.com" --role="roles/cloudbuild.builds.editor"
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:crm-deployer@<PROJECT>.iam.gserviceaccount.com" --role="roles/storage.admin"

gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github-oidc `
  --location=global --workload-identity-pool=github `
  --issuer-uri="https://token.actions.githubusercontent.com" `
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" `
  --attribute-condition="assertion.repository=='<YOU>/advocacy-crm'"
gcloud iam service-accounts add-iam-policy-binding crm-deployer@<PROJECT>.iam.gserviceaccount.com `
  --role="roles/iam.workloadIdentityUser" `
  --member="principalSet://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/attribute.repository/<YOU>/advocacy-crm"
```

Then in GitHub → repo → Settings → Variables (Actions), set:
`GCP_PROJECT_ID` = `<PROJECT>` · `GCP_REGION` = `us-central1` ·
`GCP_DEPLOY_SA` = `crm-deployer@<PROJECT>.iam.gserviceaccount.com` ·
`GCP_WIF_PROVIDER` = `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-oidc`

From now on **push to `main` = deploy**. From either laptop, or from Claude via GitHub.

## 4 · Upload the data (the only path member data travels)

```powershell
cd "C:\Users\RMand\Desktop\Claude Supernus\Database\crm_app"
python init_db.py "..\CRM_Master.db" rmandmllc@gmail.com
gcloud storage cp app.db gs://<PROJECT>-crm-data/app.db
```

First deploy (or run the Action once), then attach the volume:

```powershell
gcloud run services update advocacy-crm --region us-central1 `
  --add-volume name=data,type=cloud-storage,bucket=<PROJECT>-crm-data `
  --add-volume-mount volume=data,mount-path=/data
```

Refreshing data later = rebuild app.db locally, `gcloud storage cp`, restart the service.
Pulling dispositions/answers back = `gcloud storage cp gs://<PROJECT>-crm-data/app.db .\app_export.db`,
then ask Claude to sync into CRM_Master.db.

## 5 · Lock the front door (IAP)

```powershell
gcloud beta run services update advocacy-crm --region us-central1 --iap
gcloud beta iap web add-iam-policy-binding --resource-type=cloud-run --service=advocacy-crm `
  --region=us-central1 --member="user:rmandmllc@gmail.com" --role="roles/iap.httpsResourceAccessor"
# repeat the binding for each of the 4 advocate accounts
```

(If `--iap` isn't available in your region yet, front the service with an HTTPS load balancer and
enable IAP on the backend — happy to generate those commands.)

## 6 · Verify

Open the service URL → Google sign-in → you land on the Director console (your email is seeded as
director by init_db). Panel 5 → enroll the 4 advocates. Have one advocate sign in on their machine →
they should see only "My Queue". Confirm a stranger account gets Google's IAP block page.

## Security posture summary

| Threat | Control |
|---|---|
| PII in git / on laptops via repo | .gitignore + data only in GCS; app.db has no emails/addresses by construction |
| Stolen advocate credentials | IAP (Google account + your allowlist); disable in one click |
| Advocate bulk access / export | Served-queue API — no list, search, or export endpoints exist for the role |
| Cheating | Click+disposition timestamps, handle-time flags, GV CDR reconciliation |
| Damage | Advocates have no delete/update endpoints beyond their served card's disposition; full audit trail |
| CI credential leakage | Workload Identity Federation — no service-account keys anywhere |
