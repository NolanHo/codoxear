import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "../../app/providers";
import { api } from "../../lib/api";
import { SessionsPane } from "./SessionsPane";

vi.mock("../../lib/api", () => ({
  api: {
    createSession: vi.fn().mockResolvedValue({ ok: true, broker_pid: 42 }),
    editSession: vi.fn().mockResolvedValue({ ok: true, alias: "Updated session" }),
    editCwdGroup: vi.fn().mockResolvedValue({ ok: true }),
    deleteSession: vi.fn().mockResolvedValue({ ok: true }),
  },
}));

let root: HTMLDivElement | null = null;

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

async function click(element: Element) {
  await act(async () => {
    (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

async function setInputValue(element: HTMLInputElement, value: string) {
  await act(async () => {
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

async function pressKey(element: Element, key: string) {
  await act(async () => {
    element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  });
}

function createSessionsStore(initialState: any, options?: { onRefresh?: () => void | Promise<void> }) {
  let state = initialState;
  const listeners = new Set<() => void>();

  const emit = () => {
    listeners.forEach((listener) => listener());
  };

  const store = {
    getState: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    refresh: vi.fn(async (refreshOptions?: { preferNewest?: boolean }) => {
      if (refreshOptions?.preferNewest) {
        state = { ...state, activeSessionId: state.items[0]?.session_id ?? null };
      }
      await options?.onRefresh?.();
      emit();
    }),
    select: vi.fn((sessionId: string) => {
      state = { ...state, activeSessionId: sessionId };
      emit();
    }),
    setState(next: any) {
      state = next;
      emit();
    },
  };

  return store;
}

function renderSessionsPane(state: any, options?: { onRefresh?: () => void | Promise<void> }) {
  const sessionsStore = createSessionsStore(state, options);

  root = document.createElement("div");
  document.body.appendChild(root);
  render(
    <AppProviders sessionsStore={sessionsStore as any}>
      <SessionsPane />
    </AppProviders>,
    root,
  );

  return sessionsStore;
}

describe("SessionsPane", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    if (root) {
      render(null, root);
      root.remove();
      root = null;
    }
  });

  it("renders the sessions surface with active session cards and metadata badges", () => {
    renderSessionsPane({
      items: [
        {
          session_id: "sess-1",
          alias: "Inbox cleanup",
          first_user_message: "整理一下今天的会话",
          agent_backend: "pi",
          busy: true,
          owned: true,
          queue_len: 2,
        },
      ],
      activeSessionId: "sess-1",
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    expect(root?.querySelector("[data-testid='sessions-surface']")).not.toBeNull();
    expect(root?.querySelectorAll("[data-testid='session-card']")).toHaveLength(1);
    const activeCard = root?.querySelector<HTMLButtonElement>("[data-testid='session-card'][aria-current='true']");
    expect(activeCard).not.toBeNull();
    expect(activeCard?.getAttribute("aria-current")).toBe("true");
    expect(root?.textContent).toContain("Inbox cleanup");
    expect(root?.textContent).toContain("pi");
    expect(root?.textContent).toContain("web");
  });

  it("uses the first user message as the primary title when no alias is present", () => {
    renderSessionsPane({
      items: [
        {
          session_id: "4a145abccb9a48889dc7f3e5bed735f2",
          first_user_message: "我准备用 preact + vite 重构web端，请帮我出个规划",
          cwd: "/Users/huapeixuan/Documents/Code/codoxear",
          agent_backend: "pi",
        },
      ],
      activeSessionId: null,
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const title = root?.querySelector(".sessionTitle")?.textContent || "";
    const preview = root?.querySelector(".sessionPreview")?.textContent || "";
    expect(title).toContain("我准备用 preact + vite 重构web端，请帮我出个规划");
    expect(preview).toContain("/Users/huapeixuan/Documents/Code/codoxear");
    expect(title).not.toContain("4a145abccb9a48889dc7f3e5bed735f2");
  });

  it("deletes a session after confirmation and refreshes the list", async () => {
    const confirm = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirm);
    const sessionsStore = renderSessionsPane({
      items: [{ session_id: "sess-1", alias: "Inbox cleanup", agent_backend: "pi" }],
      activeSessionId: "sess-1",
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const deleteButton = Array.from(root?.querySelectorAll("button") || []).find((button) => button.textContent?.includes("Delete"));
    expect(deleteButton).toBeDefined();
    deleteButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await flush();

    expect(api.deleteSession).toHaveBeenCalledWith("sess-1");
    expect(sessionsStore.refresh).toHaveBeenCalled();
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("terminal-owned session"));
  });

  it("duplicates a session with launch settings and selects the new session", async () => {
    const sessionsStore = renderSessionsPane({
      items: [
        {
          session_id: "sess-1",
          alias: "Inbox cleanup",
          cwd: "/tmp/project",
          agent_backend: "codex",
          provider_choice: "openai-api",
          model: "gpt-5.4",
          reasoning_effort: "high",
          service_tier: "fast",
          transport: "tmux",
        },
      ],
      activeSessionId: "sess-1",
      loading: false,
      newSessionDefaults: null,
      recentCwds: ["/tmp/project"],
      cwdGroups: {},
      tmuxAvailable: true,
    });

    sessionsStore.refresh = vi.fn(async () => {
      sessionsStore.setState({
        ...sessionsStore.getState(),
        items: [
          ...sessionsStore.getState().items,
          {
            session_id: "sess-2",
            alias: "Inbox cleanup copy",
            cwd: "/tmp/project",
            agent_backend: "codex",
            broker_pid: 42,
          },
        ],
      });
    });

    const duplicateButton = Array.from(root?.querySelectorAll("button") || []).find((button) => button.textContent?.includes("Duplicate"));
    expect(duplicateButton).toBeDefined();
    duplicateButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await flush();

    expect(api.createSession).toHaveBeenCalledWith({
      cwd: "/tmp/project",
      backend: "codex",
      model: "gpt-5.4",
      model_provider: "openai",
      preferred_auth_method: "apikey",
      reasoning_effort: "high",
      service_tier: "fast",
      create_in_tmux: true,
    });
    expect(sessionsStore.select).toHaveBeenCalledWith("sess-2");
  });

  it("opens the edit dialog and saves legacy session metadata", async () => {
    const sessionsStore = renderSessionsPane({
      items: [
        { session_id: "sess-1", alias: "Inbox cleanup", agent_backend: "pi", priority_offset: 0 },
        { session_id: "sess-2", alias: "Release prep", agent_backend: "pi" },
      ],
      activeSessionId: "sess-1",
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const editButton = Array.from(root?.querySelectorAll("button") || []).find((button) => button.textContent?.includes("Edit"));
    expect(editButton).toBeDefined();
    editButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await flush();

    const dependencySelect = root?.querySelector('select[name="dependencySessionId"]') as HTMLSelectElement;
    await act(async () => {
      dependencySelect.value = "sess-2";
      dependencySelect.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const saveButton = Array.from(root?.querySelectorAll("button") || []).find((button) => button.textContent?.includes("Save changes"));
    expect(saveButton).toBeDefined();
    saveButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    await flush();

    expect(api.editSession).toHaveBeenCalledWith("sess-1", {
      name: "Inbox cleanup",
      priority_offset: 0,
      snooze_until: null,
      dependency_session_id: "sess-2",
    });
    expect(sessionsStore.refresh).toHaveBeenCalled();
  });

  it("groups same-cwd sessions and orders groups by freshest activity", () => {
    renderSessionsPane({
      items: [
        { session_id: "sess-1", alias: "Docs polish", cwd: "/work/docs", agent_backend: "pi", updated_ts: 30 },
        { session_id: "sess-2", alias: "Bug bash", cwd: "/work/api", agent_backend: "codex", updated_ts: 120 },
        { session_id: "sess-3", alias: "Release notes", cwd: "/work/docs", agent_backend: "pi", updated_ts: 20 },
      ],
      activeSessionId: "sess-3",
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const groups = Array.from(root?.querySelectorAll<HTMLElement>(".sessionGroup") || []);
    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.querySelector(".sessionGroupTitle")?.textContent?.trim())).toEqual(["api", "docs"]);
    expect(groups[1]?.textContent).toContain("Docs polish");
    expect(groups[1]?.textContent).toContain("Release notes");
  });

  it("selects grouped session cards when clicked", async () => {
    const sessionsStore = renderSessionsPane({
      items: [
        { session_id: "sess-1", alias: "Docs polish", cwd: "/work/docs", agent_backend: "pi", updated_ts: 30 },
        { session_id: "sess-2", alias: "Release notes", cwd: "/work/docs", agent_backend: "pi", updated_ts: 20 },
      ],
      activeSessionId: null,
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const cardButtons = root?.querySelectorAll<HTMLButtonElement>(".sessionCardButton") || [];
    await click(cardButtons[1]!);
    await flush();

    expect(sessionsStore.select).toHaveBeenCalledWith("sess-2");
  });

  it("persists cwd group rename and refreshes sessions", async () => {
    const sessionsStore = renderSessionsPane(
      {
        items: [{ session_id: "sess-1", alias: "Docs polish", cwd: "/work/docs", agent_backend: "pi" }],
        activeSessionId: null,
        loading: false,
        newSessionDefaults: null,
        recentCwds: [],
        cwdGroups: {},
        tmuxAvailable: false,
      },
      {
        onRefresh: () => {
          sessionsStore.setState({
            ...sessionsStore.getState(),
            cwdGroups: { "/work/docs": { label: "Knowledge Base" } },
          });
        },
      },
    );

    const renameButton = root?.querySelector<HTMLButtonElement>(".sessionGroupRenameButton");
    expect(renameButton).not.toBeNull();
    await click(renameButton!);

    const input = root?.querySelector<HTMLInputElement>(".sessionGroupRenameInput");
    expect(input).not.toBeNull();
    await setInputValue(input!, "Knowledge Base");
    await pressKey(input!, "Enter");
    await flush();

    expect(api.editCwdGroup).toHaveBeenCalledWith({ cwd: "/work/docs", label: "Knowledge Base" });
    expect(sessionsStore.refresh).toHaveBeenCalledTimes(1);
  });

  it("persists cwd group collapse and hides cards after refresh", async () => {
    const sessionsStore = renderSessionsPane(
      {
        items: [{ session_id: "sess-1", alias: "Docs polish", cwd: "/work/docs", agent_backend: "pi" }],
        activeSessionId: null,
        loading: false,
        newSessionDefaults: null,
        recentCwds: [],
        cwdGroups: {},
        tmuxAvailable: false,
      },
      {
        onRefresh: () => {
          sessionsStore.setState({
            ...sessionsStore.getState(),
            cwdGroups: { "/work/docs": { collapsed: true } },
          });
        },
      },
    );

    const toggleButton = root?.querySelector<HTMLButtonElement>(".sessionGroupToggleButton");
    expect(toggleButton).not.toBeNull();
    await click(toggleButton!);
    await flush();

    expect(api.editCwdGroup).toHaveBeenCalledWith({ cwd: "/work/docs", collapsed: true });
    expect(root?.querySelectorAll("[data-testid='session-card']")).toHaveLength(0);
  });

  it("renders a fallback group for sessions without cwd and disables group actions", () => {
    renderSessionsPane({
      items: [{ session_id: "sess-1", alias: "Inbox", agent_backend: "pi", start_ts: 10 }],
      activeSessionId: null,
      loading: false,
      newSessionDefaults: null,
      recentCwds: [],
      cwdGroups: {},
      tmuxAvailable: false,
    });

    const group = root?.querySelector<HTMLElement>(".sessionGroup");
    expect(group?.querySelector(".sessionGroupTitle")?.textContent).toContain("No working directory");
    expect(group?.querySelector(".sessionGroupSubtitle")?.textContent).toContain("Sessions without a cwd");
    expect(group?.querySelector(".sessionGroupRenameButton")).toBeNull();
    expect(group?.querySelector(".sessionGroupToggleButton")).toBeNull();
  });
});
