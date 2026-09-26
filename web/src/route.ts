import { isCivilDate } from "./dates";

export type Route =
  | { kind: "today" }
  | { kind: "day"; date: string }
  | { kind: "inventory" }
  | { kind: "recurrences" }
  | { kind: "todayPlanning" }
  | { kind: "notfound" };

const DAY_PATH = /^\/d\/([^/]+)$/;

export function parseRoute(pathname: string): Route {
  if (pathname === "/" || pathname === "") {
    return { kind: "today" };
  }
  if (pathname === "/inventory") {
    return { kind: "inventory" };
  }
  if (pathname === "/recurrences") {
    return { kind: "recurrences" };
  }
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
