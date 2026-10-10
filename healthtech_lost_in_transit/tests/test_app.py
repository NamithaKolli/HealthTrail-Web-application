import hashlib
import sqlite3
from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"
    test_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "testing-secret-key",
        "DATABASE_PATH": str(db_path),
        "UPLOAD_FOLDER": str(upload_path),
        "SEED_DEMO": False,
        "SESSION_COOKIE_SECURE": False,
    })
    with test_app.app_context():
        db = sqlite3.connect(db_path)
        db.execute("INSERT INTO users (username, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                   ("alice", "Alice Example", generate_password_hash("password123"), datetime.utcnow().isoformat(timespec="seconds")))
        db.execute("INSERT INTO users (username, full_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                   ("bob", "Bob Example", generate_password_hash("password123"), datetime.utcnow().isoformat(timespec="seconds")))
        db.commit()
        db.close()
    yield test_app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username="alice"):
    return client.post("/login", data={"username": username, "password": "password123"}, follow_redirects=True)


def test_login_and_dashboard(client):
    response = login(client)
    assert response.status_code == 200
    assert b"Your health" in response.data or b"health timeline" in response.data.lower()


def test_record_isolation(client, app):
    login(client, "alice")
    response = client.post("/records/create", data={
        "patient_name": "Alice Example", "record_date": "2026-10-01", "doctor_name": "Dr Example",
        "hospital_name": "Example Clinic", "cost": "200", "category": "General / Other",
        "severity": "Low", "title": "Sample visit", "diagnosis": "A synthetic test record",
        "test_type": "", "medications": "", "notes": "test", "extracted_text": "", "pending_upload": "",
    }, follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        sess.clear()
    login(client, "bob")
    with app.app_context():
        from flask import g
        # Ownership is verified through the public route rather than accessing Alice's record by guessed ID.
    response = client.get("/records/1")
    assert response.status_code == 404


def test_share_link_can_be_revoked(client, app):
    login(client, "alice")
    client.post("/records/create", data={
        "patient_name": "Alice Example", "record_date": "2026-10-01", "doctor_name": "Dr Example",
        "hospital_name": "Example Clinic", "cost": "200", "category": "General / Other",
        "severity": "Low", "title": "Shared sample", "diagnosis": "Synthetic summary",
        "test_type": "", "medications": "", "notes": "sample", "extracted_text": "", "pending_upload": "",
    })
    client.post("/sharing", data={"scope": "5", "expires_in": "60"}, follow_redirects=True)
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE_PATH"])
        db.row_factory = sqlite3.Row
        share = db.execute("SELECT * FROM share_links ORDER BY id DESC LIMIT 1").fetchone()
        # Recover the bearer token from the URL shown in the redirected HTML flash.
        # The database stores only its hash, so the test issues its own deterministic token to test lifecycle.
        token = "unit-test-share-token"
        db.execute("UPDATE share_links SET token_hash = ? WHERE id = ?", (hashlib.sha256(token.encode()).hexdigest(), share["id"]))
        db.commit()
        share_id = share["id"]
        db.close()
    client.get("/share/" + token)
    assert client.get("/share/" + token).status_code == 200
    client.post(f"/sharing/{share_id}/revoke", follow_redirects=True)
    assert client.get("/share/" + token).status_code == 410


def test_search_page_requires_login(client):
    response = client.get("/records")
    assert response.status_code == 302
    assert "/login" in response.location
