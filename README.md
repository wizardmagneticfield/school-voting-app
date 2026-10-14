# School Voting Web App

A full-stack election app for student government: students register and vote, admins create elections and publish results.

**Stack:** Flask (Python) API · React (Vite) frontend · PostgreSQL

## Features

- **Auth:** registration and login with **bcrypt**-hashed passwords (cost 12) and HTTP-only session cookies
- **Roles:** students vote; admins get a panel to create elections, open/close voting, and see turnout
- **Election lifecycle:** `draft → open → closed`, one way only. Results stay hidden from students until an election closes.
- **Results view** with vote counts and percentages

## One vote per student, enforced by the database

The rule isn't just checked in Python. It's built into the schema ([`backend/schema.sql`](backend/schema.sql)):

- `UNIQUE (user_id, election_id)` on `votes`: a second vote fails at the database level, **even if two requests race each other**
- A composite foreign key `(candidate_id, election_id) → candidates(id, election_id)`: you can't vote for a candidate from a different election
- The vote endpoint runs in **one transaction** and takes a `FOR SHARE` lock on the election row, so an admin can't close the election halfway through a vote

## Run locally

You need Python 3.10+, Node 18+, and PostgreSQL (Docker is easiest).

```bash
# 1. Database
docker compose up -d

# 2. Backend
cd backend
pip install -r requirements.txt
flask --app app init-db
flask --app app run --port 5000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Register an account in the browser, then make it an admin:

```bash
cd backend && flask --app app make-admin
```

Set `DATABASE_URL` and `SECRET_KEY` environment variables for anything beyond local dev.

## Tests

Integration tests run against a real Postgres database:

```bash
createdb voting_test   # or: docker compose exec db createdb -U voting voting_test
cd backend
DATABASE_URL=postgresql://voting:voting@localhost:5432/voting_test pytest -v
```

They cover: double voting is rejected, cross-election candidates are rejected, students can't reach admin routes or see live results, voting is blocked once an election closes, and bad passwords are rejected.

## Screenshots

_Add screenshots of the login page, ballot, results and admin panel here._

## API

| Method | Path | Who |
|---|---|---|
| POST | `/api/register`, `/api/login`, `/api/logout` | anyone |
| GET | `/api/me`, `/api/elections`, `/api/elections/:id` | logged in |
| POST | `/api/elections/:id/vote` | logged in |
| GET | `/api/elections/:id/results` | everyone once closed; admins anytime |
| POST | `/api/admin/elections` | admin |
| PATCH | `/api/admin/elections/:id/status` | admin |
| GET | `/api/admin/stats` | admin |

## Next steps

- Deploy (Render or Railway for the API, Vercel for the frontend)
- Rate-limit login attempts
- Ranked-choice voting
