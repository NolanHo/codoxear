import { useEffect, useRef, useState } from "preact/hooks";
import type { LiveSessionStore } from "../../domains/live-session/store";
import { openAppEventStream, type AppEventStreamEvent } from "../../domains/events/stream";
import type { SessionUiStore } from "../../domains/session-ui/store";
import type { SessionsStore } from "../../domains/sessions/store";
import { getSessionRuntimeId } from "../../lib/session-identity";
import type { SessionSummary } from "../../lib/types";

interface UseAppShellEventsOptions {
  activeSessionBackend?: string;
  activeSessionHistorical?: boolean;
  activeSessionId: string | null;
  activeSessionPending?: boolean;
  activeSessionRuntimeId?: string | null;
  items: SessionSummary[];
  liveSessionStoreApi: LiveSessionStore;
  onConnectionChange?: (connected: boolean) => void;
  refreshNotificationsFeed: () => Promise<void>;
  sessionUiStoreApi: SessionUiStore;
  sessionsStoreApi: SessionsStore;
  workspaceOpen: boolean;
}

function isRecoverableNotFound(error: unknown) {
  return Boolean(error && typeof error === "object" && (error as { status?: unknown }).status === 404);
}

export function useAppShellEvents({
  activeSessionBackend,
  activeSessionHistorical,
  activeSessionId,
  activeSessionPending,
  activeSessionRuntimeId,
  items,
  liveSessionStoreApi,
  onConnectionChange,
  refreshNotificationsFeed,
  sessionUiStoreApi,
  sessionsStoreApi,
  workspaceOpen,
}: UseAppShellEventsOptions) {
  const [connected, setConnected] = useState(false);
  const lastSeqRef = useRef(0);

  useEffect(() => {
    const refreshSessions = () => sessionsStoreApi.refresh().catch(() => undefined);
    const refreshActiveWorkspace = () => {
      if (!activeSessionId || !workspaceOpen) {
        return Promise.resolve();
      }
      if ((activeSessionHistorical && activeSessionBackend === "pi") || activeSessionPending) {
        return Promise.resolve();
      }
      return (activeSessionRuntimeId
        ? sessionUiStoreApi.refresh(activeSessionId, { agentBackend: activeSessionBackend, runtimeId: activeSessionRuntimeId })
        : sessionUiStoreApi.refresh(activeSessionId, { agentBackend: activeSessionBackend }))
        .catch((error) => {
          if (isRecoverableNotFound(error)) {
            return refreshSessions();
          }
          return undefined;
        });
    };
    const pollLiveSession = (sessionId: string, runtimeId?: string | null) => {
      return (runtimeId
        ? liveSessionStoreApi.poll(sessionId, runtimeId)
        : liveSessionStoreApi.poll(sessionId))
        .catch((error) => {
          if (isRecoverableNotFound(error)) {
            return refreshSessions();
          }
          return undefined;
        });
    };
    const resyncAll = () => {
      void refreshSessions();
      void refreshNotificationsFeed();
      if (activeSessionId) {
        void pollLiveSession(activeSessionId, activeSessionRuntimeId);
      }
      void refreshActiveWorkspace();
    };

    const handleEvent = (event: AppEventStreamEvent) => {
      if (typeof event.seq === "number" && Number.isFinite(event.seq)) {
        lastSeqRef.current = Math.max(lastSeqRef.current, Math.floor(event.seq));
      }
      const eventType = String(event.type || "").trim();
      if (!eventType) {
        return;
      }
      if (eventType === "stream.resync") {
        resyncAll();
        return;
      }
      if (eventType === "sessions.invalidate" || eventType === "attention.invalidate") {
        void refreshSessions();
        return;
      }
      if (eventType === "notifications.invalidate") {
        void refreshNotificationsFeed();
        return;
      }

      const targetRuntimeId = typeof event.runtime_id === "string" && event.runtime_id.trim()
        ? event.runtime_id.trim()
        : null;
      const targetSessionId = typeof event.session_id === "string" && event.session_id.trim()
        ? event.session_id.trim()
        : null;
      const session = items.find((item) => (
        (targetSessionId && item.session_id === targetSessionId)
        || (targetRuntimeId && getSessionRuntimeId(item) === targetRuntimeId)
      )) ?? null;

      if (eventType === "session.workspace.invalidate") {
        if (!workspaceOpen || !activeSessionId || !targetSessionId) {
          return;
        }
        if (activeSessionId !== targetSessionId && activeSessionRuntimeId !== targetRuntimeId) {
          return;
        }
        void refreshActiveWorkspace();
        return;
      }

      if (eventType === "session.live.invalidate" || eventType === "session.transport.invalidate") {
        if (!session) {
          void refreshSessions();
          return;
        }
        if ((session.historical && session.agent_backend === "pi") || session.pending_startup) {
          void refreshSessions();
          return;
        }
        const runtimeId = targetRuntimeId || getSessionRuntimeId(session);
        const liveState = liveSessionStoreApi.getState();
        const isTracked = session.session_id === activeSessionId
          || session.busy === true
          || typeof liveState.offsetsBySessionId[session.session_id] === "number";
        if (!isTracked) {
          return;
        }
        void pollLiveSession(session.session_id, runtimeId);
        if (eventType === "session.transport.invalidate") {
          void refreshSessions();
        }
      }
    };

    const stream = openAppEventStream({
      cursor: lastSeqRef.current,
      onEvent: handleEvent,
      onStateChange: (state) => {
        const isOpen = state === "open";
        setConnected(isOpen);
        onConnectionChange?.(isOpen);
      },
    });

    return () => {
      stream.close();
    };
  }, [activeSessionBackend, activeSessionHistorical, activeSessionId, activeSessionPending, activeSessionRuntimeId, items, liveSessionStoreApi, onConnectionChange, refreshNotificationsFeed, sessionUiStoreApi, sessionsStoreApi, workspaceOpen]);

  return { connected };
}
