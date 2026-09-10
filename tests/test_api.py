"""End-to-end API tests against an isolated SQLite database with mocked Supabase.

Supabase Auth and Storage are mocked at the service layer (auth_service and
image_service), so the suite runs without network access. ML predictions are
NOT tested — the model is not integrated (ml_service.process_image raises
NotImplementedError by design).

Coverage: health (envelope + db-down), login/me, invalid credentials, no
registration endpoint, auth-required routes, invalid tokens, scan
(success/invalid/oversize), inspection CRUD + filters, complaints (CRUD,
status enum, ownership, public inspection_id contract), dashboard, profile
(email from token, email not client-settable, role protected), cross-user data
isolation, malformed requests, database failure handling, error envelopes, and
.env.example credential safety.
"""
import io
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    # Re-import the app modules so each test gets a fresh engine on its own
    # tmp_path database and fresh module-level configuration.
    for name in [
        m
        for m in list(sys.modules)
        if m.split(".")[0] in ("main", "api", "services", "database", "schemas", "middleware", "utils")
    ]:
        del sys.modules[name]

    # Build the schema through the real Alembic migration (the same path
    # production uses), so the test DB matches the production schema.
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(project_root / "alembic.ini")), "head")

    import main as app_module

    from database.database import engine

    # --- Mock Supabase Auth + Storage -------------------------------------
    from services import auth_service, image_service

    users = {}  # email -> {"user_id", "email", "token"}

    def fake_sign_in(email, password):
        if password != "secret123":
            raise auth_service.InvalidCredentialsError("Invalid email or password")
        entry = users.get(email)
        if entry is None:
            entry = {
                "user_id": str(uuid.uuid4()),
                "email": email,
                "token": f"token-{uuid.uuid4().hex}",
            }
            users[email] = entry
        return {
            "access_token": entry["token"],
            "refresh_token": f"refresh-{entry['token']}",
            "expires_in": 3600,
            "token_type": "bearer",
            "user": {"id": entry["user_id"], "email": entry["email"]},
        }

    def fake_get_user(token):
        for entry in users.values():
            if entry["token"] == token:
                return {"user_id": entry["user_id"], "email": entry["email"]}
        raise auth_service.InvalidCredentialsError("Invalid or expired token")

    def fake_store_image(user_id, data, extension):
        return f"inspections/{user_id}/img{extension}"

    def fake_store_image_at_path(user_id, data, extension, storage_path):
        return storage_path

    def fake_download_image(storage_path):
        return PNG_BYTES

    monkeypatch.setattr(auth_service, "sign_in_with_password", fake_sign_in)
    monkeypatch.setattr(auth_service, "get_user_from_token", fake_get_user)
    monkeypatch.setattr(image_service, "store_image", fake_store_image)
    monkeypatch.setattr(image_service, "store_image_at_path", fake_store_image_at_path)
    monkeypatch.setattr(image_service, "download_image", fake_download_image)

    with TestClient(app_module.app) as c:
        yield c, users
    app_module.engine.dispose()


def _create_user(users, email):
    """Register a user in the mocked Supabase store."""
    users[email] = {
        "user_id": str(uuid.uuid4()),
        "email": email,
        "token": f"token-{uuid.uuid4().hex}",
    }
    return users[email]


