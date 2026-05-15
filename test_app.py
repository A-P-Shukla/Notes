"""
Comprehensive test suite for the Notes App API.

Uses an in-memory SQLite database so tests run instantly
without touching the dev database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import database
from database import get_db
from main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    Yields a TestClient wired to a fresh, in-memory SQLite database.
    Each test gets a completely clean database — zero bleed between tests.
    """
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    TestSession = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async def override_get_db():
        async with TestSession() as session:
            yield session

    # Patch the module-level engine so lifespan's init_db() creates tables
    # in the in-memory DB instead of the real one.
    original_engine = database.engine
    database.engine = test_engine
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    # Teardown
    database.engine = original_engine
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str, password: str = "securepass123"):
    """Helper — register a user and return the response."""
    return client.post("/register", json={"email": email, "password": password})


def _login(client: TestClient, email: str, password: str = "securepass123") -> str:
    """Helper — login and return the raw access_token string."""
    r = client.post("/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    """Helper — build an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def _create_note(client: TestClient, token: str, title: str = "Test", content: str = "Body"):
    """Helper — create a note and return the response."""
    return client.post("/notes", json={"title": title, "content": content}, headers=_auth(token))


# ---------------------------------------------------------------------------
# 1. User Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_success(self, client):
        """POST /register with valid data returns 201 and a message."""
        r = _register(client, "alice@example.com")
        assert r.status_code == 201
        body = r.json()
        assert "message" in body
        # Must NOT leak user object fields
        assert "id" not in body
        assert "email" not in body

    def test_register_duplicate_email(self, client):
        """Registering the same email twice returns 409."""
        _register(client, "alice@example.com")
        r = _register(client, "alice@example.com")
        assert r.status_code == 409

    def test_register_duplicate_case_insensitive(self, client):
        """Email uniqueness is case-insensitive."""
        _register(client, "alice@example.com")
        r = _register(client, "Alice@Example.com")
        assert r.status_code == 409

    def test_register_short_password_rejected(self, client):
        """Passwords shorter than 8 characters are rejected (422)."""
        r = _register(client, "weak@example.com", password="short")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 2. Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        """Valid credentials return 200 with an access_token."""
        _register(client, "alice@example.com")
        r = client.post("/login", json={"email": "alice@example.com", "password": "securepass123"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body

    def test_login_wrong_password(self, client):
        """Wrong password returns 401 with flat {"message": "Invalid email or password"}."""
        _register(client, "alice@example.com")
        r = client.post("/login", json={"email": "alice@example.com", "password": "wrongpassword"})
        assert r.status_code == 401
        body = r.json()
        assert body == {"message": "Invalid email or password"}
        # Must NOT be wrapped in {"detail": ...}
        assert "detail" not in body

    def test_login_nonexistent_user(self, client):
        """Login with an unregistered email returns 401 (not 404 — no user enumeration)."""
        r = client.post("/login", json={"email": "ghost@example.com", "password": "whatever1234"})
        assert r.status_code == 401

    def test_invalid_token_returns_flat_message(self, client):
        """A garbage Bearer token returns 401 with flat {"message": ...}, not {"detail": ...}."""
        r = client.get("/notes", headers={"Authorization": "Bearer garbage.token.here"})
        assert r.status_code == 401
        body = r.json()
        assert "message" in body
        assert "detail" not in body


# ---------------------------------------------------------------------------
# 3. Note Creation
# ---------------------------------------------------------------------------

class TestNoteCreation:
    def test_create_note_returns_201(self, client):
        """POST /notes returns 201 with the created note data."""
        _register(client, "alice@example.com")
        token = _login(client, "alice@example.com")
        r = _create_note(client, token, title="My Note", content="Hello world")
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "My Note"
        assert body["content"] == "Hello world"
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body
        # owner_id must not leak
        assert "owner_id" not in body

    def test_create_note_whitespace_title_rejected(self, client):
        """A whitespace-only title is rejected with 422."""
        _register(client, "alice@example.com")
        token = _login(client, "alice@example.com")
        r = _create_note(client, token, title="   ", content="valid content")
        assert r.status_code == 422

    def test_create_note_empty_content_rejected(self, client):
        """An empty content string is rejected with 422."""
        _register(client, "alice@example.com")
        token = _login(client, "alice@example.com")
        r = _create_note(client, token, title="Title", content="")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 4. Note Sharing
# ---------------------------------------------------------------------------

class TestNoteSharing:
    def test_share_note_success(self, client):
        """Owner can share a note; recipient can then read it."""
        _register(client, "owner@example.com")
        _register(client, "reader@example.com")
        owner_tok = _login(client, "owner@example.com")
        reader_tok = _login(client, "reader@example.com")

        note = _create_note(client, owner_tok, title="Shared Note", content="secret").json()
        note_id = note["id"]

        # Share
        r = client.post(
            f"/notes/{note_id}/share",
            json={"share_with_email": "reader@example.com"},
            headers=_auth(owner_tok),
        )
        assert r.status_code == 200
        assert r.json()["message"] == "Note shared successfully"

        # Reader can now GET the note
        r = client.get(f"/notes/{note_id}", headers=_auth(reader_tok))
        assert r.status_code == 200
        assert r.json()["title"] == "Shared Note"

    def test_share_with_nonexistent_user(self, client):
        """Sharing with an unregistered email returns 404."""
        _register(client, "owner@example.com")
        token = _login(client, "owner@example.com")
        note = _create_note(client, token).json()

        r = client.post(
            f"/notes/{note['id']}/share",
            json={"share_with_email": "ghost@example.com"},
            headers=_auth(token),
        )
        assert r.status_code == 404

    def test_share_with_self_blocked(self, client):
        """Owner cannot share a note with themselves."""
        _register(client, "owner@example.com")
        token = _login(client, "owner@example.com")
        note = _create_note(client, token).json()

        r = client.post(
            f"/notes/{note['id']}/share",
            json={"share_with_email": "owner@example.com"},
            headers=_auth(token),
        )
        assert r.status_code == 400

    def test_shared_user_cannot_reshare(self, client):
        """A user who received a shared note cannot re-share it."""
        _register(client, "owner@example.com")
        _register(client, "reader@example.com")
        _register(client, "third@example.com")
        owner_tok = _login(client, "owner@example.com")
        reader_tok = _login(client, "reader@example.com")

        note = _create_note(client, owner_tok).json()
        client.post(
            f"/notes/{note['id']}/share",
            json={"share_with_email": "reader@example.com"},
            headers=_auth(owner_tok),
        )

        # Reader tries to re-share with a third user
        r = client.post(
            f"/notes/{note['id']}/share",
            json={"share_with_email": "third@example.com"},
            headers=_auth(reader_tok),
        )
        assert r.status_code == 404  # Not the owner

    def test_shared_user_cannot_delete(self, client):
        """A user who received a shared note cannot delete it."""
        _register(client, "owner@example.com")
        _register(client, "reader@example.com")
        owner_tok = _login(client, "owner@example.com")
        reader_tok = _login(client, "reader@example.com")

        note = _create_note(client, owner_tok).json()
        client.post(
            f"/notes/{note['id']}/share",
            json={"share_with_email": "reader@example.com"},
            headers=_auth(owner_tok),
        )

        r = client.delete(f"/notes/{note['id']}", headers=_auth(reader_tok))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. IDOR Protection
# ---------------------------------------------------------------------------

class TestIDORProtection:
    def test_user_cannot_read_others_note(self, client):
        """User A gets 404 when fetching User B's private (unshared) note."""
        _register(client, "alice@example.com")
        _register(client, "bob@example.com")
        alice_tok = _login(client, "alice@example.com")
        bob_tok = _login(client, "bob@example.com")

        note = _create_note(client, alice_tok, title="Alice Private").json()

        r = client.get(f"/notes/{note['id']}", headers=_auth(bob_tok))
        assert r.status_code == 404

    def test_user_cannot_update_others_note(self, client):
        """User A gets 404 when trying to PUT User B's note."""
        _register(client, "alice@example.com")
        _register(client, "bob@example.com")
        alice_tok = _login(client, "alice@example.com")
        bob_tok = _login(client, "bob@example.com")

        note = _create_note(client, alice_tok).json()

        r = client.put(
            f"/notes/{note['id']}",
            json={"title": "Hacked", "content": "pwned"},
            headers=_auth(bob_tok),
        )
        assert r.status_code == 404

    def test_user_cannot_delete_others_note(self, client):
        """User A gets 404 when trying to DELETE User B's note."""
        _register(client, "alice@example.com")
        _register(client, "bob@example.com")
        alice_tok = _login(client, "alice@example.com")
        bob_tok = _login(client, "bob@example.com")

        note = _create_note(client, alice_tok).json()

        r = client.delete(f"/notes/{note['id']}", headers=_auth(bob_tok))
        assert r.status_code == 404

    def test_notes_list_only_shows_own_notes(self, client):
        """GET /notes only returns notes owned by or shared with the caller."""
        _register(client, "alice@example.com")
        _register(client, "bob@example.com")
        alice_tok = _login(client, "alice@example.com")
        bob_tok = _login(client, "bob@example.com")

        _create_note(client, alice_tok, title="Alice Note")
        _create_note(client, bob_tok, title="Bob Note")

        alice_notes = client.get("/notes", headers=_auth(alice_tok)).json()
        bob_notes = client.get("/notes", headers=_auth(bob_tok)).json()

        assert len(alice_notes) == 1
        assert alice_notes[0]["title"] == "Alice Note"
        assert len(bob_notes) == 1
        assert bob_notes[0]["title"] == "Bob Note"


# ---------------------------------------------------------------------------
# 6. Revision History
# ---------------------------------------------------------------------------

class TestRevisionHistory:
    def test_update_creates_revision(self, client):
        """Updating a note saves the previous state as a revision."""
        _register(client, "alice@example.com")
        token = _login(client, "alice@example.com")

        note = _create_note(client, token, title="V1 Title", content="V1 Content").json()
        note_id = note["id"]

        # Update the note
        client.put(
            f"/notes/{note_id}",
            json={"title": "V2 Title", "content": "V2 Content"},
            headers=_auth(token),
        )

        # Fetch revisions
        r = client.get(f"/notes/{note_id}/revisions", headers=_auth(token))
        assert r.status_code == 200
        revisions = r.json()
        assert len(revisions) == 1
        # The revision should contain the OLD content (V1), not the new
        assert revisions[0]["title"] == "V1 Title"
        assert revisions[0]["content"] == "V1 Content"

    def test_multiple_updates_create_multiple_revisions(self, client):
        """Each update appends a new revision entry."""
        _register(client, "alice@example.com")
        token = _login(client, "alice@example.com")

        note = _create_note(client, token, title="V1", content="C1").json()
        note_id = note["id"]

        client.put(f"/notes/{note_id}", json={"title": "V2", "content": "C2"}, headers=_auth(token))
        client.put(f"/notes/{note_id}", json={"title": "V3", "content": "C3"}, headers=_auth(token))

        revisions = client.get(f"/notes/{note_id}/revisions", headers=_auth(token)).json()
        assert len(revisions) == 2
        # Revisions ordered newest-first: V2 then V1
        assert revisions[0]["title"] == "V2"
        assert revisions[1]["title"] == "V1"

    def test_shared_user_cannot_see_revisions(self, client):
        """Revision history is owner-only; shared users get 404."""
        _register(client, "owner@example.com")
        _register(client, "reader@example.com")
        owner_tok = _login(client, "owner@example.com")
        reader_tok = _login(client, "reader@example.com")

        note = _create_note(client, owner_tok, title="Original").json()
        note_id = note["id"]

        # Create a revision
        client.put(
            f"/notes/{note_id}",
            json={"title": "Edited", "content": "new"},
            headers=_auth(owner_tok),
        )

        # Share the note
        client.post(
            f"/notes/{note_id}/share",
            json={"share_with_email": "reader@example.com"},
            headers=_auth(owner_tok),
        )

        # Reader tries to view revisions
        r = client.get(f"/notes/{note_id}/revisions", headers=_auth(reader_tok))
        assert r.status_code == 404
