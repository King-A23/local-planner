CREATE TABLE goals (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
  notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000),
  horizon_text TEXT NOT NULL DEFAULT '' CHECK(length(horizon_text) <= 200),
  state TEXT NOT NULL CHECK(state IN ('active', 'paused', 'ended')),
  end_reason TEXT CHECK(end_reason IN ('achieved', 'abandoned')),
  next_task_id TEXT REFERENCES tasks(id),
  focus_phase_id TEXT REFERENCES goal_phases(id),
  revision INTEGER NOT NULL CHECK(revision > 0),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  ended_at TEXT,
  CHECK ((state = 'ended' AND end_reason IS NOT NULL AND ended_at IS NOT NULL)
      OR (state != 'ended' AND end_reason IS NULL AND ended_at IS NULL))
);
CREATE TABLE goal_phases (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id),
  title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
  notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000),
  position INTEGER NOT NULL CHECK(position >= 0),
  status TEXT NOT NULL CHECK(status IN ('open', 'done', 'skipped'))
);
CREATE INDEX idx_goal_phases_goal ON goal_phases(goal_id, position);
ALTER TABLE tasks ADD COLUMN goal_id TEXT REFERENCES goals(id);
ALTER TABLE tasks ADD COLUMN phase_id TEXT REFERENCES goal_phases(id);
CREATE INDEX idx_tasks_goal ON tasks(goal_id);
ALTER TABLE day_task_entries ADD COLUMN goal_id_snapshot TEXT;
ALTER TABLE day_task_entries ADD COLUMN goal_title_snapshot TEXT;
ALTER TABLE day_task_entries ADD COLUMN phase_id_snapshot TEXT;
ALTER TABLE day_task_entries ADD COLUMN phase_title_snapshot TEXT;
CREATE TABLE goal_requests (
  request_id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  goal_id TEXT NOT NULL REFERENCES goals(id)
);
