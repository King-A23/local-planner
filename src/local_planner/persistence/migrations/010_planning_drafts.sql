CREATE TABLE planning_drafts (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE planning_requests (
    request_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    draft_id TEXT NOT NULL REFERENCES planning_drafts(id)
);
