ALTER TABLE tasks ADD COLUMN notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000);
ALTER TABLE day_task_entries ADD COLUMN notes_snapshot TEXT NOT NULL DEFAULT '' CHECK(length(notes_snapshot) <= 10000);
ALTER TABLE errands ADD COLUMN notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000);
ALTER TABLE days ADD COLUMN manual_todo_order INTEGER NOT NULL DEFAULT 0 CHECK(manual_todo_order IN (0, 1));
ALTER TABLE days ADD COLUMN manual_errand_order INTEGER NOT NULL DEFAULT 0 CHECK(manual_errand_order IN (0, 1));
