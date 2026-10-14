-- School voting app schema (PostgreSQL)

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    student_id    VARCHAR(32)  NOT NULL UNIQUE,
    name          VARCHAR(100) NOT NULL,
    password_hash VARCHAR(100) NOT NULL,            -- bcrypt hash, never the password
    role          VARCHAR(10)  NOT NULL DEFAULT 'student'
                  CHECK (role IN ('student', 'admin')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS elections (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    description TEXT,
    status      VARCHAR(10)  NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'open', 'closed')),
    created_by  INTEGER      NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS candidates (
    id          SERIAL PRIMARY KEY,
    election_id INTEGER      NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    platform    TEXT,
    UNIQUE (election_id, name),
    UNIQUE (id, election_id)          -- lets votes reference (candidate, election) as a pair
);

CREATE TABLE IF NOT EXISTS votes (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id),
    election_id  INTEGER     NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    candidate_id INTEGER     NOT NULL,
    cast_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- One vote per user per election, enforced by the database itself:
    CONSTRAINT one_vote_per_user_per_election UNIQUE (user_id, election_id),
    -- The candidate must belong to the same election the vote is for:
    FOREIGN KEY (candidate_id, election_id) REFERENCES candidates(id, election_id)
);

CREATE INDEX IF NOT EXISTS idx_votes_election ON votes(election_id);
