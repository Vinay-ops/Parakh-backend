"""Admin API tests.

Tests admin authentication, authorization, inspector CRUD, duplicate handling,
inspector listing/pagination, inspection listing (all users), inspection detail,
cross-inspector access denial, complaint listing, and compliance access.

Uses the same SQLite-based test harness as test_api.py to run fully offline
without any Supabase network calls.
"""
import io
import sys
import uuid
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
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test_admin.db'}")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("ALLOWED_ORIGINS", "")

    for name in [
        m
        for m in list(sys.modules)
        if m.split(".")[0] in ("main", "api", "services", "database", "schemas", "middleware", "utils")
    ]:
        del sys.modules[name]

    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(project_root / "alembic.ini")), "head")

    import main as app_module
    from services import auth_service, image_service

    # Shared mocked user store: email -> {user_id, email, token}
    users = {}

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

    # Inspector creation uses create_user_with_service_role — mock it to create
    # an entry in the shared users store.
    def fake_create_user_with_service_role(email, password):
        if email in users:
            raise auth_service.UserAlreadyExistsError(f"User '{email}' already exists")
        uid = str(uuid.uuid4())
        users[email] = {
            "user_id": uid,
            "email": email,
            "token": f"token-{uuid.uuid4().hex}",
        }
        return {"id": uid, "email": email}

    def fake_delete_user_with_service_role(user_id):
        to_remove = [e for e in users if users[e]["user_id"] == user_id]
        for key in to_remove:
            del users[key]

    def fake_store_image_at_path(user_id, data, extension, storage_path):
        return storage_path

    def fake_download_image(storage_path):
        return PNG_BYTES

    def fake_store_image(user_id, data, extension):
        return f"inspections/{user_id}/img{extension}"

    monkeypatch.setattr(auth_service, "sign_in_with_password", fake_sign_in)
    monkeypatch.setattr(auth_service, "get_user_from_token", fake_get_user)
    monkeypatch.setattr(auth_service, "create_user_with_service_role", fake_create_user_with_service_role)
    monkeypatch.setattr(auth_service, "delete_user_with_service_role", fake_delete_user_with_service_role)
    monkeypatch.setattr(image_service, "store_image", fake_store_image)
    monkeypatch.setattr(image_service, "store_image_at_path", fake_store_image_at_path)
    monkeypatch.setattr(image_service, "download_image", fake_download_image)

    with TestClient(app_module.app) as c:
        yield c, users
    app_module.engine.dispose()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _register_and_login(client, users, email, role=None):
    """Create a user in mocked Supabase, login, optionally set DB profile role."""
    c, _ = client
    if email not in users:
        users[email] = {
            "user_id": str(uuid.uuid4()),
            "email": email,
            "token": f"token-{uuid.uuid4().hex}",
        }
    resp = c.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    if role:
        # Touch the profile endpoint to ensure the profile row is created
        c.get("/api/profile", headers=headers)
        # Then update the role directly via the DB (bypassing the no-role-update rule)
        from database.database import SessionLocal
        from database.models import Profile
        db = SessionLocal()
        try:
            p = db.query(Profile).filter(Profile.user_id == users[email]["user_id"]).first()
            if p:
                p.role = role
                db.commit()
        finally:
            db.close()

    return headers


def _make_admin(client, users, email="admin@example.com"):
    return _register_and_login(client, users, email, role="admin")


def _make_inspector_user(client, users, email):
    return _register_and_login(client, users, email)


# ── Admin authentication ──────────────────────────────────────────────────────

def test_admin_endpoint_requires_authentication(client):
    c, _ = client
    endpoints = [
        ("get",   "/api/admin/dashboard"),
        ("get",   "/api/admin/inspectors"),
        ("post",  "/api/admin/inspectors"),
        ("get",   "/api/admin/inspections"),
        ("get",   "/api/admin/complaints"),
    ]
    for method, url in endpoints:
        resp = getattr(c, method)(url)
        assert resp.status_code == 401, f"{method.upper()} {url} should be 401, got {resp.status_code}"


