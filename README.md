# Campus Mind AI — Intelligent University Operating System

Campus Mind AI brings university administration and academic workflows into one authenticated application. The web client uses a Python FastAPI service, relational database, role based access rules, and a university knowledge assistant.

## Scope

The supplied workspace contained no source files or existing interface, so there was no MVP to retain. This repository now contains a complete runnable application foundation based on the supplied project brief.

## Features

- Super Admin, single-course Course Admin, and Student accounts; JWT expiry, password hashing, account deactivation, and server-revoked logout
- Six initial engineering courses, six subjects per course, 60 Indian university-style demo students per course
- Student creation/editing/deactivation; Course Admin creation/editing/deactivation; course and subject management
- Subject attendance marking and edits, personal attendance views and summaries, configurable low-attendance alerts
- Assignments with marks, due dates, publish/draft and archive states; student submissions and staff submission review
- Grades with publication status, computed letter grade, and student-specific visibility
- Timetable with weekday, time, faculty and room; exam schedules and status
- Course and university announcements, campus events, user notifications with unread count and read state
- Live course enrollment, attendance, marks, assignment completion, and attendance risk analytics
- Role-aware CampusMind AI and separate My Campus-Intelligent chats, with history and clear/new conversation actions
- Published FAQ search, topic filters, featured FAQs, feedback, and Super Admin FAQ management
- Responsive React UI with empty, loading, error, and form states
- PostgreSQL, SQLAlchemy, Alembic migrations, repeatable demo seed, OpenAPI docs, and authorization tests

## Stack and architecture

- Frontend: React 18, TypeScript, Vite 6
- Backend: Python 3.10+, FastAPI, Pydantic
- Database: PostgreSQL 16; SQLite is supported for a quick local run
- ORM/migrations: SQLAlchemy 2 and Alembic
- Authentication: JWT bearer tokens, bcrypt password hashes, token version revocation
- AI: configurable OpenAI-compatible chat completions endpoint (`AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`); FAQ and authorized application context are retrieved before prompts. Without a provider key, grounded FAQ and role-specific academic responses still work.

```text
React → FastAPI and role checks → SQLAlchemy → PostgreSQL
                                  └→ authorized FAQ and campus retrieval → optional LLM
```

## Run with Docker Compose

This Compose file is for local development. It starts PostgreSQL, applies migrations, loads synthetic demo data, and starts the frontend. Install Docker Desktop, then from the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`: replace `POSTGRES_PASSWORD`, use the same value in `DATABASE_URL`, choose a `DEMO_PASSWORD` with at least 10 characters, and set `JWT_SECRET` to a random value of at least 32 characters. Then run:

```powershell
docker compose up --build
```

Open the app at `http://localhost:8080` and API docs at `http://localhost:8000/docs`. Stop services with `Ctrl+C`; use `docker compose down` to stop containers. `docker compose down -v` also removes the local demo database volume.

For generated AI responses, set `AI_API_KEY` and `AI_MODEL` in `.env`. The provider endpoint can be changed with `AI_BASE_URL`. Leave them blank to use the included FAQ-grounded and role-aware local responses. When enabling a hosted model, the app sends relevant course and academic record context to that provider; review institutional approval, data processing terms, and retention settings before using real student records.

## Run directly on Windows

### Backend

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

For SQLite, set `DATABASE_URL=sqlite:///./campusmind.db` in `backend/.env`. To use PostgreSQL instead, set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` and start your PostgreSQL server/database first. Set a unique local `JWT_SECRET` and `DEMO_PASSWORD` in `.env`.

```powershell
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

### Frontend

In a second PowerShell window:

```powershell
cd frontend
npm ci
npm run dev
```

The app runs at `http://localhost:5173`. Set `VITE_API_URL` in the frontend shell or a `frontend/.env` file if the API runs elsewhere. Production bundle: `npm run build`.

## Production deployment

Production must use the backend and frontend container images behind a TLS terminating reverse proxy or managed ingress. Start with [deploy/.env.production.example](deploy/.env.production.example), and replace every placeholder through the hosting platform's secret manager. Use a managed PostgreSQL service with automated backups, point-in-time recovery, and tested restore procedures. Keep the API private to the ingress network; do not expose its port publicly. Configure the ingress to forward HTTPS traffic to the frontend container, which serves the static app and proxies `/api/` to the private API service.

