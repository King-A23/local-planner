import { useEffect, useState } from "react";

import { errorMessage, getMeta, type Meta } from "./api";
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
    return () => {
      cancelled = true;
    };
  }, []);

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
      body = <DayView date={meta.today} />;
    }
  } else {
    body = <DayView date={route.date} />;
  }

  return <Shell inventoryCount={meta?.inventoryCount}>{body}</Shell>;
}
