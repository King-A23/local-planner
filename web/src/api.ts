export type Todo = {
  taskId: string;
  title: string;
  completedOnDay: boolean;
  sortOrder: number;
  startClock: string | null;
  endClock: string | null;
  recurrence: RecurrenceOccurrence | null;
};

export type ErrandStatus = "open" | "completed" | "expired";

export type Errand = {
  id: string;
  title: string;
  status: ErrandStatus;
  sortOrder: number;
  startClock: string | null;
  endClock: string | null;
  recurrence: RecurrenceOccurrence | null;
};

/** The origin carried by an already-generated recurring occurrence. */
export type RecurrenceOccurrence = {
  seriesId: string;
  occurrenceDate: string;
  label: string;
};

export type DayPlan = {
  date: string;
  serverToday: string;
  isToday: boolean;
  isPast: boolean;
  isFuture: boolean;
  writable: boolean;
  status: "open" | "sealed";
  todos: Todo[];
  errands: Errand[];
};

export type Meta = {
  today: string;
  timezone: string;
  lastSettledDate: string;
  inventoryCount: number;
  planningStatus: PlanningStatus;
};

export type InventoryItem = {
  taskId: string;
  title: string;
  createdAt: string;
  targetDate: string | null;
  recurrence?: RecurrenceOccurrence | null;
};

export type PlanningStatus = "unplanned" | "ready";

export type PlanningUpcoming = {
  date: string;
  todoCount?: number;
  errandCount?: number;
  recurrenceCount?: number;
};

export type TodayPlanning = {
  date: string;
  status: PlanningStatus;
  day: DayPlan;
  returnedFromYesterday: InventoryItem[];
  due: InventoryItem[];
  inventory: InventoryItem[];
  upcoming: PlanningUpcoming[];
};

export type RecurrenceKind = "plan" | "errand";
export type RecurrenceFrequency = "daily" | "weekly";
export type RecurrenceState = "active" | "paused" | "stopped";

export type RecurrenceWeekday =
  | "mon"
  | "tue"
  | "wed"
  | "thu"
  | "fri"
  | "sat"
  | "sun";

export type Recurrence = {
  id: string;
  title: string;
  kind: RecurrenceKind;
  frequency: RecurrenceFrequency;
  weekdays: RecurrenceWeekday[];
  startDate: string;
  defaultStartClock: string | null;
  defaultEndClock: string | null;
  state: RecurrenceState;
  nextOccurrenceDate: string | null;
  stoppedAt: string | null;
};

export type RecurrenceInput = Pick<
  Recurrence,
  | "title"
  | "kind"
  | "frequency"
  | "weekdays"
  | "startDate"
  | "defaultStartClock"
  | "defaultEndClock"
>;

export class ApiError extends Error {
  readonly error: string;
  readonly status: number;

  constructor(status: number, error: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.error = error;
  }
}

const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

async function readJson<T>(response: Response): Promise<T> {
  const body: unknown = await response.json();
  if (!response.ok) {
    const rec = body as { error?: string; message?: string };
    throw new ApiError(
      response.status,
      rec.error ?? "Error",
      rec.message ?? "请求失败",
    );
  }
  return body as T;
}

function jsonRequest(url: string, init: RequestInit): Promise<Response> {
  return fetch(url, { ...init, headers: { ...JSON_HEADERS, ...init.headers } });
}

export type CalendarDayCount = {
  date: string;
  todoCount: number;
  errandCount: number;
};

export type Calendar = {
  today: string;
  days: CalendarDayCount[];
};

export function getMeta(): Promise<Meta> {
  return fetch("/api/meta").then((r) => readJson<Meta>(r));
}

export function getTodayPlanning(): Promise<TodayPlanning> {
  return fetch("/api/planning/today").then((r) => readJson<TodayPlanning>(r));
}

export function completeTodayPlanning(): Promise<TodayPlanning> {
  return jsonRequest("/api/planning/today/complete", {
    method: "POST",
  }).then((r) => readJson<TodayPlanning>(r));
}

export function listRecurrences(): Promise<{ items: Recurrence[] }> {
  return fetch("/api/recurrences").then((r) =>
    readJson<{ items: Recurrence[] }>(r),
  );
}

export function createRecurrence(input: RecurrenceInput): Promise<Recurrence> {
  return jsonRequest("/api/recurrences", {
    method: "POST",
    body: JSON.stringify(input),
  }).then((r) => readJson<Recurrence>(r));
}

export function updateRecurrence(
  id: string,
  input: RecurrenceInput,
): Promise<Recurrence> {
  return jsonRequest(`/api/recurrences/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  }).then((r) => readJson<Recurrence>(r));
}

function recurrenceTransition(
  id: string,
  operation: "pause" | "resume" | "stop",
): Promise<Recurrence> {
  return jsonRequest(`/api/recurrences/${id}/${operation}`, {
    method: "POST",
  }).then((r) => readJson<Recurrence>(r));
}

export function pauseRecurrence(id: string): Promise<Recurrence> {
  return recurrenceTransition(id, "pause");
}

export function resumeRecurrence(id: string): Promise<Recurrence> {
  return recurrenceTransition(id, "resume");
}

export function stopRecurrence(id: string): Promise<Recurrence> {
  return recurrenceTransition(id, "stop");
}

export function deleteRecurrence(id: string): Promise<{ ok: true }> {
  return jsonRequest(`/api/recurrences/${id}`, {
    method: "DELETE",
  }).then((r) => readJson<{ ok: true }>(r));
}

export function getCalendar(from: string, to: string): Promise<Calendar> {
  const params = new URLSearchParams({ from, to });
  return fetch(`/api/calendar?${params}`).then((r) => readJson<Calendar>(r));
}

export function openDay(date: string): Promise<DayPlan> {
  return fetch(`/api/days/${date}`).then((r) => readJson<DayPlan>(r));
}

export function addTodoOnDay(date: string, title: string): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/todos`, {
    method: "POST",
    body: JSON.stringify({ title }),
  }).then((r) => readJson<DayPlan>(r));
}

