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
import { GoalDetailPage, GoalsPage } from "./GoalsPage";
import { RecurrencesPage } from "./RecurrencesPage";
import { handleNavClick, navigate, parseRoute } from "./route";
import { Shell } from "./Shell";
import { SettingsPage } from "./SettingsPage";
import { UndoToast } from "./UndoToast";
import { matchesAssistantShortcut } from "./assistantKeyboard";

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
  const [agentFocusRequest, setAgentFocusRequest] = useState(0);
  const [agentRunTick, setAgentRunTick] = useState(0);
  const [goalRecoveryGeneration, setGoalRecoveryGeneration] = useState<string | null>(null);
  const [goalContextReady, setGoalContextReady] = useState(false);
  const [planningContext, setPlanningContext] = useState<{
    draftId: string; goalId: string | null; selectedPhaseId: string | null; expectedDraftRevision: number;
  } | null>(null);
  const agentTriggerRef = useRef<HTMLElement | null>(null);

  const openAgent = useCallback((trigger: HTMLButtonElement) => {
    agentTriggerRef.current = trigger;
    setAgentOpen((open) => !open);
  }, []);

  useEffect(() => {
    let composing = false;
    const compositionStart = () => { composing = true; };
    const compositionEnd = () => { composing = false; };
    const open = () => {
      if (composing || document.querySelector("dialog[open]")) return;
      if (route.kind === "settings") navigate("/");
      if (!agentOpen && document.activeElement instanceof HTMLElement) agentTriggerRef.current = document.activeElement;
      setAgentOpen(true);
      setAgentFocusRequest((value) => value + 1);
    };
    const key = (event: KeyboardEvent) => {
      // The native menu owns this chord in WKWebView, avoiding double dispatch.
      if (window.__PLANNER_DESKTOP_WINDOW__ || event.defaultPrevented || composing) return;
      if (matchesAssistantShortcut(event, /Mac|iPhone|iPad/.test(navigator.platform))) {
        if (document.querySelector("dialog[open]")) return;
        event.preventDefault(); open();
      }
    };
    window.addEventListener("compositionstart", compositionStart);
    window.addEventListener("compositionend", compositionEnd);
    window.addEventListener("keydown", key);
    window.addEventListener("planner:open-assistant", open);
    return () => {
      window.removeEventListener("compositionstart", compositionStart);
      window.removeEventListener("compositionend", compositionEnd);
      window.removeEventListener("keydown", key);
      window.removeEventListener("planner:open-assistant", open);
    };
  }, [agentOpen, route.kind]);

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
        : route.kind === "goals"
          ? "goals"
          : route.kind === "goal"
            ? "goal"
            : "today";
  const agentDate = route.kind === "day" ? route.date : null;
  const agentGoalId = route.kind === "goal" ? route.id : null;
  const activeSection =
    route.kind === "settings" ? "settings" : route.kind === "inventory"
      ? "inventory"
      : route.kind === "recurrences"
        ? "recurrences"
        : route.kind === "goals" || route.kind === "goal"
          ? "goals"
        : route.kind === "notfound"
          ? undefined
          : "today";

  const refreshAll = useCallback(() => { setAgentRunTick((tick) => tick + 1); refreshMeta(); }, [refreshMeta]);
  useEffect(() => {
    setGoalContextReady(false);
  }, [route.kind, route.kind === "goal" ? route.id : ""]);
  useEffect(() => {
    window.addEventListener("planner:restored", refreshAll);
    window.addEventListener("planner:items-changed", refreshAll);
    return () => {
      window.removeEventListener("planner:restored", refreshAll);
      window.removeEventListener("planner:items-changed", refreshAll);
    };
  }, [refreshAll]);
  useEffect(() => {
    const beginPlanning = (event: Event) => {
      const detail = (event as CustomEvent<Partial<{
        draftId: string; goalId: string | null; selectedPhaseId: string | null; expectedDraftRevision: number;
      }>>).detail;
      if (!detail?.draftId || typeof detail.expectedDraftRevision !== "number") return;
      setPlanningContext({
        draftId: detail.draftId,
        goalId: detail.goalId ?? null,
        selectedPhaseId: detail.selectedPhaseId ?? null,
        expectedDraftRevision: detail.expectedDraftRevision,
      });
      setAgentOpen(true);
    };
    window.addEventListener("planner:planning-context", beginPlanning);
    const updatePlanningRevision = (event: Event) => {
      const detail = (event as CustomEvent<{ draftId?: string; revision?: number }>).detail;
      if (!detail?.draftId || typeof detail.revision !== "number") return;
      const revision = detail.revision;
      setPlanningContext((current) => {
        if (!current || current.draftId !== detail.draftId) return current;
        return { ...current, expectedDraftRevision: revision };
      });
    };
    const selectPlanningPhase = (event: Event) => {
      const detail = (event as CustomEvent<{
        draftId?: string; goalId?: string | null; selectedPhaseId?: string | null;
      }>).detail;
      if (!detail?.draftId) return;
      setPlanningContext((current) => {
        if (!current || current.draftId !== detail.draftId) return current;
        return { ...current, selectedPhaseId: detail.selectedPhaseId ?? null };
      });
    };
    window.addEventListener("planner:planning-draft-updated", updatePlanningRevision);
    window.addEventListener("planner:planning-phase-selected", selectPlanningPhase);
    const clearPlanning = () => { setPlanningContext(null); setAgentOpen(false); };
    window.addEventListener("planner:planning-context-clear", clearPlanning);
    return () => {
      window.removeEventListener("planner:planning-context", beginPlanning);
      window.removeEventListener("planner:planning-draft-updated", updatePlanningRevision);
      window.removeEventListener("planner:planning-phase-selected", selectPlanningPhase);
      window.removeEventListener("planner:planning-context-clear", clearPlanning);
    };
  }, []);
  useEffect(() => { if (route.kind === "settings") setAgentOpen(false); }, [route.kind]);
  useEffect(() => {
    if (route.kind !== "goals" && route.kind !== "goal") setPlanningContext(null);
    if (route.kind === "goals" && planningContext?.goalId) setPlanningContext(null);
    if (route.kind === "goal" && planningContext && planningContext.goalId !== route.id) setPlanningContext(null);
  }, [route.kind, route.kind === "goal" ? route.id : "", planningContext?.goalId]);

  // Every assistant entry on a planning page shares the same draft workflow,
  // including the header button, a persisted open panel and desktop shortcuts.
  useEffect(() => {
    if (agentOpen && goalContextReady && !planningContext && !agentStatus &&
        (route.kind === "goals" || route.kind === "goal"))
      window.dispatchEvent(new Event("planner:planning-request"));
  }, [agentOpen, goalContextReady, planningContext, agentStatus, route.kind, agentGoalId]);

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
  } else if (route.kind === "goals") {
    body = <GoalsPage onChange={refreshAll} onRecoveryGeneration={(generation) => { setGoalRecoveryGeneration(generation); setGoalContextReady(true); }} refreshToken={agentRunTick} />;
  } else if (route.kind === "goal") {
    body = <GoalDetailPage key={route.id} id={route.id} onChange={refreshAll} onRecoveryGeneration={(generation) => { setGoalRecoveryGeneration(generation); setGoalContextReady(true); }} refreshToken={agentRunTick} />;
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
        focusRequest={agentFocusRequest}
        onStatusChange={setAgentStatus}
        open={agentOpen}
        onClose={() => setAgentOpen(false)}
        onOpen={() => setAgentOpen(true)}
        triggerRef={agentTriggerRef}
        surface={agentSurface}
        date={agentDate}
        goalId={agentGoalId}
        recoveryGeneration={goalRecoveryGeneration}
        contextReady={agentSurface !== "goals" && agentSurface !== "goal" || (goalContextReady && !!planningContext && planningContext.goalId === agentGoalId)}
        mode={agentSurface === "goals" || agentSurface === "goal" ? "planning" : "execution"}
        draftId={planningContext?.draftId ?? null}
        selectedPhaseId={planningContext?.selectedPhaseId ?? null}
        expectedDraftRevision={planningContext?.expectedDraftRevision ?? null}
        onRan={() => {
          setAgentRunTick((tick) => tick + 1);
          refreshMeta();
        }}
      />
    </div>
  );
}