Build and publish versioned images from a reviewed commit. The backend image installs the exact versions in `backend/requirements.lock.txt`, and the frontend uses `npm ci` from its lockfile. Set `APP_ENV=production`, a unique `JWT_SECRET` with at least 32 characters, `DATABASE_URL` for PostgreSQL, exact `ALLOWED_HOSTS` values, and the public HTTPS origin in `CORS_ORIGINS`. Store these values in the hosting platform's secret manager. Leave `DEMO_PASSWORD` unset. The backend rejects unsafe production configuration, disables interactive API docs, sets secure HTTP-only session cookies, restricts cookie-authenticated writes by origin, and applies security response headers. The frontend ingress configuration limits login attempts; retain equivalent or stronger rate limiting at the public ingress when deploying a different frontend server.

Run `alembic upgrade head` once as a release step before routing traffic to a new backend version. Do not run the demo seed in production. Deploy at least two API instances behind the ingress when availability requires it, and size `DATABASE_POOL_SIZE` and `DATABASE_MAX_OVERFLOW` against the database's connection limit and instance count. Configure platform monitoring for `/api/health` (process liveness) and `/api/ready` (database readiness), centralized logs, alerting, backups, and a rollback plan. Terminate TLS at a trusted ingress and make sure direct HTTP access is blocked.

These controls prepare the code and containers for a production deployment; production readiness still depends on the chosen hosting, network, secrets, database operations, restore drills, security review, and traffic validation. Institutional SSO/MFA, account recovery, comprehensive administrator audit trails, and university-specific privacy/retention controls still need to be designed with the deploying institution. The included Compose stack is deliberately a local demo stack, not a production deployment topology.

## Demo accounts

Seeding requires a `DEMO_PASSWORD` environment value at least 10 characters long. Every seeded demo account uses the value you choose; the application never displays it.

- Super Admin: `admin`
- Course Admins: `cse_admin`, `it_admin`, `entc_admin`, `me_admin`, `ce_admin`, `aids_admin`
- Student examples: `CSE2026001`, `IT2026001`, `ENTC2026001`, `ME2026001`, `CE2026001`, `AIDS2026001`

The seed is additive and repeatable. It creates six courses, 36 subjects, six course administrators, 360 students, attendance, timetable entries, exams, assignments, sample grades, announcements, events, notifications, FAQ topics and FAQ content. It does not reset or change passwords on existing accounts.

## API and database

All routes except `/api/health`, `/api/ready`, and the credential endpoints need authentication. Browser sign-in at `/api/auth/login` uses an HTTP-only session cookie. API clients can exchange credentials at `/api/auth/token` for a bearer token. FastAPI publishes the interactive contract at `/docs` and `/openapi.json` in development; these endpoints are disabled in production.

API groups include authentication, courses, subjects, students, administrators, attendance and summary, assignments and submissions, grades, timetable, exams, announcements, events, notifications, FAQs and feedback, analytics, AI conversations and chat.

Alembic manages schema changes. The first migration creates the schema from the project's SQLAlchemy metadata; future changes should be made as reviewed migrations. SQLAlchemy database connections use `DATABASE_URL`.

## Security notes

The API checks role, active status, and token version on each request. Browser sessions use HTTP-only, same-site cookies and state-changing cookie requests must come from a configured origin. A Student cannot list or read another student's records. A Course Admin is bound to one course, and staff academic writes validate the student's and subject's course membership. AI receives only the authenticated user's authorized record context, plus published campus information. The interface's hidden navigation is not used as an authorization boundary.

Set `CORS_ORIGINS` to the exact browser origins you serve. Production deployment should terminate HTTPS at a trusted proxy and store secrets outside source control.

## Verification

From `backend`, run `python -m pytest`. Tests cover authentication, inactive users, logout token revocation, student record isolation, course-admin course isolation, and restricted account creation. The frontend production bundle is built with `npm run build`.

Format backend Python with `python -m black app tests alembic` after installing `requirements-dev.txt`. Format frontend source with `npm run format`.

## Project structure

```text
backend/app/          FastAPI app, SQLAlchemy models, schemas, security, administration
backend/alembic/      Database migration environment and initial revision
backend/tests/        API permission and authentication tests
frontend/src/         React app and responsive styles
docker-compose.yml    PostgreSQL + API + frontend local stack
```
