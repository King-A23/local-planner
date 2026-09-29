-- Preserve create request IDs after a goal is permanently deleted.
CREATE TABLE goal_requests_new (
  request_id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  goal_id TEXT REFERENCES goals(id) ON DELETE SET NULL
);
INSERT INTO goal_requests_new(request_id, fingerprint, goal_id)
SELECT request_id, fingerprint, goal_id FROM goal_requests;
DROP TABLE goal_requests;
ALTER TABLE goal_requests_new RENAME TO goal_requests;
