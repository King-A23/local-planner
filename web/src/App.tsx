import { useCallback, useEffect, useRef, useState } from "react";

import { ItemEditorHost } from "./ItemEditor";
import { SearchDialog } from "./SearchDialog";
import { AgentPanel } from "./AgentPanel";
import { errorMessage, getMeta, type Meta } from "./api";
import { BackgroundDecorations } from "./BackgroundDecorations";
import { META_POLL_MS } from "./constants";
import { DailyPlanningPage } from "./DailyPlanningPage";
import { DayView } from "./DayView";
import { InventoryPage } from "./InventoryPage";
import { RecurrencesPage } from "./RecurrencesPage";
import { handleNavClick, navigate, parseRoute } from "./route";
import { Shell } from "./Shell";
import { SettingsPage } from "./SettingsPage";
import { UndoToast } from "./UndoToast";

function useLocation(): { pathname: string; search: string } {
  const [location, setLocation] = useState(() => ({
    pathname: window.location.pathname,
    search: window.location.search,
  }));
  useEffect(() => {
    const onPop = () =>
      setLocation({ pathname: window.location.pathname, search: window.location.search });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return location;
}

export function App() {
  const { pathname, search } = useLocation();
  const route = parseRoute(pathname);
  const [searchOpen, setSearchOpen] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [agentOpen, setAgentOpen] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("agent") === "1";
  });
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [agentRunTick, setAgentRunTick] = useState(0);
  const agentTriggerRef = useRef<HTMLElement | null>(null);

  const openAgent = useCallback((trigger: HTMLButtonElement) => {
    agentTriggerRef.current = trigger;
    setAgentOpen((open) => !open);
  }, []);

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

  const agentSurface =
    route.kind === "inventory"
      ? "todo"
      : route.kind === "day"
        ? "day"
        : "today";
  const agentDate = route.kind === "day" ? route.date : null;
  const activeSection =
    route.kind === "settings" ? "settings" : route.kind === "inventory"
      ? "inventory"
      : route.kind === "recurrences"
        ? "recurrences"
        : route.kind === "notfound"
          ? undefined
          : "today";

  const refreshAll = useCallback(() => { setAgentRunTick((tick) => tick + 1); refreshMeta(); }, [refreshMeta]);
  useEffect(() => {
    window.addEventListener("planner:restored", refreshAll);
    window.addEventListener("planner:items-changed", refreshAll);
    return () => {
      window.removeEventListener("planner:restored", refreshAll);
      window.removeEventListener("planner:items-changed", refreshAll);
    };
  }, [refreshAll]);
  useEffect(() => { if (route.kind === "settings") setAgentOpen(false); }, [route.kind]);

  useEffect(() => {
    const open = () => { if (!document.querySelector("dialog[open]")) setSearchOpen(true); };
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !event.altKey && !event.shiftKey && !event.isComposing) {
        event.preventDefault(); open();
      }
    };
    window.addEventListener("keydown", key);
    window.addEventListener("planner:search", open);
    return () => { window.removeEventListener("keydown", key); window.removeEventListener("planner:search", open); };
  }, []);

  let body;
  if (route.kind === "settings") {
    body = <SettingsPage />;
  } else if (route.kind === "inventory") {
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
          <InventoryPage
            today={meta.today}
            onInventoryChange={refreshMeta}
            refreshToken={agentRunTick}
          />
        </>
      );
    }
  } else if (route.kind === "recurrences") {
    if (!meta) {
      body = (
        <main className="page">
          {metaError ? <p className="error">{metaError}</p> : <p>加载中…</p>}
        </main>
      );
    } else {
      const kind = new URLSearchParams(search).get("kind");
      body = (
        <>
          {metaError ? <p className="error">{metaError}</p> : null}
          <RecurrencesPage
            today={meta.today}
            initialKind={kind === "errand" || kind === "plan" ? kind : undefined}
            onChange={refreshMeta}
            refreshToken={agentRunTick}
          />
        </>
      );
    }
  } else if (route.kind === "todayPlanning") {
    body = (
      <DailyPlanningPage
        onChange={refreshMeta}
        onReady={() => {
          refreshMeta();
        }}
        onDefer={() => {
          navigate("/");
        }}
        agentOpen={agentOpen}
        onOpenAgent={openAgent}
        refreshToken={agentRunTick}
      />
    );
  } else if (route.kind === "notfound") {
    body = (
      <main className="page">
        <h1>找不到该页</h1>
        <p>
          <a href="/" onClick={(e) => handleNavClick(e, "/")}>
            今天
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
            planningStatus={meta.planningStatus}
            onStartPlanning={() => {
              navigate("/planning/today");
            }}
            refreshToken={agentRunTick}
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
        planningStatus={
          route.date === meta?.today ? meta?.planningStatus : undefined
        }
        onStartPlanning={() => {
          navigate("/planning/today");
        }}
        refreshToken={agentRunTick}
      />
    );
  }

  return (
    <div className="layout" data-agent-open={agentOpen ? "true" : undefined}>
      <BackgroundDecorations />
      <Shell
        agentStatus={agentStatus}
        inventoryCount={meta?.inventoryCount}
        today={meta?.today}
        viewedDate={viewedDate}
        activeSection={activeSection}
        agentOpen={agentOpen}
        onOpenAgent={openAgent}
        onSearch={() => setSearchOpen(true)}
      >
        {body}
      </Shell>
      <ItemEditorHost />
      {searchOpen && <SearchDialog onClose={() => setSearchOpen(false)} />}
      <UndoToast onChanged={refreshAll} />
      <AgentPanel
        onStatusChange={setAgentStatus}
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        onOpen={() => setAgentOpen(true)}
        triggerRef={agentTriggerRef}
        surface={agentSurface}
        date={agentDate}
        onRan={() => {
          setAgentRunTick((tick) => tick + 1);
          refreshMeta();
        }}
      />
    </div>
  );
}
