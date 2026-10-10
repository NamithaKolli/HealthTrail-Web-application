from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

CATEGORIES = [
    "Cardiovascular", "Endocrine", "Respiratory", "Gastroenterology",
    "Neurology", "Orthopedics", "Dermatology", "Infectious Disease",
    "Ophthalmology", "Mental Health", "General / Other",
]
SEVERITIES = ["Low", "Moderate", "High", "Emergency"]
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
MAX_TEXT_LENGTH = 50_000

CATEGORY_KEYWORDS = {
    "Cardiovascular": ["cardiac", "cardiology", "heart", "hypertension", "blood pressure", "ecg", "ekg", "cholesterol", "varicose", "vein"],
    "Endocrine": ["diabetes", "diabetic", "glucose", "hba1c", "thyroid", "tsh", "insulin", "endocrine"],
    "Respiratory": ["asthma", "respiratory", "lung", "breathing", "bronchitis", "pneumonia", "inhaler"],
    "Gastroenterology": ["gastro", "diarrhea", "diarrhoea", "stomach", "abdominal", "acidity", "gastritis", "liver", "intestine", "vomiting"],
    "Neurology": ["neurology", "migraine", "seizure", "neurological", "headache", "brain"],
    "Orthopedics": ["orthopedic", "orthopaedic", "bone", "fracture", "joint", "arthritis", "spine", "knee"],
    "Dermatology": ["dermatology", "skin", "rash", "eczema", "acne", "dermatitis"],
    "Infectious Disease": ["viral", "infection", "infectious", "fever", "dengue", "malaria", "covid", "influenza", "bacterial"],
    "Ophthalmology": ["eye", "ophthalmology", "vision", "retina", "cataract"],
    "Mental Health": ["mental health", "psychiatry", "anxiety", "depression", "psychology"],
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    instance_dir = Path(app.instance_path)
    instance_dir.mkdir(parents=True, exist_ok=True)
    default_upload_dir = instance_dir / "uploads"
    default_upload_dir.mkdir(parents=True, exist_ok=True)
    (default_upload_dir / ".staging").mkdir(parents=True, exist_ok=True)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_path = instance_dir / "secret_key"
        try:
            with secret_path.open("x", encoding="utf-8") as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret_key = secret_path.read_text(encoding="utf-8").strip()
        if not secret_key:
            secret_key = secrets.token_hex(32)

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DATABASE_PATH=os.environ.get("DATABASE_PATH", str(instance_dir / "healthtransit.db")),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", str(default_upload_dir)),
        MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        SEED_DEMO=os.environ.get("SEED_DEMO", "1") == "1",
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    (Path(app.config["UPLOAD_FOLDER"]) / ".staging").mkdir(parents=True, exist_ok=True)

    csrf = CSRFProtect()
    csrf.init_app(app)

    def connect_db() -> sqlite3.Connection:
        path = app.config["DATABASE_PATH"]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def init_db() -> None:
        connection = connect_db()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                allergies TEXT NOT NULL DEFAULT '',
                current_medications TEXT NOT NULL DEFAULT '',
                chronic_conditions TEXT NOT NULL DEFAULT '',
                emergency_contact TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                patient_name TEXT NOT NULL,
                record_date TEXT NOT NULL,
                doctor_name TEXT NOT NULL DEFAULT '',
                hospital_name TEXT NOT NULL DEFAULT '',
                cost REAL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                diagnosis TEXT NOT NULL DEFAULT '',
                test_type TEXT NOT NULL DEFAULT '',
                medications TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                extracted_text TEXT NOT NULL DEFAULT '',
                attachment_path TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, record_date DESC);
            CREATE INDEX IF NOT EXISTS idx_records_user_category ON records(user_id, category);
            CREATE TABLE IF NOT EXISTS share_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                scope_label TEXT NOT NULL,
                profile_snapshot TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS share_records (
                share_id INTEGER NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
                record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                PRIMARY KEY (share_id, record_id)
            );
            CREATE TABLE IF NOT EXISTS share_access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_id INTEGER NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
                event TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
        connection.close()
        if app.config.get("SEED_DEMO", True):
            seed_demo_database()

    def seed_demo_database() -> None:
        connection = connect_db()
        connection.execute("BEGIN IMMEDIATE")
        found = connection.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()
        if found:
            connection.close()
            return
        cursor = connection.execute(
            """INSERT INTO users
               (username, full_name, password_hash, allergies, current_medications,
                chronic_conditions, emergency_contact, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "demo", "Aarav Demo", generate_password_hash("Demo@123"),
                "Penicillin (synthetic example)", "Metformin (example; reconcile with clinician)",
                "Type 2 diabetes; hypertension (synthetic examples)", "+91 90000 00000 (sample only)", iso_now(),
            ),
        )
        user_id = cursor.lastrowid
        today = date.today()
        samples = [
            (-4, "Dr. Meera Rao", "Lotus Family Clinic", 450, "Endocrine", "Moderate", "HbA1c follow-up", "Type 2 diabetes monitoring (synthetic)", "HbA1c", "Metformin (example)", "Synthetic sample record. Review actual medication list with a clinician."),
            (-17, "Dr. Arjun Menon", "City Diagnostics", 650, "General / Other", "Low", "Complete Blood Count (CBC)", "Routine blood count (synthetic)", "CBC", "", "Synthetic sample. A repeat test may be intentional; verify context."),
            (-32, "Dr. Meera Rao", "Lotus Family Clinic", 650, "General / Other", "Low", "Complete Blood Count (CBC)", "Routine blood count (synthetic)", "CBC", "", "Synthetic sample. Included to demonstrate repeat-test hints."),
            (-48, "Dr. Kavya Iyer", "Green Park Hospital", 800, "Cardiovascular", "Moderate", "Blood pressure review", "Hypertension follow-up (synthetic)", "", "Amlodipine (example)", "Synthetic sample. This entry is not a prescription."),
            (-75, "Dr. Sanjay Das", "Northside Respiratory Centre", 1100, "Respiratory", "Moderate", "Asthma review", "Asthma follow-up (synthetic)", "Spirometry", "Salbutamol inhaler (example)", "Synthetic sample."),
            (-103, "Dr. Ananya Shah", "Sunrise Clinic", 380, "Infectious Disease", "Low", "Acute fever consultation", "Viral fever (synthetic example)", "", "", "Synthetic sample, not a real clinical event."),
            (-130, "Dr. Vivek Nair", "Metro Gastro Clinic", 1250, "Gastroenterology", "Low", "Gastroenteritis consultation", "Diarrhoea and dehydration assessment (synthetic)", "Stool test", "", "Synthetic sample. Severity is illustrative only."),
            (-165, "Dr. Meera Rao", "City Diagnostics", 900, "Endocrine", "Moderate", "Thyroid panel", "Thyroid function follow-up (synthetic)", "TSH panel", "Levothyroxine (example)", "Synthetic sample; dose intentionally not supplied."),
            (-210, "Dr. Kavya Iyer", "Green Park Hospital", 1500, "Cardiovascular", "High", "ECG and cardiac review", "Palpitations evaluation (synthetic)", "ECG", "", "Synthetic example marked high for demo; not an urgent-care rule."),
            (-252, "Dr. Rohan Kulkarni", "OrthoCare Clinic", 2100, "Orthopedics", "Moderate", "Leg vein consultation", "Varicose veins assessment (synthetic)", "Venous Doppler", "Compression stockings discussed (example)", "Synthetic sample."),
            (-300, "Dr. Sanjay Das", "Northside Respiratory Centre", 700, "Respiratory", "Moderate", "Asthma prescription review", "Asthma management (synthetic)", "", "Salbutamol inhaler (example)", "Synthetic sample."),
            (-350, "Dr. Leela Thomas", "City Diagnostics", 530, "Endocrine", "Moderate", "Fasting glucose test", "Glucose monitoring (synthetic)", "Fasting glucose", "", "Synthetic sample."),
            (-410, "Dr. Omar Khan", "Eastside Eye Centre", 600, "Ophthalmology", "Low", "Vision check", "Routine vision review (synthetic)", "Eye exam", "", "Synthetic sample."),
            (-470, "Dr. Vivek Nair", "Metro Gastro Clinic", 980, "Gastroenterology", "Moderate", "Acidity follow-up", "Gastritis assessment (synthetic)", "", "Antacid (example)", "Synthetic sample."),
        ]
        for days_ago, doctor, hospital, cost, category, severity, title, diagnosis, test_type, medications, notes in samples:
            connection.execute(
                """INSERT INTO records
                   (user_id, patient_name, record_date, doctor_name, hospital_name, cost,
                    category, severity, title, diagnosis, test_type, medications, notes,
                    source_type, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synthetic', ?)""",
                (user_id, "Aarav Demo", (today + timedelta(days=days_ago)).isoformat(), doctor, hospital,
                 cost, category, severity, title, diagnosis, test_type, medications, notes, iso_now()),
            )
        connection.commit()
        connection.close()

    @app.teardown_appcontext
    def close_db(_exception: BaseException | None = None) -> None:
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            path = app.config["DATABASE_PATH"]
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            g.db = sqlite3.connect(path)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
            g.db.execute("PRAGMA busy_timeout = 5000")
        return g.db

    # Make the DB connection available to seed and route functions.
    app.extensions["healthtransit_connect_db"] = connect_db

    def current_user() -> sqlite3.Row | None:
        if "user" not in g:
            user_id = session.get("user_id")
            g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None
        return g.user

    app.jinja_env.globals["current_user"] = current_user
    app.jinja_env.globals["categories"] = CATEGORIES
    app.jinja_env.globals["severities"] = SEVERITIES
    app.jinja_env.globals["demo_enabled"] = app.config.get("SEED_DEMO", True)

    @app.before_request
    def load_logged_in_user() -> None:
        current_user()

    def login_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if current_user() is None:
                flash("Please sign in to access your health records.", "info")
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped_view

    def own_record(record_id: int) -> sqlite3.Row:
        row = get_db().execute("SELECT * FROM records WHERE id = ? AND user_id = ?", (record_id, current_user()["id"])).fetchone()
        if row is None:
            abort(404)
        return row

    def clean_text(value: Any, limit: int = 3000) -> str:
        return str(value or "").strip()[:limit]

    def parse_cost(value: Any) -> float | None:
        value = str(value or "").strip().replace(",", "")
        if not value:
            return None
        try:
            number = float(value)
            if number < 0 or number > 100_000_000:
                raise ValueError
            return round(number, 2)
        except ValueError:
            raise ValueError("Cost must be a non-negative number.")

    def record_form_values(form) -> dict[str, Any]:
        values = {
            "patient_name": clean_text(form.get("patient_name"), 120),
            "record_date": clean_text(form.get("record_date"), 10),
            "doctor_name": clean_text(form.get("doctor_name"), 160),
            "hospital_name": clean_text(form.get("hospital_name"), 180),
            "cost": clean_text(form.get("cost"), 30),
            "category": clean_text(form.get("category"), 60),
            "severity": clean_text(form.get("severity"), 20),
            "title": clean_text(form.get("title"), 180),
            "diagnosis": clean_text(form.get("diagnosis"), 1500),
            "test_type": clean_text(form.get("test_type"), 120),
            "medications": clean_text(form.get("medications"), 1500),
            "notes": clean_text(form.get("notes"), 4000),
            "extracted_text": clean_text(form.get("extracted_text"), MAX_TEXT_LENGTH),
            "pending_upload": clean_text(form.get("pending_upload"), 120),
        }
        return values

    def validate_record_values(values: dict[str, Any]) -> tuple[str | None, float | None]:
        if not values["patient_name"] or not values["record_date"] or not values["title"]:
            raise ValueError("Patient name, record date and record title are required.")
        try:
            date.fromisoformat(values["record_date"])
        except ValueError:
            raise ValueError("Enter a valid record date.")
        if values["category"] not in CATEGORIES:
            raise ValueError("Choose a valid health concern category.")
        if values["severity"] not in SEVERITIES:
            raise ValueError("Choose a valid reported severity.")
        cost = parse_cost(values["cost"])
        pending = values["pending_upload"]
        if pending and pending != session.get("pending_upload"):
            raise ValueError("The uploaded file session expired. Upload the report again.")
        return pending or None, cost

    def get_potential_repeats(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
        rows = get_db().execute(
            """SELECT id, record_date, title, test_type, hospital_name, cost, category
               FROM records WHERE user_id = ? AND TRIM(test_type) != ''
               ORDER BY record_date DESC, id DESC LIMIT 250""", (user_id,)
        ).fetchall()
        repeats: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for i, latest in enumerate(rows):
            try:
                latest_date = date.fromisoformat(latest["record_date"])
            except ValueError:
                continue
            latest_test = re.sub(r"\W+", "", latest["test_type"].lower())
            if len(latest_test) < 3:
                continue
            for previous in rows[i + 1:]:
                previous_test = re.sub(r"\W+", "", previous["test_type"].lower())
                if latest_test != previous_test:
                    continue
                try:
                    previous_date = date.fromisoformat(previous["record_date"])
                except ValueError:
                    continue
                gap = abs((latest_date - previous_date).days)
                if 0 < gap <= 90:
                    pair = (min(latest["id"], previous["id"]), max(latest["id"], previous["id"]))
                    if pair not in seen:
                        seen.add(pair)
                        repeats.append({
                            "latest": latest, "previous": previous, "gap": gap,
                            "combined_cost": (latest["cost"] or 0) + (previous["cost"] or 0),
                        })
                    break
            if len(repeats) >= limit:
                break
        return repeats

    def extract_document_text(file_path: Path, ext: str) -> tuple[str, str | None]:
        """Extract PDF text first; use OCR as a best-effort fallback."""
        text = ""
        warning: str | None = None
        try:
            if ext == "pdf":
                doc = fitz.open(file_path)
                text = "\n".join(page.get_text("text") for page in doc[:8])[:MAX_TEXT_LENGTH]
                if not text.strip():
                    try:
                        pages = []
                        for page in doc[:3]:
                            pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            pages.append(pytesseract.image_to_string(image))
                        text = "\n".join(pages)[:MAX_TEXT_LENGTH]
                    except Exception:
                        warning = "This looks like a scanned PDF, but OCR was unavailable. You can still attach it and fill in the fields manually."
                doc.close()
            else:
                with Image.open(file_path) as image:
                    image = image.convert("RGB")
                    text = pytesseract.image_to_string(image)[:MAX_TEXT_LENGTH]
        except Exception as exc:
            warning = "Text extraction did not work for this file. You can still save the attachment and enter its details manually."
            app.logger.info("Document extraction fallback: %s", type(exc).__name__)
        if not text.strip() and warning is None:
            warning = "No readable text was found. Review the image/PDF and fill in the fields manually."
        return text.strip(), warning

    def guess_date(text: str) -> str:
        match = re.search(r"\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b", text)
        if not match:
            return date.today().isoformat()
        raw = match.group(1).replace(".", "/").replace("-", "/")
        formats = ["%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        return date.today().isoformat()

    def suggest_fields(text: str, user_name: str) -> dict[str, str]:
        lower = text.lower()
        category = "General / Other"
        max_matches = 0
        for candidate, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(lower.count(word) for word in keywords)
            if hits > max_matches:
                category, max_matches = candidate, hits
        if any(word in lower for word in ["icu", "intensive care", "emergency admission", "resuscitation"]):
            severity = "Emergency"
        elif any(word in lower for word in ["severe", "hospital admission", "critical condition"]):
            severity = "High"
        elif any(word in lower for word in ["diabetes", "hypertension", "asthma", "thyroid", "chronic", "varicose"]):
            severity = "Moderate"
        else:
            severity = "Low"

        doctor = ""
        doctor_match = re.search(r"\b(?:doctor|dr\.?|consultant)\s*[:.-]?\s*([A-Z][A-Za-z.' -]{2,60})", text)
        if doctor_match:
            doctor = doctor_match.group(1).strip(" .,:;\n\r")[:150].split("\n")[0]
        hospital = ""
        for line in text.splitlines()[:100]:
            if re.search(r"hospital|clinic|diagnostic|medical centre|medical center|healthcare", line, re.I):
                candidate = line.strip(" :-\t")
                if 2 <= len(candidate) <= 180:
                    hospital = candidate
                    break
        cost = ""
        cost_match = re.search(r"(?:₹|\bINR\b|\bRs\.?\s*)([0-9][0-9,]*(?:\.\d{1,2})?)", text, re.I)
        if cost_match:
            cost = cost_match.group(1).replace(",", "")
        elif re.search(r"(?:total|amount|bill)\s*[:=-]\s*[₹]?\s*[0-9,]+", text, re.I):
            amount_match = re.search(r"(?:total|amount|bill)\s*[:=-]\s*[₹]?\s*([0-9,]+(?:\.\d{1,2})?)", text, re.I)
            if amount_match:
                cost = amount_match.group(1).replace(",", "")
        first_lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 4]
        title = next((line[:160] for line in first_lines[:10] if not re.search(r"patient|hospital|doctor|address|phone|date|age|gender", line, re.I)), "Uploaded medical report")
        patient_match = re.search(r"(?:patient\s*(?:name)?|name)\s*[:.-]\s*([A-Za-z][A-Za-z .'-]{1,100})", text, re.I)
        patient_name = patient_match.group(1).strip()[:120] if patient_match else user_name
        return {
            "patient_name": patient_name,
            "record_date": guess_date(text),
            "doctor_name": doctor,
            "hospital_name": hospital,
            "cost": cost,
            "category": category,
            "severity": severity,
            "title": title,
            "diagnosis": "",
            "test_type": "",
            "medications": "",
            "notes": "",
            "extracted_text": text,
        }

    @app.route("/health")
    def health_check():
        return jsonify(status="ok", service="HealthTech Lost in Transit"), 200

    @app.route("/")
    def index():
        return redirect(url_for("dashboard") if current_user() else url_for("login"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            full_name = clean_text(request.form.get("full_name"), 120)
            username = clean_text(request.form.get("username"), 40)
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not full_name or not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
                flash("Enter your name and a username of 3–40 letters, numbers, dots, underscores or hyphens.", "error")
            elif len(password) < 8:
                flash("Use a password with at least 8 characters.", "error")
            elif password != confirm:
                flash("The passwords do not match.", "error")
            else:
                try:
                    cursor = get_db().execute(
                        "INSERT INTO users (username, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                        (username, full_name, generate_password_hash(password), iso_now()),
                    )
                    get_db().commit()
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    flash("Your private health space is ready. Add your first record to begin.", "success")
                    return redirect(url_for("dashboard"))
                except sqlite3.IntegrityError:
                    flash("That username is already taken. Try another one.", "error")
        return render_template("signup.html", page_title="Create your account")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = clean_text(request.form.get("username"), 40)
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Username or password is incorrect.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                target = request.args.get("next", "")
                # Only allow local app paths after login.
                if target.startswith("/") and not target.startswith("//"):
                    return redirect(target)
                flash(f"Welcome back, {user['full_name'].split()[0]}.", "success")
                return redirect(url_for("dashboard"))
        return render_template("login.html", page_title="Welcome back")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        session.clear()
        flash("You have been signed out.", "info")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        db = get_db()
        totals = db.execute(
            """SELECT COUNT(*) AS record_count, COALESCE(SUM(cost), 0) AS total_cost,
                      SUM(CASE WHEN severity IN ('High', 'Emergency') THEN 1 ELSE 0 END) AS priority_count
               FROM records WHERE user_id = ?""", (user["id"],)
        ).fetchone()
        recent = db.execute("SELECT * FROM records WHERE user_id = ? ORDER BY record_date DESC, id DESC LIMIT 6", (user["id"],)).fetchall()
        category_rows = db.execute(
            "SELECT category, COUNT(*) AS n FROM records WHERE user_id = ? GROUP BY category ORDER BY n DESC LIMIT 5", (user["id"],)
        ).fetchall()
        repeats = get_potential_repeats(user["id"], 4)
        active_shares = db.execute("SELECT COUNT(*) FROM share_links WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?", (user["id"], iso_now())).fetchone()[0]
        return render_template("dashboard.html", page_title="Your health overview", totals=totals, recent=recent,
                               category_rows=category_rows, repeats=repeats, active_shares=active_shares)

    @app.route("/records")
    @login_required
    def records():
        user_id = current_user()["id"]
        q = clean_text(request.args.get("q"), 180)
        category = clean_text(request.args.get("category"), 60)
        severity = clean_text(request.args.get("severity"), 20)
        hospital = clean_text(request.args.get("hospital"), 180)
        start_date = clean_text(request.args.get("start_date"), 10)
        end_date = clean_text(request.args.get("end_date"), 10)
        clauses = ["user_id = ?"]
        params: list[Any] = [user_id]
        if q:
            searchable = ["patient_name", "record_date", "doctor_name", "hospital_name", "category", "severity", "title", "diagnosis", "test_type", "medications", "notes", "extracted_text", "original_filename", "source_type", "created_at", "CAST(cost AS TEXT)"]
            clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable) + ")")
            params.extend([f"%{q}%"] * len(searchable))
        if category in CATEGORIES:
            clauses.append("category = ?")
            params.append(category)
        if severity in SEVERITIES:
            clauses.append("severity = ?")
            params.append(severity)
        if hospital:
            clauses.append("hospital_name LIKE ?")
            params.append(f"%{hospital}%")
        if start_date:
            try:
                date.fromisoformat(start_date)
                clauses.append("record_date >= ?")
                params.append(start_date)
            except ValueError:
                flash("The start date filter was ignored because it is invalid.", "info")
        if end_date:
            try:
                date.fromisoformat(end_date)
                clauses.append("record_date <= ?")
                params.append(end_date)
            except ValueError:
                flash("The end date filter was ignored because it is invalid.", "info")
        sql = "SELECT * FROM records WHERE " + " AND ".join(clauses) + " ORDER BY record_date DESC, id DESC LIMIT 300"
        rows = get_db().execute(sql, params).fetchall()
        return render_template("records.html", page_title="Search your records", records=rows,
                               filters={"q": q, "category": category, "severity": severity, "hospital": hospital,
                                        "start_date": start_date, "end_date": end_date})

    @app.route("/records/new")
    @login_required
    def new_record():
        return render_template("record_form.html", page_title="Add a health record", values={
            "patient_name": current_user()["full_name"], "record_date": date.today().isoformat(),
            "category": "General / Other", "severity": "Low", "title": "", "doctor_name": "",
            "hospital_name": "", "cost": "", "diagnosis": "", "test_type": "", "medications": "",
            "notes": "", "extracted_text": "", "pending_upload": "",
        }, mode="create", upload_warning=None)

    @app.route("/records/extract", methods=["POST"])
    @login_required
    def extract_upload():
        upload = request.files.get("medical_file")
        if upload is None or not upload.filename:
            flash("Choose a PDF or image to upload first.", "error")
            return redirect(url_for("new_record"))
        safe_name = secure_filename(upload.filename)
        suffix = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if suffix not in ALLOWED_EXTENSIONS:
            flash("Supported formats are PDF, PNG, JPG, JPEG and WEBP.", "error")
            return redirect(url_for("new_record"))
        pending_id = uuid.uuid4().hex + "." + suffix
        stage_path = Path(app.config["UPLOAD_FOLDER"]) / ".staging" / pending_id
        try:
            upload.save(stage_path)
            if stage_path.stat().st_size > app.config["MAX_CONTENT_LENGTH"]:
                stage_path.unlink(missing_ok=True)
                flash("That file is too large. The maximum upload size is 12 MB.", "error")
                return redirect(url_for("new_record"))
            text, warning = extract_document_text(stage_path, suffix)
            values = suggest_fields(text, current_user()["full_name"])
            values["pending_upload"] = pending_id
            session["pending_upload"] = pending_id
            session["pending_original_filename"] = safe_name[:240]
            if warning:
                flash(warning, "info")
            flash("We filled a few fields from the document where possible. Verify every suggestion before saving.", "info")
            return render_template("record_form.html", page_title="Review extracted record", values=values,
                                   mode="create", upload_warning=warning, uploaded_filename=safe_name)
        except Exception:
            stage_path.unlink(missing_ok=True)
            app.logger.exception("Upload processing failed")
            flash("The file could not be processed. Try another file or enter the details manually.", "error")
            return redirect(url_for("new_record"))

    @app.route("/records/create", methods=["POST"])
    @login_required
    def create_record():
        values = record_form_values(request.form)
        try:
            pending, cost = validate_record_values(values)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("record_form.html", page_title="Add a health record", values=values,
                                   mode="create", upload_warning=None), 400
        attachment_path = ""
        original_filename = ""
        source_type = "manual"
        if pending:
            stage_dir = Path(app.config["UPLOAD_FOLDER"]) / ".staging"
            stage_path = stage_dir / pending
            if not stage_path.is_file() or stage_path.name != pending:
                flash("The uploaded file expired. Please upload it again.", "error")
                return render_template("record_form.html", page_title="Add a health record", values=values,
                                       mode="create", upload_warning=None), 400
            attachment_path = uuid.uuid4().hex + "." + pending.rsplit(".", 1)[-1]
            original_filename = clean_text(session.get("pending_original_filename"), 240)
            source_type = "upload"
            stage_path.replace(Path(app.config["UPLOAD_FOLDER"]) / attachment_path)
        db = get_db()
        db.execute(
            """INSERT INTO records
               (user_id, patient_name, record_date, doctor_name, hospital_name, cost, category,
                severity, title, diagnosis, test_type, medications, notes, extracted_text,
                attachment_path, original_filename, source_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (current_user()["id"], values["patient_name"], values["record_date"], values["doctor_name"],
             values["hospital_name"], cost, values["category"], values["severity"], values["title"],
             values["diagnosis"], values["test_type"], values["medications"], values["notes"],
             values["extracted_text"], attachment_path, original_filename, source_type, iso_now()),
        )
        record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
        session.pop("pending_upload", None)
        session.pop("pending_original_filename", None)
        repeats = get_potential_repeats(current_user()["id"], 8)
        if values["test_type"] and any(r["latest"]["id"] == record_id or r["previous"]["id"] == record_id for r in repeats):
            flash("This record looks similar to a recent test. The hint is not proof of duplication—check with your clinician before repeating or skipping a test.", "info")
        flash("Record added to your health timeline.", "success")
        return redirect(url_for("record_detail", record_id=record_id))

    @app.route("/records/<int:record_id>")
    @login_required
    def record_detail(record_id: int):
        row = own_record(record_id)
        repeats = [r for r in get_potential_repeats(current_user()["id"], 20)
                   if row["id"] in (r["latest"]["id"], r["previous"]["id"])]
        return render_template("record_detail.html", page_title=row["title"], record=row, repeats=repeats)

    @app.route("/records/<int:record_id>/download")
    @login_required
    def download_record(record_id: int):
        row = own_record(record_id)
        if not row["attachment_path"]:
            abort(404)
        path = Path(app.config["UPLOAD_FOLDER"]) / row["attachment_path"]
        if not path.is_file():
            flash("The attachment is no longer available on this deployment.", "error")
            return redirect(url_for("record_detail", record_id=record_id))
        return send_from_directory(app.config["UPLOAD_FOLDER"], row["attachment_path"],
                                   as_attachment=True, download_name=row["original_filename"] or row["attachment_path"])

    @app.route("/records/<int:record_id>/edit")
    @login_required
    def edit_record(record_id: int):
        row = own_record(record_id)
        values = dict(row)
        values["pending_upload"] = ""
        values["cost"] = "" if row["cost"] is None else str(row["cost"])
        return render_template("edit_record.html", page_title="Edit health record", values=values, record=row)

    @app.route("/records/<int:record_id>/update", methods=["POST"])
    @login_required
    def update_record(record_id: int):
        own_record(record_id)
        values = record_form_values(request.form)
        try:
            _, cost = validate_record_values(values)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("edit_record", record_id=record_id))
        db = get_db()
        db.execute(
            """UPDATE records SET patient_name=?, record_date=?, doctor_name=?, hospital_name=?, cost=?,
               category=?, severity=?, title=?, diagnosis=?, test_type=?, medications=?, notes=?, extracted_text=?
               WHERE id=? AND user_id=?""",
            (values["patient_name"], values["record_date"], values["doctor_name"], values["hospital_name"], cost,
             values["category"], values["severity"], values["title"], values["diagnosis"], values["test_type"],
             values["medications"], values["notes"], values["extracted_text"], record_id, current_user()["id"]),
        )
        db.commit()
        flash("Record updated.", "success")
        return redirect(url_for("record_detail", record_id=record_id))

    @app.route("/records/<int:record_id>/delete", methods=["POST"])
    @login_required
    def delete_record(record_id: int):
        row = own_record(record_id)
        if row["attachment_path"]:
            (Path(app.config["UPLOAD_FOLDER"]) / row["attachment_path"]).unlink(missing_ok=True)
        db = get_db()
        db.execute("DELETE FROM records WHERE id = ? AND user_id = ?", (record_id, current_user()["id"]))
        db.commit()
        flash("Record deleted from your account.", "success")
        return redirect(url_for("records"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        db = get_db()
        if request.method == "POST":
            full_name = clean_text(request.form.get("full_name"), 120)
            if not full_name:
                flash("Name cannot be empty.", "error")
            else:
                db.execute(
                    """UPDATE users SET full_name=?, allergies=?, current_medications=?, chronic_conditions=?, emergency_contact=?
                       WHERE id=?""",
                    (full_name, clean_text(request.form.get("allergies"), 2000),
                     clean_text(request.form.get("current_medications"), 2000),
                     clean_text(request.form.get("chronic_conditions"), 2000),
                     clean_text(request.form.get("emergency_contact"), 200), current_user()["id"]),
                )
                db.commit()
                flash("Health profile updated.", "success")
                return redirect(url_for("profile"))
        user = db.execute("SELECT * FROM users WHERE id = ?", (current_user()["id"],)).fetchone()
        return render_template("profile.html", page_title="Health profile", user=user)

    @app.route("/emergency-card")
    @login_required
    def emergency_card():
        user = current_user()
        important = get_db().execute(
            "SELECT * FROM records WHERE user_id = ? AND severity IN ('High', 'Emergency') ORDER BY record_date DESC LIMIT 5",
            (user["id"],),
        ).fetchall()
        return render_template("emergency_card.html", page_title="Emergency summary", user=user, important=important, generated_on=date.today().isoformat())

    @app.route("/sharing", methods=["GET", "POST"])
    @login_required
    def sharing():
        db = get_db()
        user = current_user()
        if request.method == "POST":
            expires_choice = request.form.get("expires_in", "60")
            scope = request.form.get("scope", "10")
            durations = {"15": 15, "60": 60, "1440": 1440}
            scopes = {"5": 5, "10": 10, "all": 100000}
            if expires_choice not in durations or scope not in scopes:
                flash("Choose a valid expiry and record scope.", "error")
                return redirect(url_for("sharing"))
            count_active = db.execute(
                "SELECT COUNT(*) FROM share_links WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?",
                (user["id"], iso_now()),
            ).fetchone()[0]
            if count_active >= 10:
                flash("You have 10 active links. Revoke or wait for one to expire before creating another.", "error")
                return redirect(url_for("sharing"))
            token = secrets.token_urlsafe(32)
            created = utcnow()
            expires = created + timedelta(minutes=durations[expires_choice])
            scope_label = "All current records" if scope == "all" else f"Most recent {scopes[scope]} records"
            profile_snapshot = {
                "full_name": user["full_name"], "allergies": user["allergies"],
                "current_medications": user["current_medications"],
                "chronic_conditions": user["chronic_conditions"],
                "emergency_contact": user["emergency_contact"],
            }
            cursor = db.execute(
                """INSERT INTO share_links (user_id, token_hash, created_at, expires_at, scope_label, profile_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user["id"], hashlib.sha256(token.encode()).hexdigest(), created.isoformat(), expires.isoformat(),
                 scope_label, json.dumps(profile_snapshot)),
            )
            share_id = cursor.lastrowid
            limit = scopes[scope]
            rows = db.execute("SELECT id FROM records WHERE user_id = ? ORDER BY record_date DESC, id DESC LIMIT ?",
                              (user["id"], limit)).fetchall()
            for record in rows:
                db.execute("INSERT INTO share_records (share_id, record_id) VALUES (?, ?)", (share_id, record["id"]))
            db.execute("INSERT INTO share_access_logs (share_id, event, occurred_at) VALUES (?, 'created', ?)", (share_id, iso_now()))
            db.commit()
            new_url = url_for("public_share", token=token, _external=True)
            flash("SHARE_LINK_CREATED:" + new_url, "sharelink")
            return redirect(url_for("sharing"))
        links = db.execute(
            """SELECT sl.*,
                      (SELECT COUNT(*) FROM share_access_logs sal WHERE sal.share_id = sl.id AND sal.event = 'viewed') AS view_count,
                      (SELECT MAX(occurred_at) FROM share_access_logs sal WHERE sal.share_id = sl.id AND sal.event = 'viewed') AS last_viewed
               FROM share_links sl WHERE sl.user_id = ? ORDER BY sl.created_at DESC LIMIT 30""", (user["id"],)
        ).fetchall()
        return render_template("sharing.html", page_title="Share records safely", links=links, now=iso_now())

    @app.route("/sharing/<int:share_id>/revoke", methods=["POST"])
    @login_required
    def revoke_share(share_id: int):
        db = get_db()
        row = db.execute("SELECT * FROM share_links WHERE id = ? AND user_id = ?", (share_id, current_user()["id"])).fetchone()
        if row is None:
            abort(404)
        if row["revoked_at"] is None:
            db.execute("UPDATE share_links SET revoked_at = ? WHERE id = ?", (iso_now(), share_id))
            db.execute("INSERT INTO share_access_logs (share_id, event, occurred_at) VALUES (?, 'revoked', ?)", (share_id, iso_now()))
            db.commit()
            flash("Share link revoked. It will no longer open.", "success")
        else:
            flash("That link was already revoked.", "info")
        return redirect(url_for("sharing"))

    @app.route("/share/<token>")
    def public_share(token: str):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db = get_db()
        share = db.execute("SELECT * FROM share_links WHERE token_hash = ?", (token_hash,)).fetchone()
        if share is None or share["revoked_at"] or share["expires_at"] <= iso_now():
            return render_template("share_unavailable.html", page_title="Share link unavailable"), 410
        profile_snapshot = json.loads(share["profile_snapshot"])
        records_rows = db.execute(
            """SELECT r.* FROM records r JOIN share_records sr ON sr.record_id = r.id
               WHERE sr.share_id = ? ORDER BY r.record_date DESC, r.id DESC""", (share["id"],)
        ).fetchall()
        db.execute("INSERT INTO share_access_logs (share_id, event, occurred_at) VALUES (?, 'viewed', ?)", (share["id"], iso_now()))
        db.commit()
        return render_template("public_share.html", page_title="Shared health summary", share=share,
                               profile=profile_snapshot, records=records_rows)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html", page_title="Not found"), 404

    @app.errorhandler(413)
    def upload_too_large(_error):
        flash("That file is too large. The upload limit is 12 MB.", "error")
        return redirect(url_for("new_record")), 413

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=int(os.environ.get("PORT", "5000")))
