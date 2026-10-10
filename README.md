# HealthTrail --- HealthTech Lost in Transit

> **A patient-owned platform for unified medical records and continuity
> of care.**

**Live application:**
https://healthtrail-web-application-service.onrender.com

**Demo video:** [Watch the HealthTrail
demo](https://drive.google.com/drive/folders/1i5xrXOnkwSm69Ig7QCc_Sjv34D_zalXU?usp=sharing)

**Source code:**
https://github.com/NamithaKolli/HealthTrail-Web-application

**HealthTrail: Your Medical History, Without the Missing Pieces.**

HealthTrail is a student hackathon prototype that wae have developed to help people collect,
organise, search, and selectively share medical records that would
otherwise be scattered across paper prescriptions, PDFs, photos, and
different providers. The project uses synthetic demonstration data and
is **not intended for real patient data or clinical decision-making**.

------------------------------------------------------------------------

## Table of Contents

-   [Problem Statement](#problem-statement)
-   [Our Solution](#our-solution)
-   [Key Features](#key-features)
-   [What Makes HealthTrail
    Different](#what-makes-healthtrail-different)
-   [Technology Stack](#technology-stack)
-   [How the Application Works](#how-the-application-works)
-   [Database Design](#database-design)
-   [Run Locally](#run-locally)
-   [Deployment](#deployment)
-   [Demo Account](#demo-account)
-   [Limitations and Safety](#limitations-and-safety)
-   [Future Scope](#future-scope)
-   [Team Contributions](#team-contributions)
-   [Conclusion](#conclusion)

------------------------------------------------------------------------

## Problem Statement

Patients with long-term or recurring health conditions often visit
multiple doctors, hospitals, laboratories, and pharmacies. Their records
are kept in different formats and locations, making it difficult to
provide a complete history during a new consultation or emergency.

This fragmentation can contribute to:

*   Incomplete medical history during consultations.
*   Difficulty remembering earlier diagnoses, allergies, tests, and
    medications.
*   Potentially repeated diagnostic tests when earlier results are
    unavailable.
*   Delayed continuity of care when patients change providers or move
    cities.
*   Unsafe or inconvenient sharing of sensitive reports through informal
    channels.

## Our Solution

HealthTrail gives patients a single place to maintain a searchable
medical timeline. Users can add information manually or attach a medical
document, review extracted text, search past visits, identify possible
repeat tests, and create time-limited sharing links for a clinician.

The workflow is:

**Add records → Organise the timeline → Search history → Review possible
repeat tests → Share a limited snapshot → Revoke access**

The application is a prototype and does not connect to real hospital
systems.

## Key Features

### 1. User registration and login

-   Users can create an account and sign in.
-   Passwords are hashed using Werkzeug rather than stored as plain
    text.
-   Record-related routes are scoped to the signed-in user.

### 2. Unified medical timeline

Each record can store fields such as: - Record title and date. - Patient
name. - Doctor and hospital/clinic. - Cost. - Health category. -
Reported severity. - Diagnosis or reason. - Test name. - Medication
names mentioned. - Notes and extracted report text. - An uploaded source
document, where applicable.

### 3. Manual record entry

Patients can enter record details using a form. Required fields are
validated before saving, and users can correct details rather than
relying entirely on automated extraction.

### 4. PDF and image upload with text extraction

-   Supports PDF, PNG, JPG/JPEG, and WEBP uploads within the configured
    file-size limit.
-   PyMuPDF extracts text from text-based PDFs.
-   Pillow supports image handling.
-   pytesseract can call Tesseract OCR for images and scanned PDFs when
    Tesseract is installed and available.
-   Extracted information is a starting point, not verified medical
    data. Users should compare it with the original document and correct
    mistakes before saving.

### 5. Search and filters

Users can search their saved history and narrow records using available
fields such as keywords, provider, category, severity, and date.
Parameterised SQL queries are used for database lookups.

### 6. Reported severity labels

Records can be labelled by reported severity to make the timeline easier
to scan. These labels are organisational metadata, not a clinical
assessment or emergency-triage system.

### 7. Possible repeat-test hints

The prototype highlights matching test names found within a 90-day
period. This can help a patient bring earlier results to a clinician's
attention.

**Important:** a repeated test is not necessarily unnecessary. The
feature is only a prompt to review the history; it does not recommend
skipping a test.

### 8. Temporary, revocable sharing

-   Generate a read-only sharing link for the latest 5 records, latest
    10 records, or all current records.
-   Choose an expiry period of 15 minutes, 1 hour, or 24 hours.
-   Revoke a link before its expiry.
-   Track link creation, views, and revocation.
-   Shared snapshots omit the original attachments and full OCR text.

A share link is a bearer link: anyone with the full URL may access its
snapshot until it expires or is revoked. Only share it with a trusted
recipient.

### 9. Emergency-friendly summary

A printable summary helps users organise selected health information,
such as allergies, current medications, and recent history. It is not a
substitute for a clinician or emergency services.

### 10. Synthetic demo data

A fictional demo account and example records are provided to make the
application easier to evaluate. All demo data should remain fictional.

------------------------------------------------------------------------

## What Makes HealthTrail Different?

HealthTrail is not only a place to upload documents. Its main
differentiator is the **patient-controlled handover workflow**:

1.  Consolidate scattered records into one timeline.
2.  Search for prior diagnoses, tests, providers, and dates.
3.  Surface possible repeat-test matches for discussion with a
    clinician.
4.  Share a selected, read-only history snapshot for a limited time.
5.  Revoke the link when access is no longer required.

This combines continuity-of-care support with user-controlled sharing in
one simple interface. It avoids claiming to diagnose disease or make
clinical decisions.

------------------------------------------------------------------------
 
## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | HTML, Jinja templates, CSS, JavaScript | Responsive forms, dashboards, search, file uploads, and sharing interfaces |
| Backend | Python, Flask | Routing, authentication, form handling, business logic, and server-side rendering |
| Database | SQLite | Stores user accounts, medical records, sharing links, and access logs |
| Password Security | Werkzeug password hashing | Stores password hashes instead of plain-text passwords |
| Form Protection | Flask-WTF, CSRF protection | Helps protect state-changing forms against cross-site request forgery |
| PDF Text Extraction | PyMuPDF | Extracts text from text-based PDF documents |
| Image Processing | Pillow | Opens and processes supported image formats |
| OCR | pytesseract, Tesseract OCR | Attempts text recognition on images and scanned documents |
| Production Server | Gunicorn | Runs the Flask application in the production environment |
| Hosting | Render Web Service | Builds and hosts the publicly accessible web application |
| Testing | pytest, Flask test client | Tests selected authentication, account isolation, and sharing behaviours |


### Architecture overview

1.  A user interacts with the HTML/CSS interface in a browser.
2.  Flask handles the request and checks the user's session and
    permissions.
3.  Structured record information is stored in SQLite.
4.  Uploaded files are stored in the configured upload directory.
5.  PDF/OCR extraction provides text suggestions for the user to review.
6.  When a share URL is opened, the application checks the token,
    expiry, and revocation state before returning a read-only snapshot.


## Database Design

The application uses SQLite to store structured data in the following principal tables:

| Table | Purpose |
|---|---|
| `users` | Stores account identity and password-hash information. |
| `records` | Stores medical-record metadata, extracted text, and attachment references. |
| `share_links` | Stores hashed sharing tokens, expiry times, revocation status, and access metadata. |
| `share_records` | Associates medical records with a shared snapshot. |
| `share_access_logs` | Records events such as share-link creation, viewing, and revocation. |

### Database Relationships

- **Users → Records:** One user can have multiple medical records.
- **Share Links → Share Records:** A share link can include multiple records.
- **Share Records → Records:** Each association identifies a record included in a shared snapshot.
- **Share Links → Share Access Logs:** Access logs help track sharing activity.

SQLite provides lightweight relational storage without requiring a separate database server, making it suitable for this prototype.


## How to Use HealthTrail

1.  **Open the application:** visit the [live HealthTrail
    deployment](https://healthtrail-web-application-service.onrender.com).
2.  **Sign up or sign in:** create a user account, or use the synthetic
    demo account listed below.
3.  **Review the dashboard:** explore the medical timeline and existing
    sample records.
4.  **Add a record:** enter the details manually or choose a supported
    PDF/image.
5.  **Extract and verify:** review the suggested text and correct any
    inaccurate fields before saving.
6.  **Search history:** use keywords and available filters to locate
    older records.
7.  **Review repeat-test hints:** check matching test names and dates,
    and discuss them with a qualified clinician where relevant.
8.  **Share selected history:** create a temporary sharing link, share
    it only with the intended recipient, and revoke it when finished.

### Demo account

-   **Username:** `demo`
-   **Password:** `Demo@123`

This account is intended only for demonstration and uses fictional
records. Do not reuse this password elsewhere or place real patient
information in the demo account. A public demo account is predictable by
design; do not treat it as a private account.

------------------------------------------------------------------------

## Run Locally

### Requirements

-   Python 3.10 or later (Python 3.12 is used in the supplied Docker
    image).
-   Internet access to install Python packages.
-   Tesseract OCR installed separately if image/scanned-document OCR is
    required outside Docker.

### Windows PowerShell

From the folder containing `app.py` and `requirements.txt`:

``` powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Then open <http://127.0.0.1:5000>.

### macOS / Linux

``` bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.

### OCR setup on Windows

Install Tesseract OCR separately and ensure `tesseract.exe` is available
on the system `PATH`. Without it, text extraction from scanned documents
or images may not work, although manual entry and text-based PDF
extraction may still be available.

### Run tests

``` bash
python -m pip install pytest
pytest -q
```

------------------------------------------------------------------------

## Deployment

The live application is hosted as a Render Web Service:

**Live URL:** https://healthtrail-web-application-service.onrender.com

The source repository is:

**GitHub:** https://github.com/NamithaKolli/HealthTrail-Web-application

The project includes deployment configuration such as a `Procfile`,
`render.yaml`, and `Dockerfile`.

For a Render deployment where `app.py` and `requirements.txt` are in the
selected root directory, use:

**Build command**

``` bash
pip install -r requirements.txt
```

**Start command**

``` bash
gunicorn app:app
```

If these files are inside a subfolder, set Render's **Root Directory**
to that folder. The start command assumes that `app.py` exposes the
Flask application instance as `app`.

### Important deployment note

A successful deployment does not automatically guarantee persistent
storage. Render instances may have an ephemeral filesystem unless
persistent storage is configured. SQLite data and uploaded files can be
lost across restarts or redeployments if stored only on an ephemeral
disk. Configure and verify persistent storage before relying on stored
records.

------------------------------------------------------------------------

## Limitations and Safety

-   **Prototype only:** the app is not certified or approved for
    production healthcare use.
-   **Synthetic data:** the project is designed for demonstration and
    should not be used to store real patient records without a thorough
    security, privacy, legal and operational review.
-   **No hospital integration:** it does not connect to real hospital,
    laboratory, pharmacy, ABHA/ABDM, or health-information-exchange
    systems.
-   **OCR can be inaccurate:** names, dates, costs, medication names and
    lab values may be misread. Always verify against the original
    report.
-   **No medical advice:** the app does not diagnose conditions,
    recommend medication doses, detect drug interactions, or provide
    clinical triage.
-   **Severity is descriptive:** severity is a user-entered or
    report-derived label, not a clinical risk prediction.
-   **Repeat-test hints are basic:** matching test names and a 90-day
    window do not determine whether a test is medically necessary.
-   **Bearer-link risk:** anyone who obtains a complete active share URL
    may access its shared snapshot. Link sharing is not equivalent to
    verified clinician authentication.
-   **Local database and file storage:** SQLite and local files are
    appropriate for a small prototype but need a deliberate backup,
    persistence, access-control and scaling strategy for production.
-   **Deployment configuration matters:** secrets must be configured
    safely, persistent storage must be verified, and logs must not
    expose sensitive health information.

Before handling real health data, the system would need threat
modelling, independent security testing, encrypted storage and backups,
appropriate retention/deletion policies, stronger session and rate-limit
controls, verified clinician identity, explicit consent management,
accessibility review, and applicable legal/regulatory compliance. No
compliance claim should be made without an appropriate assessment.

------------------------------------------------------------------------

## Future Scope

1.  **Verified clinician access:** add clinician identity verification
    and role-based access.
2.  **Granular consent:** let patients select exact records and fields,
    define access purposes, and review or revoke permissions.
3.  **Healthcare interoperability:** explore FHIR-compatible data
    exchange and carefully governed integration with India's ABDM
    ecosystem, subject to approvals and standards.
4.  **Stronger duplicate-test support:** compare test type, date,
    provider and available result metadata; keep all matches as review
    suggestions for clinicians.
5.  **Improved document understanding:** use validated extraction
    pipelines and confidence indicators, with mandatory user review and
    no unverified automatic clinical decisions.
6.  **Medication reconciliation:** provide a structured,
    clinician-reviewed medication list; do not claim interaction
    checking without validated clinical data and safety evaluation.
7.  **Notifications and reminders:** support patient-controlled
    reminders for follow-up appointments and tests.
8.  **Production storage:** use a managed database, durable object
    storage for attachments, automated backups, and tested recovery
    procedures.
9.  **Security and privacy:** introduce stronger audit reporting,
    session/rate limiting, key rotation, data export/deletion, and
    independent penetration testing.
10. **Accessibility and multilingual support:** improve keyboard
    navigation, screen-reader support, and language options.

------------------------------------------------------------------------

## Team Contributions

[Namitha Sai Kolli](https://www.linkedin.com/in/namitha-kolli-963419373?utm_source=share_via&utm_content=profile&utm_medium=member_android)


[Ravipati Vishnu Tejaswini](www.linkedin.com/in/vishnu-tejaswini-ravipati-a526663a3)

[Gogineni Gouthami](https://www.linkedin.com/in/gouthami-gogineni-bb340b370)

Together We have worked on the following tasks: 

### Backend and Integration
-   Flask application structure and route integration.
-   SQLite data model and record-management workflow.
-   Authentication/session integration and account-scoped record access.
-   Deployment coordination and integration of application features.


### Document Processing and Data Features

-   Medical document upload workflow and file validation.
-   PDF text extraction and OCR integration.
-   Record search/filtering and possible repeat-test matching logic.
-   Testing document-processing edge cases and extraction limitations.


### Frontend and User Experience

-   Responsive interface using HTML templates and CSS.
-   Dashboard, record-entry forms, profile and medical timeline screens.
-   Patient-facing severity/category labels and emergency summary
    presentation.
-   Sharing screens and usability testing of the end-to-end demo
    workflow.

------------------------------------------------------------------------

## Conclusion

HealthTrail addresses a practical continuity-of-care problem: medical
records often exist, but patients cannot easily find and safely share
them when changing providers. By combining a unified searchable
timeline, document-assisted entry, possible repeat-test hints, and
temporary revocable sharing, the project demonstrates a patient-centred
approach to making medical history easier to carry between
consultations.

The key contribution is the complete handover workflow---not just
document storage. HealthTrail remains a prototype, and its next steps
are stronger persistence, verified clinician access, granular consent,
interoperability, and independent security and clinical-safety
evaluation.

------------------------------------------------------------------------

## Acknowledgements

Built as a student project using open-source Python and web
technologies. All seeded demonstration records are fictional.
