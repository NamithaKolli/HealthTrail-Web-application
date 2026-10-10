# HealthTrail — HealthTech Lost in Transit

## Project Demo

[Watch the HealthTrail Demo Video](YOUR_GOOGLE_DRIVE_LINK)
*Demo video link will be updated shortly.*

**A patient-owned, searchable health timeline with expiring, revocable sharing.** This is a student/demo prototype built for a hackathon. It uses synthetic data and is not designed or certified for real patient information or clinical decision-making.

## Why this can stand out

A medical-record folder is useful, but the prototype demonstrates three continuity-of-care ideas together:

1. **Patient health timeline:** one place to search visit summaries, providers, dates, categories, costs, test names and medication mentions.
2. **Repeat-test hints:** exact test-name matches within 90 days are surfaced for review. This is only a prompt to ask the clinician; the system never advises a patient to skip testing.
3. **Patient-controlled sharing:** create a read-only handover link scoped to the last 5 records, last 10 records or all current records. Links expire after 15 minutes, 1 hour or 24 hours and can be revoked early. Shared pages don't expose attachments or full OCR text.

Additional features include sign-up/sign-in with password hashing, ownership-scoped routes and attachments, a quick emergency summary, synthetic demo history, audit entries for link creation/view/revocation with view count and last-opened time, PDF/image extraction with best-effort OCR, and search/filter controls.

## Quick start (Windows, macOS, Linux)

Requires Python 3.10+; Python 3.12 is used in the Docker image.

```bash
cd healthtech_lost_in_transit
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

### Demo account

- Username: `demo`
- Password: `Demo@123`

The app seeds one fictional patient with example records, including two CBC records to demonstrate the possible-repeat hint. Any account created through sign-up receives its own empty record space. All names, facilities, contact details and events in the seeded account are synthetic.

**Never use the demo password for anything personal.** The demo account is deliberately predictable for judging. Before a public demo, confirm that the environment only contains synthetic data and set a fresh `SECRET_KEY`. Set `SEED_DEMO=0` for a fresh deployment that should not create the demo account; this does not remove demo rows from an already-initialized database.

## Adding a medical record

- **Manual:** open *Add a record*, enter fields, and save.
- **PDF/image:** choose a PDF, PNG, JPG/JPEG or WEBP file. Text-based PDFs are read with PyMuPDF. The app attempts OCR for images and scanned PDFs using Tesseract. Extracted values are suggestions only: review the name, date, hospital, category and severity before saving.
- If OCR is unavailable or the file is hard to read, you can still attach it and enter metadata manually.
- Attachments are private and can only be downloaded after signing in as the owning account.

For local OCR on Windows, install Tesseract OCR separately and make sure `tesseract.exe` is on `PATH`. Docker includes Tesseract already.

## Run tests

```bash
python -m pip install pytest
pytest -q
```

## Deployment

The repository includes a `Dockerfile`, `Procfile`, health endpoint (`/health`), and `render.yaml` blueprint. The Render blueprint uses a small persistent disk so SQLite and uploaded files survive deploys. Persistent disks and always-on web services may incur charges; check the platform's current pricing before deploying.

1. Push this folder to a Git repository.
2. In Render, create a new Blueprint from the repository and review the service/disk plan.
3. Deploy, wait for `/health` to return `{"status":"ok"}`, then open the public service URL.
4. Verify sign-up, upload, record search, creating a share link and revoking it.
5. Keep the seeded demo account limited to fictional data. Change the seeded-demo policy before using any non-synthetic records. Set `COOKIE_SECURE=1` only behind HTTPS.

For local Docker testing:

```bash
docker build -t healthtrail .
docker run --rm -p 5000:5000 -e SECRET_KEY="replace-this-for-local-testing" -e DATABASE_PATH=/var/data/healthtransit.db -e UPLOAD_FOLDER=/var/data/uploads -v healthtrail-data:/var/data healthtrail
```

## Important design and privacy limitations

- This prototype stores data in SQLite and local disk. It does **not** connect to real hospitals, laboratories, pharmacy systems, ABHA/ABDM or health information exchanges.
- A share URL is a bearer link: anyone with the complete URL can read the chosen snapshot until expiry or revocation. The patient should only send it to a trusted clinician. Add clinician identity verification, patient consent capture, stronger access controls, and a security review before real-world use.
- Passwords are hashed. Standard forms have CSRF protection. User-specific pages, record edits and file downloads are scoped to the authenticated account. Public share links are random, hashed at rest, expiry-checked, and can be revoked.
- This MVP does not provide medication interaction checking, diagnoses, dosage advice, or triage. The severity value is a patient-entered label. The upload parser's category/severity hints are keyword-based and may be wrong.
- OCR can misread names, dates, costs, lab values and medicine names. Always compare with the original source. Do not rely on this app for emergency decisions.
- Before handling real health data, add formal threat modelling, encrypted storage/backups, retention/deletion policy, audit review, user/session rate limits, secure secret management, accessibility review, and appropriate legal/regulatory compliance. Do not claim compliance without an independent assessment.

## Technical overview

- **Backend:** Flask + SQLite (parameterised SQL)
- **Authentication:** Werkzeug password hashing + signed session cookies
- **Document extraction:** PyMuPDF + Pillow + pytesseract/Tesseract OCR
- **UI:** responsive HTML templates and custom pastel CSS
- **Main tables:** `users`, `records`, `share_links`, `share_records`, `share_access_logs`
- **Tests:** Flask test-client checks for authentication, account isolation and sharing expiry/revocation.

## Pitch for the demo video (around 90 seconds)

1. Start with the problem: a patient must reconstruct years of history during every provider switch.
2. Sign in to the fictional demo account and show a single timeline with category/severity labels and search by a hospital, test, date or keyword.
3. Add a sample report using upload. Show that fields are prefilled, then manually verify/correct them before saving.
4. Explain the repeat-test hint and explicitly say it is not a recommendation to skip testing.
5. Update the profile and create a share link with a 15-minute expiry. Open it in a private/incognito window, show the read-only snapshot, revoke it, and show that it no longer opens.
6. Close with what comes next: verified clinician identity, consent records, FHIR/ABDM integration, stronger auditability and independent security assessment.

## Suggested judging narrative

Call out that the differentiator is not merely “all records in one dashboard”; it is the **patient-controlled handover loop**: collect records → make history searchable → spot possible duplication → share a minimum-needed snapshot → revoke access. The prototype intentionally avoids pretending to diagnose or safely detect drug interactions without validated clinical logic.
