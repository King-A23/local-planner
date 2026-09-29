ALTER TABLE goals ADD COLUMN parent_goal_id TEXT REFERENCES goals(id);
ALTER TABLE goals ADD COLUMN next_action_id TEXT REFERENCES goal_actions(id);
ALTER TABLE goal_phases ADD COLUMN outcome TEXT NOT NULL DEFAULT '' CHECK(length(outcome) <= 10000);
ALTER TABLE goal_phases ADD COLUMN horizon_text TEXT NOT NULL DEFAULT '' CHECK(length(horizon_text) <= 200);

CREATE INDEX idx_goals_parent ON goals(parent_goal_id);
CREATE TABLE goal_actions (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id),
  phase_id TEXT REFERENCES goal_phases(id),
  title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
  notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000),
  position INTEGER NOT NULL CHECK(position >= 0),
  task_id TEXT UNIQUE REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE INDEX idx_goal_actions_goal ON goal_actions(goal_id, position);
CREATE TABLE goal_action_requests (
  request_id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  -- Keep request tombstones after a candidate is removed.  A retry must not
  -- silently recreate an action, while structural draft apply may delete it.
  action_id TEXT NOT NULL
);

-- Existing goal-linked Tasks keep their IDs and become linked roadmap actions.
INSERT INTO goal_actions(id, goal_id, phase_id, title, notes, position, task_id)
SELECT lower(hex(randomblob(16))), t.goal_id, t.phase_id, t.title, t.notes,
       (SELECT count(*) FROM tasks earlier WHERE earlier.goal_id = t.goal_id
         AND earlier.discarded_at IS NULL
         AND (earlier.created_at < t.created_at OR (earlier.created_at = t.created_at AND earlier.id < t.id))),
       t.id
FROM tasks t
WHERE t.goal_id IS NOT NULL AND t.discarded_at IS NULL;
