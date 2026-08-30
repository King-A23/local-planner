PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE days (
  date TEXT PRIMARY KEY,          -- YYYY-MM-DD
  status TEXT NOT NULL CHECK (status IN ('open', 'sealed')),
  sealed_at TEXT,
  CHECK (
    (status = 'open' AND sealed_at IS NULL)
    OR (status = 'sealed' AND sealed_at IS NOT NULL)
  )
);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  created_at TEXT NOT NULL,
  current_scheduled_date TEXT REFERENCES days(date),
  completed_at TEXT,
  completed_on_date TEXT,
  CHECK (
    (completed_at IS NULL AND completed_on_date IS NULL)
    OR (completed_at IS NOT NULL AND completed_on_date IS NOT NULL)
  )
);

CREATE TABLE day_task_entries (
  day_date TEXT NOT NULL REFERENCES days(date),
  task_id TEXT NOT NULL REFERENCES tasks(id),
  title_snapshot TEXT NOT NULL
    CHECK (length(title_snapshot) BETWEEN 1 AND 200),
  sort_order INTEGER NOT NULL,
  completed_on_day INTEGER NOT NULL DEFAULT 0
    CHECK (completed_on_day IN (0, 1)),
  PRIMARY KEY (day_date, task_id),
  UNIQUE (day_date, sort_order)
);

CREATE TABLE errands (
  id TEXT PRIMARY KEY,
  day_date TEXT NOT NULL REFERENCES days(date),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  sort_order INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'completed', 'expired')),
  completed_at TEXT,
  UNIQUE (day_date, sort_order),
  CHECK (
    (status = 'completed' AND completed_at IS NOT NULL)
    OR (status IN ('open', 'expired') AND completed_at IS NULL)
  )
);

CREATE INDEX idx_tasks_inventory
  ON tasks (completed_at, current_scheduled_date);
CREATE INDEX idx_tasks_schedule
  ON tasks (current_scheduled_date);
CREATE INDEX idx_errands_day
  ON errands (day_date, sort_order);
CREATE INDEX idx_entries_day
  ON day_task_entries (day_date, sort_order);

-- 封印不可变：001_init.sql 必含，不是建议。应用层仍先拒绝。

CREATE TRIGGER day_task_entries_no_insert_sealed
BEFORE INSERT ON day_task_entries
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER day_task_entries_no_update_sealed
BEFORE UPDATE ON day_task_entries
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
              OR (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER day_task_entries_no_delete_sealed
BEFORE DELETE ON day_task_entries
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER errands_no_insert_sealed
BEFORE INSERT ON errands
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER errands_no_update_sealed
BEFORE UPDATE ON errands
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
              OR (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER errands_no_delete_sealed
BEFORE DELETE ON errands
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER days_no_unseal_or_mutate_sealed
BEFORE UPDATE ON days
BEGIN
  SELECT CASE WHEN OLD.status = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER days_no_delete_sealed
BEFORE DELETE ON days
BEGIN
  SELECT CASE WHEN OLD.status = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;