export function addErrandOnDay(date: string, title: string): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/errands`, {
    method: "POST",
    body: JSON.stringify({ title }),
  }).then((r) => readJson<DayPlan>(r));
}

export function completeErrand(errandId: string): Promise<DayPlan> {
  return jsonRequest(`/api/errands/${errandId}/complete`, {
    method: "POST",
  }).then((r) => readJson<DayPlan>(r));
}

export function uncompleteErrand(errandId: string): Promise<DayPlan> {
  return jsonRequest(`/api/errands/${errandId}/uncomplete`, {
    method: "POST",
  }).then((r) => readJson<DayPlan>(r));
}

export function renameErrand(errandId: string, title: string): Promise<DayPlan> {
  return jsonRequest(`/api/errands/${errandId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  }).then((r) => readJson<DayPlan>(r));
}

export function deleteErrand(errandId: string): Promise<DayPlan> {
  return jsonRequest(`/api/errands/${errandId}`, { method: "DELETE" }).then((r) =>
    readJson<DayPlan>(r),
  );
}

export function completeTodo(date: string, taskId: string): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/todos/${taskId}/complete`, {
    method: "POST",
  }).then((r) => readJson<DayPlan>(r));
}

export function uncompleteTodo(date: string, taskId: string): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/todos/${taskId}/uncomplete`, {
    method: "POST",
  }).then((r) => readJson<DayPlan>(r));
}

export function renameTask(
  taskId: string,
  title: string,
): Promise<DayPlan | InventoryItem> {
  return jsonRequest(`/api/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  }).then((r) => readJson<DayPlan | InventoryItem>(r));
}

export function deleteTask(taskId: string): Promise<{ ok: true }> {
  return jsonRequest(`/api/tasks/${taskId}`, { method: "DELETE" }).then((r) =>
    readJson<{ ok: true }>(r),
  );
}

export function completeInventoryTask(taskId: string): Promise<DayPlan> {
  return jsonRequest(`/api/inventory/tasks/${taskId}/complete`, {
    method: "POST",
  }).then((r) => readJson<DayPlan>(r));
}

export type InventoryList = {
  items: InventoryItem[];
};

export function listInventory(): Promise<InventoryList> {
  return fetch("/api/inventory").then((r) => readJson<InventoryList>(r));
}

export function addToInventory(
  title: string,
  targetDate?: string | null,
): Promise<InventoryItem> {
  return jsonRequest("/api/inventory/tasks", {
    method: "POST",
    body: JSON.stringify({ title, targetDate: targetDate ?? null }),
  }).then((r) => readJson<InventoryItem>(r));
}

export function setTaskTarget(
  taskId: string,
  date: string | null,
): Promise<InventoryItem | DayPlan> {
  return jsonRequest(`/api/tasks/${taskId}/target`, {
    method: "PATCH",
    body: JSON.stringify({ date }),
  }).then((r) => readJson<InventoryItem | DayPlan>(r));
}

export function setTodoClocks(
  date: string,
  taskId: string,
  startClock: string | null,
  endClock: string | null,
): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/todos/${taskId}/clocks`, {
    method: "PATCH",
    body: JSON.stringify({ startClock, endClock }),
  }).then((r) => readJson<DayPlan>(r));
}

export function setErrandClocks(
  errandId: string,
  startClock: string | null,
  endClock: string | null,
): Promise<DayPlan> {
  return jsonRequest(`/api/errands/${errandId}/clocks`, {
    method: "PATCH",
    body: JSON.stringify({ startClock, endClock }),
  }).then((r) => readJson<DayPlan>(r));
}

export function scheduleTask(taskId: string, date: string): Promise<DayPlan> {
  return jsonRequest(`/api/tasks/${taskId}/schedule`, {
    method: "POST",
    body: JSON.stringify({ date }),
  }).then((r) => readJson<DayPlan>(r));
}

export function unscheduleTask(taskId: string): Promise<InventoryItem> {
  return jsonRequest(`/api/tasks/${taskId}/unschedule`, {
    method: "POST",
  }).then((r) => readJson<InventoryItem>(r));
}

export function reorderTodos(date: string, taskIds: string[]): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/todos/order`, {
    method: "PUT",
    body: JSON.stringify({ taskIds }),
  }).then((r) => readJson<DayPlan>(r));
}

export function reorderErrands(
  date: string,
  errandIds: string[],
): Promise<DayPlan> {
  return jsonRequest(`/api/days/${date}/errands/order`, {
    method: "PUT",
    body: JSON.stringify({ errandIds }),
  }).then((r) => readJson<DayPlan>(r));
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "请求失败";
}

export function isDayPlan(
  value: DayPlan | InventoryItem,
): value is DayPlan {
  return "todos" in value && "date" in value;
}
