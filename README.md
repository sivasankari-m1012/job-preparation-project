# Job Interview Track Platform

Track job applications and prepare for each company's interview — Flask REST API,
SQLAlchemy database layer, and a vanilla JavaScript front end.

## Features

- Add, update, filter, search, sort and delete job applications
- Dashboard counts per status (Applied → Online Assessment → … → Selected / Rejected)
- Status history timeline for every application (who moved where, and when)
- Optional details: location, job link, deadline, notes
- Company preparation kits (TCS, Cargill, Infosys, Wipro)
- Server-side validation with clear error messages, JSON errors on every `/api` route

## Tech stack

Python · Flask · Flask-SQLAlchemy / SQLAlchemy · SQLite (default) or PostgreSQL · JavaScript · pytest

## Database design

```
job (1) ──────< status_history (many)

job             id PK · company · role · status · location · url · notes
                deadline · created_at · updated_at
status_history  id PK · job_id FK → job.id (ON DELETE CASCADE)
                from_status · to_status · changed_at
```

- `status` is restricted to the six allowed values (CHECK constraint + API validation)
- Indexes on `job.company`, `job.status` and `status_history.job_id`
- Deleting a job deletes its history (cascade); SQLite foreign keys are switched on explicitly
- A history row is written when a job is created and whenever its status actually changes

## Run it (Windows)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python backend/app.py
```

Open http://127.0.0.1:5000. The SQLite file is created at `instance/jobs.db`
(same place wherever you start the app from). Debug mode is off unless you set `FLASK_DEBUG=1`.

### Use PostgreSQL instead

```
pip install "psycopg[binary]"
set DATABASE_URL=postgresql://user:password@localhost:5432/jobtrack
python backend/app.py
```

Tables are created on startup. For schema changes on an existing PostgreSQL database use
Flask-Migrate / Alembic.

### Already have an old `jobs.db`?

```
python scripts/upgrade_legacy_db.py
```

Adds the new columns and the history table, keeps your rows, and writes `jobs.db.bak` first.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/jobs?status=&q=&sort=&order=` | List (filter by status, search company/role, sort by `company`, `role`, `status`, `deadline`, `created_at`) |
| POST | `/api/jobs` | Create (`company`, `role`, `status` required) |
| GET | `/api/jobs/<id>` | One job with its status history |
| PATCH | `/api/jobs/<id>` | Partial update (e.g. only `status`) |
| PUT | `/api/jobs/<id>` | Full replace (`company`, `role`, `status` required) |
| DELETE | `/api/jobs/<id>` | Delete job and its history |
| GET | `/api/stats` | Total and count per status |

Errors are JSON: `400 {"error": "Validation failed", "details": {"company": "cannot be blank"}}`,
`404 {"error": "Job not found"}`.

## Tests

```
python -m pytest
```

Covers create/read/update/delete, validation, filtering and sorting, status history,
cascade delete, stats, and that data survives an app restart.

## Roadmap

- User accounts (register/login) with per-user applications
- React front end
- Deployment (gunicorn + hosted PostgreSQL)
