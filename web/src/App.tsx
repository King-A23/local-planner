import { useEffect, useState } from "react";

import { errorMessage, getMeta, type Meta } from "./api";
import { META_POLL_MS } from "./constants";
import { DayView } from "./DayView";
import { handleNavClick, parseRoute } from "./route";
import { Shell } from "./Shell";

function usePathname(): string {
  const [pathname, setPathname] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return pathname;
}

export function App() {
  const pathname = usePathname();
  const route = parseRoute(pathname);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    function refresh() {
      getMeta()
        .then((next) => {
          if (!cancelled) {
            setMeta(next);
            setMetaError(null);
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setMetaError(errorMessage(err));
          }
        });
    }
    refresh();
    // §6.6: poll updates meta.today only. `/` re-opens the new today;
    // a parked `/d/昨天` stays on that URL and DayView re-reads OpenDay.
    const id = window.setInterval(refresh, META_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const viewedDate =
    route.kind === "day"
      ? route.date
      : route.kind === "today"
        ? meta?.today
        : undefined;

  let body;
  if (route.kind === "inventory") {
    body = (
      <main className="page">
        <h1>库存</h1>
        <p className="muted">未排期的正经待办将出现在这里。</p>
      </main>
    );
  } else if (route.kind === "notfound") {
    body = (
      <main className="page">
        <h1>找不到该页</h1>
        <p>
          <a href="/" onClick={(e) => handleNavClick(e, "/")}>
            回到今天
          </a>
        </p>
      </main>
    );
  } else if (route.kind === "today") {
    if (metaError) {
      body = (
        <main className="page">
          <p className="error">{metaError}</p>
        </main>
      );
    } else if (!meta) {
      body = (
        <main className="page">
          <p>加载中…</p>
        </main>
      );
    } else {
      body = <DayView date={meta.today} serverToday={meta.today} />;
    }
  } else {
    body = <DayView date={route.date} serverToday={meta?.today} />;
  }

  return (
    <Shell
      inventoryCount={meta?.inventoryCount}
      today={meta?.today}
      viewedDate={viewedDate}
    >
      {body}
    </Shell>
  );
}
