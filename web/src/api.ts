export type Todo = {
  taskId: string;
  title: string;
  completedOnDay: boolean;
  sortOrder: number;
};

export type ErrandStatus = "open" | "completed" | "expired";

export type Errand = {
  id: string;
  title: string;
  status: ErrandStatus;
  sortOrder: number;
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
};

export type InventoryItem = {
  taskId: string;
  title: string;
  createdAt: string;
};

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

export type InventoryList = {
  items: InventoryItem[];
};

export function listInventory(): Promise<InventoryList> {
  return fetch("/api/inventory").then((r) => readJson<InventoryList>(r));
}

export function addToInventory(title: string): Promise<InventoryItem> {
  return jsonRequest("/api/inventory/tasks", {
    method: "POST",
    body: JSON.stringify({ title }),
  }).then((r) => readJson<InventoryItem>(r));
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