def _login(client, email, password="secret123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return {"Authorization": f"Bearer {body['data']['access_token']}"}


# ---------------------------------------------------------------- health ---


def test_health(client):
    c, _ = client
    resp = c.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    # All endpoints must return the standard envelope including "message".
    assert "message" in body
    assert isinstance(body["message"], str)
    data = body["data"]
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_health_db_down(client, monkeypatch):
    c, _ = client
    from database import database

    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(database.engine, "connect", boom)
    resp = c.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["success"] is False
    assert body["error_code"] == "DB_UNAVAILABLE"
    assert "message" in body
    assert body["data"]["status"] == "degraded"


# ------------------------------------------------------------------ auth ---


def test_login_and_me(client):
    c, users = client
    _create_user(users, "a@x.com")
    resp = c.post("/api/auth/login", json={"email": "a@x.com", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"].startswith("token-")
    assert data["token_type"] == "bearer"
    assert data["refresh_token"]
    assert data["user_id"]
    assert data["email"] == "a@x.com"

    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["user_id"] == data["user_id"]
    assert me.json()["data"]["email"] == "a@x.com"


def test_login_invalid_credentials(client):
    c, _ = client
    resp = c.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False and body["error_code"] == "INVALID_CREDENTIALS"


def test_no_registration_endpoint(client):
    c, _ = client
    assert c.post("/api/auth/register", json={}).status_code in (404, 405)
    assert c.post("/api/auth/signup", json={}).status_code in (404, 405)


def test_protected_endpoints_require_auth(client):
    c, _ = client
    for method, url in [
        ("get", "/api/inspections"),
        ("get", "/api/dashboard"),
        ("get", "/api/profile"),
        ("get", "/api/complaints"),
        ("get", "/api/auth/me"),
        ("post", "/api/scan"),
    ]:
        resp = getattr(c, method)(url)
        assert resp.status_code == 401, url
        assert resp.json()["error_code"] == "UNAUTHORIZED"


def test_invalid_token_rejected(client):
    c, _ = client
    resp = c.get("/api/inspections", headers={"Authorization": "Bearer bogus-token"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "UNAUTHORIZED"


# ------------------------------------------------------------------ scan ---


def _scan(c, headers, name="label.png", data=PNG_BYTES, content_type="image/png", form=None):
    return c.post(
        "/api/scan",
        files={"image": (name, io.BytesIO(data), content_type)},
        data=form or {"product_name": "Test Chips", "product_category": "Food"},
        headers=headers,
    )


def test_scan_creates_pending_ml_inspection(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    resp = _scan(c, headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "PENDING_ML"
    assert data["ml_pending"] is True
    assert data["inspection_id"].startswith("INSP-")
    assert data["image_url"].startswith("https://test.supabase.co/storage/v1/object/public/")

    listed = c.get("/api/inspections", headers=headers).json()["data"]
    assert any(i["inspection_id"] == data["inspection_id"] for i in listed["items"])


def test_scan_validates_image_content(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")

    # Declared image/png but actual content is text -> rejected by magic bytes.
    resp = _scan(c, headers, data=b"hello world", content_type="image/png")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_IMAGE"

    # Unsupported declared type -> rejected.
    resp = _scan(c, headers, data=b"hello", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "UNSUPPORTED_IMAGE_TYPE"


def test_scan_rejects_oversize(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    resp = _scan(c, headers, data=b"\0" * (11 * 1024 * 1024))
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "IMAGE_TOO_LARGE"


# ------------------------------------------------------------ inspections ---


def test_inspection_flow(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")

    created = c.post(
        "/api/inspections",
        json={"product_name": "Juice", "product_category": "Beverage", "side_count": 2},
        headers=headers,
    )
    assert created.status_code == 200
    created_data = created.json()["data"]
    insp_id = created_data["inspection_id"]
    # inspection_time serializes without error (Time -> "HH:MM:SS").
    assert "inspection_time" in created_data

    listed = c.get("/api/inspections", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()["data"]
    assert payload["total"] >= 1 and any(i["inspection_id"] == insp_id for i in payload["items"])

    detail = c.get(f"/api/inspections/{insp_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["product_name"] == "Juice"

    # No ML yet -> no extracted info, empty compliance rules.
    assert c.get(f"/api/inspections/{insp_id}/extracted-info", headers=headers).status_code == 404
    comp = c.get(f"/api/inspections/{insp_id}/compliance", headers=headers)
    assert comp.status_code == 200
    assert comp.json()["data"]["rules"] == []

    filtered = c.get(
        "/api/inspections",
        params={"status": "COMPLIANT", "date_from": date.today()},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 0


def test_create_inspection_requires_product_name(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    resp = c.post("/api/inspections", json={}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["success"] is False
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


def test_multi_side_inspection_requires_exact_capture_set(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    created = c.post(
        "/api/inspections",
        json={"product_type": "carton", "side_count": 2},
        headers=headers,
    )
    inspection_id = created.json()["data"]["inspection_id"]

    invalid_side = c.post(
        f"/api/inspections/{inspection_id}/images",
        files={"image": ("left.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"side": "left"},
        headers=headers,
    )
    assert invalid_side.status_code == 422
    assert invalid_side.json()["error_code"] == "INVALID_SIDE"

    front = c.post(
        f"/api/inspections/{inspection_id}/images",
        files={"image": ("front.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"side": "front"},
        headers=headers,
    )
    assert front.status_code == 200
    assert "/object/public/" in front.json()["data"]["public_url"]

    incomplete = c.post(f"/api/inspections/{inspection_id}/process", headers=headers)
    assert incomplete.status_code == 422
    assert incomplete.json()["error_code"] == "INCOMPLETE_CAPTURE"

    back = c.post(
        f"/api/inspections/{inspection_id}/images",
        files={"image": ("back.png", io.BytesIO(PNG_BYTES), "image/png")},
        data={"side": "back"},
        headers=headers,
    )
    assert back.status_code == 200

    process = c.post(f"/api/inspections/{inspection_id}/process", headers=headers)
    assert process.status_code == 200
    assert process.json()["data"]["status"] == "PENDING_ML"


# -------------------------------------------------------------- complaints ---


def test_complaint_flow(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")

    created = c.post(
        "/api/complaints",
        json={
            "complaint_title": "Wrong MRP",
            "description": "d",
            "category": "Labeling",
            "priority": "HIGH",
        },
        headers=headers,
    )
    assert created.status_code == 200
    cid = created.json()["data"]["complaint_id"]
    assert cid.startswith("CMP-")

    assert c.get("/api/complaints", headers=headers).json()["data"]["total"] == 1

    detail = c.get(f"/api/complaints/{cid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "OPEN"

    patched = c.patch(f"/api/complaints/{cid}", json={"status": "UNDER_REVIEW"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["data"]["status"] == "UNDER_REVIEW"

    assert c.get("/api/complaints?status=resolved", headers=headers).json()["data"]["total"] == 0

    # Invalid status rejected by the Literal type.
    bad = c.patch(f"/api/complaints/{cid}", json={"status": "BOGUS"}, headers=headers)
    assert bad.status_code == 422
    assert bad.json()["error_code"] == "VALIDATION_ERROR"


def test_complaint_inspection_id_is_public(client):
    """ComplaintOut.inspection_id must be the public INSP-XXXXXXXX identifier."""
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")

    # Create an inspection; get its public id.
    insp = c.post(
        "/api/inspections", json={"product_name": "Biscuit", "side_count": 2}, headers=headers
    ).json()["data"]
    public_insp_id = insp["inspection_id"]
    assert public_insp_id.startswith("INSP-")

    # Link a complaint to that inspection using the public id.
    resp = c.post(
        "/api/complaints",
        json={"complaint_title": "MRP mismatch", "inspection_id": public_insp_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    cdata = resp.json()["data"]

    # inspection_id in the response must be the public INSP-... id, not a UUID.
    assert cdata["inspection_id"] == public_insp_id
    assert cdata["inspection_id"].startswith("INSP-")

    # Verify the same value is returned on GET and PATCH.
    cid = cdata["complaint_id"]
    get_data = c.get(f"/api/complaints/{cid}", headers=headers).json()["data"]
    assert get_data["inspection_id"] == public_insp_id

    patch_data = c.patch(
        f"/api/complaints/{cid}", json={"status": "UNDER_REVIEW"}, headers=headers
    ).json()["data"]
    assert patch_data["inspection_id"] == public_insp_id

    # Complaint with no inspection: inspection_id must be null.
    no_insp = c.post(
        "/api/complaints", json={"complaint_title": "Standalone"}, headers=headers
    ).json()["data"]
    assert no_insp["inspection_id"] is None


def test_complaint_references_owned_inspection(client):
    c, users = client
    _create_user(users, "a@x.com")
    _create_user(users, "b@x.com")
    ha, hb = _login(c, "a@x.com"), _login(c, "b@x.com")

    insp = c.post("/api/inspections", json={"product_name": "X", "side_count": 2}, headers=ha).json()["data"]
    public_insp_id = insp["inspection_id"]

    # Same user: allowed; response inspection_id must be the public INSP-... id.
    resp = c.post(
        "/api/complaints",
        json={"complaint_title": "T", "inspection_id": public_insp_id},
        headers=ha,
    )
    assert resp.status_code == 200
    # The response now returns the public id, not the internal UUID.
    assert resp.json()["data"]["inspection_id"] == public_insp_id

    # Other user referencing the same inspection: 404.
    denied = c.post(
        "/api/complaints",
        json={"complaint_title": "T", "inspection_id": public_insp_id},
        headers=hb,
    )
    assert denied.status_code == 404


# ------------------------------------------------- dashboard + profile -----


def test_dashboard_and_profile(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    _scan(c, headers)
    c.post("/api/complaints", json={"complaint_title": "T"}, headers=headers)

    dash = c.get("/api/dashboard", headers=headers)
    assert dash.status_code == 200
    data = dash.json()["data"]
    assert data["total_inspections"] == 1
    assert data["total_complaints"] == 1
    assert data["pending_complaints"] == 1
    assert data["reviewed_complaints"] == 0
    assert len(data["recent_inspections"]) == 1

    profile = c.get("/api/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["data"]["user_id"]

    updated = c.patch("/api/profile", json={"full_name": "Renamed"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["full_name"] == "Renamed"


def test_profile_email_from_token(client):
    """GET /api/profile must return the email from the authenticated Supabase token."""
    c, users = client
    _create_user(users, "alice@example.com")
    headers = _login(c, "alice@example.com")

    profile = c.get("/api/profile", headers=headers)
    assert profile.status_code == 200
    data = profile.json()["data"]
    assert data["email"] == "alice@example.com"

    # PATCH /api/profile preserves the token email.
    patched = c.patch("/api/profile", json={"full_name": "Alice"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["data"]["email"] == "alice@example.com"


def test_profile_email_not_client_settable(client):
    """Clients must not be able to set or change the profile email field."""
    c, users = client
    _create_user(users, "bob@example.com")
    headers = _login(c, "bob@example.com")

    # email is not in ProfileUpdate (extra="forbid") -> 422.
    resp = c.patch("/api/profile", json={"email": "hacker@evil.com"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"

    # Profile email is still the token email, not the attempted override.
    profile = c.get("/api/profile", headers=headers)
    assert profile.json()["data"]["email"] == "bob@example.com"


def test_profile_cannot_change_role(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    # role is not client-updatable: ProfileUpdate forbids extra fields -> 422.
    resp = c.patch("/api/profile", json={"role": "admin"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"


# ------------------------------------------------------- data isolation -----


def test_user_isolation(client):
    c, users = client
    _create_user(users, "a@x.com")
    _create_user(users, "b@x.com")
    ha, hb = _login(c, "a@x.com"), _login(c, "b@x.com")

    scan_a = _scan(c, ha).json()["data"]
    insp_a = c.post("/api/inspections", json={"product_name": "A product", "side_count": 2}, headers=ha).json()["data"]
    comp_a = c.post("/api/complaints", json={"complaint_title": "A complaint"}, headers=ha).json()["data"]

    # User B sees none of user A's data.
    assert c.get("/api/inspections", headers=hb).json()["data"]["total"] == 0
    assert c.get("/api/complaints", headers=hb).json()["data"]["total"] == 0
    assert c.get(f"/api/inspections/{insp_a['inspection_id']}", headers=hb).status_code == 404
    assert c.get(f"/api/inspections/{scan_a['inspection_id']}/compliance", headers=hb).status_code == 404
    assert c.get(f"/api/inspections/{scan_a['inspection_id']}/extracted-info", headers=hb).status_code == 404
    assert c.get(f"/api/complaints/{comp_a['complaint_id']}", headers=hb).status_code == 404
    assert (
        c.patch(
            f"/api/complaints/{comp_a['complaint_id']}", json={"status": "RESOLVED"}, headers=hb
        ).status_code
        == 404
    )
    assert c.get("/api/dashboard", headers=hb).json()["data"]["total_inspections"] == 0
    profile_a = c.get("/api/profile", headers=ha).json()["data"]
    profile_b = c.get("/api/profile", headers=hb).json()["data"]
    assert profile_a["user_id"] != profile_b["user_id"]
    # Each user's profile email matches their own token.
    assert profile_a["email"] == "a@x.com"
    assert profile_b["email"] == "b@x.com"


# ------------------------------------------------- error envelope + misc ----


def test_malformed_request_uses_error_envelope(client):
    c, users = client
    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    resp = c.post("/api/complaints", json={"complaint_title": ""}, headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False and body["data"] is None
    assert body["error_code"] == "VALIDATION_ERROR"


def test_error_envelope(client):
    c, users = client
    resp = c.get("/api/inspections/INSP-DOESNOTEXIST")
    assert resp.status_code == 401  # auth check happens before existence

    _create_user(users, "a@x.com")
    headers = _login(c, "a@x.com")
    resp = c.get("/api/inspections/INSP-DOESNOTEXIST", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) >= {"success", "data", "message", "error_code"}
    assert body["success"] is False and body["data"] is None


# ----------------------------------------------- .env.example safety ------


def test_env_example_has_no_real_credentials():
    """.env.example must contain only safe placeholder values — no real secrets."""
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    assert env_example.exists(), ".env.example must exist"
    content = env_example.read_text()

    # All four required variables must have placeholder entries.
    assert "SUPABASE_URL=" in content
    assert "SUPABASE_ANON_KEY=" in content
    assert "SUPABASE_SERVICE_ROLE_KEY=" in content
    assert "DATABASE_URL=" in content

    # Must NOT contain the previously leaked real database password.
    assert "Vinay811200" not in content, "Real DB password found in .env.example"
    # Must NOT contain the real Supabase project reference.
    assert "yxyjbkimaamwkvcghccg" not in content, "Real project ref found in .env.example"
    # The DATABASE_URL entry must use a placeholder, not a real host.
    assert "YOUR_DB_PASSWORD" in content
    assert "YOUR_PROJECT_REF" in content
