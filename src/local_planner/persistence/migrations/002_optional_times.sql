ALTER TABLE tasks ADD COLUMN target_date TEXT;

ALTER TABLE day_task_entries ADD COLUMN start_clock TEXT;
ALTER TABLE day_task_entries ADD COLUMN end_clock TEXT;

ALTER TABLE errands ADD COLUMN start_clock TEXT;
ALTER TABLE errands ADD COLUMN end_clock TEXT;
