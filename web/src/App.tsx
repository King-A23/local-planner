import { useCallback, useEffect, useState } from "react";

import { errorMessage, getMeta, type Meta } from "./api";
import { META_POLL_MS } from "./constants";
import { DayView } from "./DayView";
import { InventoryPage } from "./InventoryPage";
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

  const refreshMeta = useCallback(() => {
    getMeta()
      .then((next) => {
        setMeta(next);
        setMetaError(null);
      })
      .catch((err: unknown) => {
        setMetaError(errorMessage(err));
      });
  }, []);

  useEffect(() => {
    refreshMeta();
    const id = window.setInterval(refreshMeta, META_POLL_MS);
    return () => {
      window.clearInterval(id);
    };
  }, [refreshMeta]);

  const viewedDate =
    route.kind === "day"
      ? route.date
      : route.kind === "today"
        ? meta?.today
        : undefined;

  let body;
  if (route.kind === "inventory") {
    if (!meta) {
      body = (
        <main className="page">
          {metaError ? <p className="error">{metaError}</p> : <p>加载中…</p>}
        </main>
      );
    } else {
      body = (
        <>
          {metaError ? <p className="error">{metaError}</p> : null}
          <InventoryPage today={meta.today} onInventoryChange={refreshMeta} />
        </>
      );
    }
  } else if (route.kind === "notfound") {
    body = (
      <main className="page">
        <h1>找不到该页</h1>
        <p>
          <a href="/" onClick={(e) => handleNavClick(e, "/")}>
            Today
          </a>
        </p>
      </main>
    );
  } else if (route.kind === "today") {
    if (!meta) {
      body = (
        <main className="page">
          {metaError ? <p className="error">{metaError}</p> : <p>加载中…</p>}
        </main>
      );
    } else {
      body = (
        <>
          {metaError ? <p className="error">{metaError}</p> : null}
          <DayView
            date={meta.today}
            serverToday={meta.today}
            onInventoryChange={refreshMeta}
          />
        </>
      );
    }
  } else {
    body = (
      <DayView
        date={route.date}
        serverToday={meta?.today}
        onInventoryChange={refreshMeta}
      />
    );
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
