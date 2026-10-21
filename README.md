# Agentic AI Based IT Helpdesk Automation Platform

React + Vite frontend and a FastAPI backend with PostgreSQL-backed tickets. The AI Help Center calls Groq through the Python backend only. Knowledge-base article references are returned only when the backend retrieves a matching article. Chat and workflow examples do not run device diagnostics or remediation. Ticket, workflow, dashboard, and AI routes require cookie authentication and enforce user ownership or admin access.

## Backend setup (Windows PowerShell)

Python 3.11+ and PostgreSQL 14+ are required. This workspace's existing database is `helpdesk_db`; keep your current `DATABASE_URL` and ticket data. From the project root:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If this is a fresh setup, copy the placeholder configuration and edit it locally:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `DATABASE_URL` to your PostgreSQL role and `helpdesk_db`. `backend/.env` is excluded from Git. To enable chat, set `GROQ_API_KEY` in that file; never put the key in frontend code or chat. `GROQ_MODEL` defaults to `openai/gpt-oss-20b`; `GROQ_TIMEOUT_SECONDS` defaults to 30 and accepts 5-120 seconds. `CORS_ORIGINS` must list explicit frontend origins; the local Vite defaults are already in `.env.example`. `AUTH_SESSION_HOURS` defaults to 8. If the key is missing, AI chat returns a clear configuration error while ticket APIs remain available to authenticated clients.

Apply migrations and start the API:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`; docs are at `/docs`. `GET /api/health` checks the database connection. Alembic applies schema changes explicitly; startup does not seed or create tables.

### Optional demo data

After migration, you can explicitly run `python -m app.seed_demo` from `backend/`. It refuses `APP_ENV=production` and refuses to seed a non-empty table.

### Backend tests

```powershell
python -m pytest
```

Tests use isolated in-memory SQLite for ticket API tests and a mocked Groq client for AI tests. No Groq API key or outbound provider request is used by the tests. They do not replace a live PostgreSQL/Groq configuration check.

### Authentication and authorization

From `backend/`, create the initial administrator interactively with `python -m app.create_admin`. It prompts for a login identity and a password twice without echoing the password. Passwords are stored as Argon2id hashes. There is no public signup or account-promotion endpoint; this CLI refuses duplicate normalized identities. Run it only against the intended local database after migrations are applied.

Cookie-based clients first call `GET /api/auth/csrf` with `credentials: "include"`. It returns `{ "csrf_token": "…" }` and sets an HttpOnly CSRF cookie. Send that token in `X-CSRF-Token` and include credentials on state-changing auth requests. Since the session cookie uses `SameSite=Lax`, use the same host name for Vite and the API: with the current `127.0.0.1` API default, open Vite at `http://127.0.0.1:5173`; if you use Vite's `localhost` URL, set `VITE_API_BASE_URL=http://localhost:8000` in the frontend environment file.

```ts
const csrf = await fetch(`${API}/api/auth/csrf`, { credentials: "include" }).then(r => r.json());
const login = await fetch(`${API}/api/auth/login`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf.csrf_token },
  body: JSON.stringify({ login_identity, password }),
});
```

Successful login returns `{ "user": { "id", "login_identity", "role" }, "csrf_token" }`; the raw session token is only in an HttpOnly cookie. Use the returned CSRF token for logout. `GET /api/auth/me` returns only `{ "id", "login_identity", "role" }` and requires the session cookie. `POST /api/auth/logout` requires the Origin and CSRF header, revokes the session, clears both cookies, and returns `{ "status": "logged_out" }`. Local HTTP uses non-Secure cookies; production settings force Secure cookies and require HTTPS CORS origins.

The backend uses the reusable current-user and admin dependencies on protected routes. Users see only tickets and workflow runs linked to their user ID; old records with a null `user_id` are excluded from user views. Admins can inspect all records, including unlinked history. Ticket creation takes ownership from the session; the legacy `owner` request value is ignored. Users can edit ticket title and description, while category, priority, and status changes require an admin. Workflow event access follows the parent run, and user workflows cannot link to another user's ticket.

Dashboard metrics are scoped to the signed-in user's records; admins receive organization-wide aggregates. AI chat requires a session and CSRF validation and receives only the submitted issue plus retrieved static knowledge-base material; it does not load ticket or workflow history. The knowledge base has no standalone data API route. Data routes and the Swagger/ReDoc/OpenAPI documentation require authentication; login, logout, and the origin-checked CSRF bootstrap are the unauthenticated auth lifecycle routes, and login/logout still require CSRF/origin validation. `/api/health` remains public with minimal status information.

The React frontend includes the cookie-based login flow. It checks the current session on startup, uses credentialed API requests, obtains CSRF tokens from the backend, and shows navigation for the signed-in role. No session token is stored in browser storage.

## Frontend setup (PowerShell)

In another terminal, from the project root:

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

`VITE_API_BASE_URL` defaults to `http://127.0.0.1:8000`. The ticket list, filters, detail requests, ticket creation, dashboard counts, and analytics use backend data. Chat responses come from Groq through the backend and are never replaced by mock answers when the API/key/provider is unavailable. Workflow diagnostic outputs are explicitly simulated and do not inspect or change devices.

Frontend checks:

```powershell
npm run build
npm run lint
```

## API endpoints

- `GET /api/health`
- `GET /api/tickets?search=...&status=Open&priority=High`
- `GET /api/tickets/{ticket_id}`
- `POST /api/tickets`
- `PATCH /api/tickets/{ticket_id}`
- `POST /api/ai/chat` with `{ "issue": "VPN disconnects during calls" }`

The backend uses the official [Groq Python SDK](https://github.com/groq/groq-python) (`groq`). Provider calls use `GROQ_API_KEY`, the configured `GROQ_MODEL`, a bounded timeout, and disabled SDK retries so one request cannot silently expand into repeated provider calls.

## Phase 4 workflow monitor

The AI Help Center can start a persisted troubleshooting workflow with `POST /api/workflows`. The backend asks Groq for a diagnosis, validates it against the existing Pydantic schema, retrieves matching knowledge-base articles, then selects a tool only through its fixed safe allowlist (`simulated_network_connectivity`, `simulated_dns_resolution`, `simulated_service_health`, or `simulated_account_access`). Simulations never access operating-system commands, devices, accounts, or live network services. Their output is labeled `SIMULATED`; a sample pass is not proof about a real environment.

Workflow runs and audit events are stored in PostgreSQL. `GET /api/workflows` lists recent runs; `GET /api/workflows/{id}` returns a run; `POST /api/workflows/{id}/confirm` records the user's `{ "fixed": true|false }` confirmation. A positive confirmation marks the workflow as user-confirmed; it does not update a linked ticket. An inconclusive or failed check recommends human escalation and never creates a ticket automatically. To persist the new tables in an existing database, run `alembic upgrade head` from `backend/` before starting the API.

Workflow API uses the configured Groq key for live requests. Unit tests mock Groq and simulated tools; no API key or live provider is required to run the test suite. PostgreSQL migrations and records are unchanged by this provider migration.

### Live retest

After setting `GROQ_API_KEY` in `backend/.env`, start the backend and frontend as above. In AI Help Center, submit a short issue such as `Campus Wi-Fi keeps disconnecting`; a real answer should appear with any actually retrieved article references. Then select **Start safe troubleshooting workflow** and open the Workflow Monitor to inspect the validated diagnosis, retrieved articles, labeled simulation, verification, and audit timeline. A provider error should be shown as an error, and no simulation should run if diagnosis generation or validation fails. This migration has not been claimed as a live end-to-end workflow test.
