CREATE TABLE day_planning (
  day_date TEXT PRIMARY KEY REFERENCES days(date) ON DELETE RESTRICT,
  planned_at TEXT NOT NULL
);

CREATE TRIGGER day_planning_no_insert_sealed
BEFORE INSERT ON day_planning
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER day_planning_no_update_sealed
BEFORE UPDATE ON day_planning
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
              OR (SELECT status FROM days WHERE date = NEW.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;

CREATE TRIGGER day_planning_no_delete_sealed
BEFORE DELETE ON day_planning
BEGIN
  SELECT CASE WHEN (SELECT status FROM days WHERE date = OLD.day_date) = 'sealed'
    THEN RAISE(ABORT, 'sealed day is immutable') END;
END;
