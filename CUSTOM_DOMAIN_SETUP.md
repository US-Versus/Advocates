# Set up crm.parkinsons.community → Advocacy CRM

Goal: `https://crm.parkinsons.community/CRM` = advocate console, `.../director` = director console.
Security is unchanged — the same Identity-Aware Proxy sign-in fronts the subdomain, and the 3-person
allowlist stays exactly as-is (it lives on the service, not the domain).

The app side is done (the `/CRM` and `/director` paths exist). Three steps remain, all at your **domain
registrar** (GoDaddy / Namecheap / wherever parkinsons.community is registered). Two need a person with
registrar login; the middle GCP step Claude runs.

---

## Step 1 — Verify domain ownership (registrar + a browser)

**Important:** sign in as **support@researchcat.com** — the same Google account that deploys the app —
so the mapping in Step 2 is allowed. (If someone else verifies it, add support@researchcat.com as an
"owner" in Search Console.)

1. Go to **https://search.google.com/search-console** → **Add property** → **Domain** →
   enter `parkinsons.community` (the bare domain — this covers all subdomains).
2. Google shows a **TXT record** like `google-site-verification=abc123…`.
3. At the registrar's DNS page, add a **TXT record**:
   - Host/Name: `@` (or blank / the root)
   - Value: the `google-site-verification=…` string Google gave you
   - TTL: default
4. Wait a few minutes, then click **Verify** in Search Console. ✅

This TXT record does **not** affect the WordPress website — it only proves ownership.

---

## Step 2 — Create the mapping (Claude runs this once Step 1 is verified)

Claude runs `gcloud beta run domain-mappings create --service advocacy-crm
--domain crm.parkinsons.community --region us-central1`, which returns the **exact CNAME target**
(a `ghs.googlehosted.com`-style value). Tell Claude when Step 1 is verified.

---

## Step 3 — Point the subdomain at the app (registrar)

Add ONE record at the registrar (Claude gives you the exact value from Step 2):

| Type  | Host / Name | Value                         | TTL     |
|-------|-------------|-------------------------------|---------|
| CNAME | `crm`       | `ghs.googlehosted.com.`       | default |

This creates `crm.parkinsons.community` and touches nothing on `www` or the apex — the WordPress site
is completely unaffected.

---

## Then

- Google auto-provisions a managed TLS certificate (~15–60 min after the CNAME resolves).
- `https://crm.parkinsons.community/CRM` → advocate console; `.../director` → director console;
  `https://crm.parkinsons.community/` alone → sends each person to the right console by role.
- First visit still goes through the Google IAP sign-in, same as today.

## Optional — the exact `/CRM` and `/director` paths on www too
If you also want `www.parkinsons.community/CRM` to work (not just the subdomain), add two redirect rules
in **WordPress** (Redirection plugin or host redirect settings):
`/CRM` → `https://crm.parkinsons.community/CRM` and `/director` → `https://crm.parkinsons.community/director`.
Claude cannot do this — it has no access to the WordPress site.
