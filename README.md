# FastAPI Notes App

**Live Deployment:** [Insert Render URL Here]

## Project Overview

FastAPI Notes App is an async, JWT-secured notes backend built for a backend engineering assignment with production-style concerns: strict response contracts, ownership-aware authorization, note sharing, search, pagination, test coverage, Docker support, and a custom audit-trail feature.

The backend stack is:

- **FastAPI** for the HTTP API and OpenAPI documentation
- **SQLAlchemy 2.0 async** for ORM and query construction
- **PostgreSQL + asyncpg** as the default database target
- **SQLite + aiosqlite** for fast local/test execution
- **Pydantic v2** for request and response validation
- **PyJWT** for signed Bearer access tokens
- **Docker** for containerized deployment
- **Pytest** for endpoint and security regression coverage

The application also serves a lightweight frontend at:

```text
GET /app
```

API documentation is available automatically through FastAPI:

```text
GET /docs
GET /openapi.json
```

## Custom Feature: Note Revision History (Audit Trail)

The custom feature is **Note Revision History (Audit Trail)**.

In fintech and robust systems, state mutation without an audit log is a vulnerability. I implemented an immutable revision history so every PUT request archives the previous state, preventing accidental data loss and ensuring data integrity.

When a note owner updates a note through:

```http
PUT /notes/{id}
```

the API first inserts the current note state into the `note_revisions` table before applying the update. Each revision stores:

- `id`
- `note_id`
- `title`
- `content`
- `updated_at`

Revision history is exposed through:

```http
GET /notes/{id}/revisions
```

In the current implementation, revision history is **owner-only**. Shared users can read the shared note itself, but they cannot view its audit trail. This keeps historical data access stricter than regular read access.

## Stretch Goals Completed

- **Pagination:** `GET /notes?skip=0&limit=10`
- **Search:** `GET /search?q=keyword` searches title and content
- **Note Sharing:** owners can share notes with registered users
- **Pytest Coverage:** tests cover auth, notes, sharing, IDOR protection, and revision history
- **Dockerization:** `Dockerfile` is included for containerized execution
- **Minimal Frontend:** static UI served from `/app`

## Security & Edge Case Handling

The API is designed to avoid common backend security mistakes, especially **IDOR (Insecure Direct Object Reference)**. Note read queries only return records where the current user is either:

- the note owner, or
- explicitly present in the `note_shares` association table for that note

Mutating operations are stricter:

- Only owners can update notes.
- Only owners can delete notes.
- Only owners can share notes.
- Revision history is owner-only.

JWTs are strictly validated before protected routes run. Invalid, missing, or malformed Bearer tokens return a flat `401` response body:

```json
{"message": "Invalid or missing token"}
```

Other notable edge-case handling:

- Login failures return exactly:

```json
{"message": "Invalid email or password"}
```

- Duplicate registration returns `409 Conflict`.
- Invalid emails are rejected by Pydantic.
- Registration passwords must be between 8 and 128 characters.
- Blank or whitespace-only note titles/content are rejected.
- Sharing with an unregistered email returns `404`.
- Sharing a note with yourself returns `400`.
- Unauthorized access to another user's note returns `404` instead of leaking resource existence.

## API Endpoints

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/about` | No | Assignment metadata and custom feature summary |
| `GET` | `/app` | No | Static frontend |
| `POST` | `/register` | No | Register a new user |
| `POST` | `/login` | No | Authenticate and receive an access token |
| `GET` | `/notes` | Yes | List owned and shared notes with pagination |
| `POST` | `/notes` | Yes | Create a note |
| `GET` | `/notes/{id}` | Yes | Fetch a note the user owns or has been shared |
| `PUT` | `/notes/{id}` | Yes | Owner-only note update with revision snapshot |
| `DELETE` | `/notes/{id}` | Yes | Owner-only note deletion |
| `POST` | `/notes/{id}/share` | Yes | Owner-only note sharing |
| `GET` | `/notes/{id}/revisions` | Yes | Owner-only revision history |
| `GET` | `/search?q=keyword` | Yes | Search owned and shared notes |

## Response Contract Highlights

Registration:

```http
POST /register
```

Successful response:

```json
{
  "message": "User registered successfully"
}
```

Login:

```http
POST /login
```

Successful response:

```json
{
  "access_token": "jwt-token"
}
```

Failed login response:

```json
{
  "message": "Invalid email or password"
}
```

Note sharing:

```http
POST /notes/{id}/share
```

Request body:

```json
{
  "share_with_email": "reader@example.com"
}
```

Successful response:

```json
{
  "message": "Note shared successfully"
}
```

## Local Setup: Docker

Build the image:

```bash
docker build -t Notes .
```

Run the container:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="sqlite+aiosqlite:///./notes.db" \
  -e SECRET_KEY="local-development-secret" \
  Notes
```

The API will be available at:

```text
http://localhost:8000
```

For PostgreSQL, provide a PostgreSQL async SQLAlchemy URL:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/notes" \
  -e SECRET_KEY="replace-me" \
  Notes
```

## Local Setup: Manual

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Activate it on macOS/Linux:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

For instant local SQLite execution:

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///./notes.db"
$env:SECRET_KEY="local-development-secret"
uvicorn main:app --reload
```

On macOS/Linux:

```bash
export DATABASE_URL="sqlite+aiosqlite:///./notes.db"
export SECRET_KEY="local-development-secret"
uvicorn main:app --reload
```

If you are using local PostgreSQL instead, the app defaults to:

```text
postgresql+asyncpg://postgres:postgres@localhost:5432/notes
```

You can override it with:

```bash
DATABASE_URL="postgresql+asyncpg://user:password@host:5432/database"
```

## Testing

Install test dependencies if they are not already available in your environment:

```bash
pip install pytest httpx
```

Run the test suite:

```bash
pytest
```

On Windows with the project virtual environment:

```powershell
.\venv\Scripts\python.exe -m pytest
```

The tests use an in-memory SQLite database, so they do not mutate the development database. Coverage includes:

- registration and duplicate-user handling
- login success and failure contracts
- JWT validation failures
- note creation and validation
- note sharing
- IDOR protection
- owner-only update/delete behavior
- revision history creation and access control

## Data Model

Core tables:

- `users`: registered users with unique normalized email addresses
- `notes`: note records owned by users
- `note_shares`: association table linking shared notes to users
- `note_revisions`: immutable snapshots of old note state before updates

The key authorization rule is enforced at query time for reads:

```text
note.owner_id == current_user.id
OR current_user.id exists in note_shares for that note
```

Owner-only operations perform stricter checks against `owner_id`.

## Project Structure

```text
.
|-- auth.py              # Password hashing, JWT creation, auth dependency
|-- database.py          # Async SQLAlchemy engine/session setup
|-- Dockerfile           # Container image definition
|-- main.py              # FastAPI app, middleware, exception handlers, static serving
|-- models.py            # SQLAlchemy ORM models and association table
|-- requirements.txt     # Runtime dependencies
|-- routes.py            # API routes and authorization-aware queries
|-- schemas.py           # Pydantic request/response schemas
|-- static/
|   `-- index.html       # Minimal frontend served at /app
`-- test_app.py          # Pytest API test suite
```

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/notes` | Async SQLAlchemy database URL |
| `SECRET_KEY` | `change-this-secret-key-for-production` | JWT signing secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |

For production or hosted deployment, always set a strong `SECRET_KEY` and a managed PostgreSQL `DATABASE_URL`.
