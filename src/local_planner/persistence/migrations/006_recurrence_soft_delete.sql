ALTER TABLE recurrence_series ADD COLUMN deleted_at TEXT;

DROP INDEX idx_recurrence_series_state;
CREATE INDEX idx_recurrence_series_state
  ON recurrence_series (deleted_at, state, schedule_from);
