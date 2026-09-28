import { isCivilDate } from "./dates";
import { openDesktopSettings } from "./desktop";

export type Route =
  | { kind: "today" }
  | { kind: "day"; date: string }
  | { kind: "inventory" }
  | { kind: "settings" }
  | { kind: "recurrences" }
  | { kind: "goals" }
  | { kind: "goal"; id: string }
  | { kind: "todayPlanning" }
  | { kind: "notfound" };

const DAY_PATH = /^\/d\/([^/]+)$/;
const GOAL_PATH = /^\/goals\/([^/]+)$/;

export function parseRoute(pathname: string): Route {
  if (pathname === "/" || pathname === "") {
    return { kind: "today" };
  }
  if (pathname === "/settings") return { kind: "settings" };
  if (pathname === "/inventory") {
    return { kind: "inventory" };
  }
  if (pathname === "/recurrences") {
    return { kind: "recurrences" };
  }
  if (pathname === "/goals") return { kind: "goals" };
  const goal = GOAL_PATH.exec(pathname);
  if (goal) return { kind: "goal", id: decodeURIComponent(goal[1]) };
  if (pathname === "/planning/today") {
    return { kind: "todayPlanning" };
  }
  const match = DAY_PATH.exec(pathname);
  if (match) {
    return isCivilDate(match[1])
      ? { kind: "day", date: match[1] }
      : { kind: "notfound" };
  }
  return { kind: "notfound" };
}

export function navigate(href: string): void {
  if (new URL(href, window.location.href).pathname === "/settings" && openDesktopSettings(href)) return;
  if (window.location.pathname === href) {
    return;
  }
  window.history.pushState(null, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function handleNavClick(
  event: { preventDefault: () => void },
  href: string,
): void {
  event.preventDefault();
  navigate(href);
}