def test_non_admin_user_cannot_access_admin_endpoints(client):
    """Inspector (role=inspector) must not access admin endpoints — 403."""
    c, users = client
    headers = _make_inspector_user(client, users, "inspector@x.com")
    # Touch profile to create a profile row
    c.get("/api/profile", headers=headers)

    for method, url in [
        ("get",  "/api/admin/dashboard"),
        ("get",  "/api/admin/inspectors"),
        ("get",  "/api/admin/inspections"),
        ("get",  "/api/admin/complaints"),
    ]:
        resp = getattr(c, method)(url, headers=headers)
        assert resp.status_code == 403, f"{method.upper()} {url} should be 403, got {resp.status_code}"
        assert resp.json()["error_code"] == "FORBIDDEN"


def test_admin_with_role_can_access_admin_dashboard(client):
    c, users = client
    headers = _make_admin(client, users)
    resp = c.get("/api/admin/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_inspectors" in data
    assert "total_inspections" in data
    assert "compliant_inspections" in data


# ── Inspector creation ────────────────────────────────────────────────────────

def test_admin_can_create_inspector(client):
    c, users = client
    headers = _make_admin(client, users)
    payload = {
        "full_name": "Rajesh Kumar",
        "email": "rajesh@dept.gov.in",
        "password": "StrongPass1!",
        "employee_id": "EMP-001",
        "department": "Food Safety",
        "phone": "+91 98765 43210",
        "role": "inspector",
        "active": True,
    }
    resp = c.post("/api/admin/inspectors", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["full_name"] == "Rajesh Kumar"
    assert data["email"] == "rajesh@dept.gov.in"
    assert data["employee_id"] == "EMP-001"
    assert data["department"] == "Food Safety"
    assert data["active"] is True
    assert data["role"] == "inspector"
    # Password must NOT appear in the response
    assert "password" not in data
    # user_id must be a real UUID (created in mock Supabase)
    assert data["user_id"]


def test_create_inspector_duplicate_email_rejected(client):
    c, users = client
    headers = _make_admin(client, users)
    payload = {"full_name": "A", "email": "dup@x.com", "password": "Passw0rd!"}
    c.post("/api/admin/inspectors", json=payload, headers=headers)
    resp = c.post("/api/admin/inspectors", json=payload, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "DUPLICATE_EMAIL"


def test_create_inspector_duplicate_employee_id_rejected(client):
    c, users = client
    headers = _make_admin(client, users)
    c.post("/api/admin/inspectors", json={"full_name": "A", "email": "a1@x.com", "password": "Passw0rd!", "employee_id": "EMP-DUP"}, headers=headers)
    resp = c.post("/api/admin/inspectors", json={"full_name": "B", "email": "b1@x.com", "password": "Passw0rd!", "employee_id": "EMP-DUP"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "DUPLICATE_EMPLOYEE_ID"


def test_create_inspector_missing_required_fields(client):
    c, users = client
    headers = _make_admin(client, users)
    # Missing password
    resp = c.post("/api/admin/inspectors", json={"full_name": "A", "email": "x@x.com"}, headers=headers)
    assert resp.status_code == 422

    # Missing email
    resp = c.post("/api/admin/inspectors", json={"full_name": "A", "password": "Passw0rd!"}, headers=headers)
    assert resp.status_code == 422

    # Missing full_name
    resp = c.post("/api/admin/inspectors", json={"email": "y@x.com", "password": "Passw0rd!"}, headers=headers)
    assert resp.status_code == 422


def test_create_inspector_weak_password_rejected(client):
    c, users = client
    headers = _make_admin(client, users)
    resp = c.post("/api/admin/inspectors", json={"full_name": "A", "email": "x@x.com", "password": "short"}, headers=headers)
    assert resp.status_code == 422


# ── Inspector listing ─────────────────────────────────────────────────────────

def test_admin_can_list_inspectors(client):
    c, users = client
    headers = _make_admin(client, users)
    c.post("/api/admin/inspectors", json={"full_name": "Alice", "email": "alice@x.com", "password": "Passw0rd!", "department": "Food"}, headers=headers)
    c.post("/api/admin/inspectors", json={"full_name": "Bob",   "email": "bob@x.com",   "password": "Passw0rd!", "department": "Weights"}, headers=headers)

    resp = c.get("/api/admin/inspectors", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2
    assert "items" in data


def test_inspector_list_search_filter(client):
    c, users = client
    headers = _make_admin(client, users)
    c.post("/api/admin/inspectors", json={"full_name": "Unique Name XYZ", "email": "uniq@x.com", "password": "Passw0rd!"}, headers=headers)
    c.post("/api/admin/inspectors", json={"full_name": "Other", "email": "other@x.com", "password": "Passw0rd!"}, headers=headers)

    resp = c.get("/api/admin/inspectors?search=Unique+Name+XYZ", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["full_name"] == "Unique Name XYZ"


def test_inspector_list_active_filter(client):
    c, users = client
    headers = _make_admin(client, users)
    created = c.post("/api/admin/inspectors", json={"full_name": "Active One", "email": "active1@x.com", "password": "Passw0rd!", "active": True}, headers=headers).json()["data"]
    c.post("/api/admin/inspectors", json={"full_name": "Inactive One", "email": "inactive1@x.com", "password": "Passw0rd!", "active": False}, headers=headers)

    active_resp = c.get("/api/admin/inspectors?active=true", headers=headers)
    assert active_resp.status_code == 200
    active_items = active_resp.json()["data"]["items"]
    assert all(i["active"] for i in active_items)

    inactive_resp = c.get("/api/admin/inspectors?active=false", headers=headers)
    assert inactive_resp.status_code == 200
    inactive_items = inactive_resp.json()["data"]["items"]
    assert all(not i["active"] for i in inactive_items)


# ── Inspector activation/deactivation ────────────────────────────────────────

def test_admin_can_activate_deactivate_inspector(client):
    c, users = client
    headers = _make_admin(client, users)
    created = c.post("/api/admin/inspectors", json={"full_name": "Toggle", "email": "toggle@x.com", "password": "Passw0rd!", "active": True}, headers=headers).json()["data"]
    iid = created["id"]

    deactivated = c.patch(f"/api/admin/inspectors/{iid}", json={"active": False}, headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["active"] is False

    reactivated = c.patch(f"/api/admin/inspectors/{iid}", json={"active": True}, headers=headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["active"] is True


def test_admin_can_update_inspector_profile(client):
    c, users = client
    headers = _make_admin(client, users)
    created = c.post("/api/admin/inspectors", json={"full_name": "Old Name", "email": "upd@x.com", "password": "Passw0rd!"}, headers=headers).json()["data"]
    iid = created["id"]

    updated = c.patch(f"/api/admin/inspectors/{iid}", json={"full_name": "New Name", "department": "Legal Metrology"}, headers=headers)
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["full_name"] == "New Name"
    assert data["department"] == "Legal Metrology"


def test_inspector_update_does_not_allow_extra_fields(client):
    c, users = client
    headers = _make_admin(client, users)
    created = c.post("/api/admin/inspectors", json={"full_name": "X", "email": "extra@x.com", "password": "Passw0rd!"}, headers=headers).json()["data"]
    iid = created["id"]
    resp = c.patch(f"/api/admin/inspectors/{iid}", json={"nonexistent_field": "val"}, headers=headers)
    assert resp.status_code == 422


# ── Admin inspection listing ──────────────────────────────────────────────────

def _create_inspection_for_user(c, headers):
    return c.post(
        "/api/inspections",
        json={"product_name": "Test Product", "side_count": 2},
        headers=headers,
    ).json()["data"]["inspection_id"]


def test_admin_sees_all_inspections(client):
    """Admin must see inspections from all users, not just their own."""
    c, users = client
    admin_headers = _make_admin(client, users)

    insp1_headers = _make_inspector_user(client, users, "insp1@x.com")
    insp2_headers = _make_inspector_user(client, users, "insp2@x.com")

    _create_inspection_for_user(c, insp1_headers)
    _create_inspection_for_user(c, insp2_headers)

    resp = c.get("/api/admin/inspections", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2


def test_admin_inspection_detail_accessible_unscoped(client):
    """Admin can open an inspection that belongs to any inspector."""
    c, users = client
    admin_headers = _make_admin(client, users)
    insp_headers  = _make_inspector_user(client, users, "insp3@x.com")

    insp_id = _create_inspection_for_user(c, insp_headers)

    resp = c.get(f"/api/admin/inspections/{insp_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["inspection"]["inspection_id"] == insp_id
    assert "images" in data
    assert "extracted_info" in data
    assert "compliance" in data


def test_admin_inspection_includes_inspector_info(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    # Create an inspector and set their profile name
    insp_headers = _make_inspector_user(client, users, "insp4@x.com")
    c.patch("/api/profile", json={"full_name": "Field Inspector"}, headers=insp_headers)
    insp_id = _create_inspection_for_user(c, insp_headers)

    resp = c.get(f"/api/admin/inspections/{insp_id}", headers=admin_headers)
    assert resp.status_code == 200
    inspector_data = resp.json()["data"]["inspector"]
    # email should be present
    assert inspector_data["email"] == "insp4@x.com"


def test_admin_inspection_filter_by_status(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    insp_headers = _make_inspector_user(client, users, "insp5@x.com")
    _create_inspection_for_user(c, insp_headers)

    resp = c.get("/api/admin/inspections?status=COMPLIANT", headers=admin_headers)
    assert resp.status_code == 200
    # No COMPLIANT inspections yet
    assert resp.json()["data"]["total"] == 0

    resp2 = c.get("/api/admin/inspections?status=CREATED", headers=admin_headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["total"] >= 1


def test_admin_inspection_search(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    insp_headers = _make_inspector_user(client, users, "insp6@x.com")
    c.post("/api/inspections", json={"product_name": "Unique Biscuit Brand", "side_count": 2}, headers=insp_headers)

    resp = c.get("/api/admin/inspections?search=Unique+Biscuit+Brand", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any("Unique Biscuit Brand" in (i.get("product_name") or "") for i in items)


# ── Cross-inspector access denial ────────────────────────────────────────────

def test_inspector_cannot_access_another_inspectors_data(client):
    """Inspector A's token must not retrieve Inspector B's inspections."""
    c, users = client
    ha = _make_inspector_user(client, users, "a@x.com")
    hb = _make_inspector_user(client, users, "b@x.com")

    insp_a = _create_inspection_for_user(c, ha)

    # Inspector B tries to get Inspector A's inspection via inspector endpoint
    resp = c.get(f"/api/inspections/{insp_a}", headers=hb)
    assert resp.status_code == 404


def test_inspector_cannot_access_admin_endpoints(client):
    c, users = client
    hb = _make_inspector_user(client, users, "inspector@x.com")
    c.get("/api/profile", headers=hb)  # create profile row

    resp = c.get("/api/admin/dashboard", headers=hb)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN"


# ── Complaints ────────────────────────────────────────────────────────────────

def test_admin_can_list_all_complaints(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    ha = _make_inspector_user(client, users, "ca@x.com")
    hb = _make_inspector_user(client, users, "cb@x.com")

    c.post("/api/complaints", json={"complaint_title": "Complaint from A"}, headers=ha)
    c.post("/api/complaints", json={"complaint_title": "Complaint from B"}, headers=hb)

    resp = c.get("/api/admin/complaints", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 2


def test_admin_complaint_filter_by_status(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    h = _make_inspector_user(client, users, "cc@x.com")

    created = c.post("/api/complaints", json={"complaint_title": "T"}, headers=h).json()["data"]
    cid = created["complaint_id"]
    c.patch(f"/api/complaints/{cid}", json={"status": "RESOLVED"}, headers=h)

    resp = c.get("/api/admin/complaints?status=RESOLVED", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert any(i["complaint_id"] == cid for i in items)

    resp2 = c.get("/api/admin/complaints?status=OPEN", headers=admin_headers)
    open_ids = [i["complaint_id"] for i in resp2.json()["data"]["items"]]
    assert cid not in open_ids


# ── Admin dashboard stats accuracy ───────────────────────────────────────────

def test_admin_dashboard_reflects_real_counts(client):
    c, users = client
    admin_headers = _make_admin(client, users)

    # Create 2 inspectors
    c.post("/api/admin/inspectors", json={"full_name": "I1", "email": "d1@x.com", "password": "Passw0rd!", "active": True}, headers=admin_headers)
    c.post("/api/admin/inspectors", json={"full_name": "I2", "email": "d2@x.com", "password": "Passw0rd!", "active": False}, headers=admin_headers)

    # Create an inspection from inspector I1
    h1 = _make_inspector_user(client, users, "d1@x.com")
    _create_inspection_for_user(c, h1)

    stats = c.get("/api/admin/dashboard", headers=admin_headers).json()["data"]

    # total_inspectors includes all profiles (admin + inspectors)
    assert stats["total_inspectors"] >= 3  # admin + 2 inspectors
    assert stats["active_inspectors"] >= 1
    assert stats["total_inspections"] >= 1
    assert isinstance(stats["recent_inspections"], list)


# ── Security: no service-role key in responses ────────────────────────────────

def test_no_sensitive_config_in_responses(client):
    c, users = client
    admin_headers = _make_admin(client, users)

    for resp in [
        c.get("/api/admin/dashboard", headers=admin_headers),
        c.get("/api/admin/inspectors", headers=admin_headers),
        c.get("/api/admin/inspections", headers=admin_headers),
    ]:
        body_text = resp.text
        assert "service_role" not in body_text.lower()
        assert "test-service-role-key" not in body_text
        assert "DATABASE_URL" not in body_text
        assert "postgresql://" not in body_text


# ── Inspector pagination ──────────────────────────────────────────────────────

def test_inspector_list_pagination(client):
    c, users = client
    admin_headers = _make_admin(client, users)

    for i in range(5):
        c.post("/api/admin/inspectors", json={
            "full_name": f"Inspector {i}",
            "email": f"paginsp{i}@x.com",
            "password": "Passw0rd!",
        }, headers=admin_headers)

    page1 = c.get("/api/admin/inspectors?page=1&page_size=3", headers=admin_headers)
    assert page1.status_code == 200
    p1_data = page1.json()["data"]
    assert len(p1_data["items"]) <= 3
    assert p1_data["page"] == 1

    page2 = c.get("/api/admin/inspectors?page=2&page_size=3", headers=admin_headers)
    assert page2.status_code == 200
    p2_data = page2.json()["data"]
    assert p2_data["page"] == 2

    # No overlap
    p1_ids = {i["id"] for i in p1_data["items"]}
    p2_ids = {i["id"] for i in p2_data["items"]}
    assert p1_ids.isdisjoint(p2_ids)


# ── Inspector not found ───────────────────────────────────────────────────────

def test_get_nonexistent_inspector_returns_404(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    fake_id = str(uuid.uuid4())
    resp = c.get(f"/api/admin/inspectors/{fake_id}", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"


def test_get_nonexistent_inspection_returns_404(client):
    c, users = client
    admin_headers = _make_admin(client, users)
    resp = c.get("/api/admin/inspections/INSP-NOTEXIST", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "NOT_FOUND"
