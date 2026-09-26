CREATE TABLE recurrence_series (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('plan', 'errand')),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly')),
  weekdays_mask INTEGER NOT NULL CHECK (weekdays_mask BETWEEN 1 AND 127),
  start_date TEXT NOT NULL,
  schedule_from TEXT NOT NULL,
  default_start_clock TEXT,
  default_end_clock TEXT,
  state TEXT NOT NULL CHECK (state IN ('active', 'paused', 'stopped')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  paused_at TEXT,
  stopped_at TEXT
);

CREATE TABLE recurrence_occurrences (
  series_id TEXT NOT NULL REFERENCES recurrence_series(id) ON DELETE RESTRICT,
  occurrence_date TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('plan', 'errand')),
  entity_id TEXT,
  disposition TEXT NOT NULL
    CHECK (disposition IN ('materialized', 'skipped_sealed')),
  generated_at TEXT NOT NULL,
  PRIMARY KEY (series_id, occurrence_date),
  UNIQUE (kind, entity_id),
  CHECK (
    (disposition = 'materialized' AND entity_id IS NOT NULL)
    OR (disposition = 'skipped_sealed' AND entity_id IS NULL)
  )
);

CREATE INDEX idx_recurrence_series_state
  ON recurrence_series (state, schedule_from);
CREATE INDEX idx_recurrence_occurrence_entity
  ON recurrence_occurrences (kind, entity_id);
