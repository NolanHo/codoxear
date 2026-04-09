import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

interface SessionGroupProps {
  title: string;
  subtitle: string;
  collapsed?: boolean;
  canRename?: boolean;
  isSaving?: boolean;
  errorMessage?: string;
  onRename?: (value: string) => Promise<boolean> | boolean;
  onToggle?: () => void;
  children: ComponentChildren;
}

export function SessionGroup({
  title,
  subtitle,
  collapsed = false,
  canRename = false,
  isSaving = false,
  errorMessage = "",
  onRename,
  onToggle,
  children,
}: SessionGroupProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const savingRef = useRef(false);

  useEffect(() => {
    if (!isEditing) {
      setDraftTitle(title);
    }
  }, [title, isEditing]);

  async function commitRename() {
    if (!onRename || savingRef.current) {
      return;
    }

    savingRef.current = true;
    const saved = await onRename(draftTitle);
    savingRef.current = false;
    if (saved) {
      setIsEditing(false);
    }
  }

  return (
    <section className="sessionGroup">
      <div className="sessionGroupShell">
        <div className="sessionGroupHeader" aria-expanded={!collapsed}>
          <span className="sessionGroupHeading">
            {isEditing ? (
              <input
                type="text"
                className="sessionGroupRenameInput"
                value={draftTitle}
                onInput={(event) => setDraftTitle(event.currentTarget.value)}
                onBlur={() => {
                  void commitRename();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void commitRename();
                  }
                  if (event.key === "Escape") {
                    event.preventDefault();
                    setDraftTitle(title);
                    setIsEditing(false);
                  }
                }}
                disabled={isSaving}
                autoFocus
              />
            ) : (
              <span className="sessionGroupTitle">{title}</span>
            )}
            <span className="sessionGroupSubtitle">{subtitle}</span>
          </span>
          <span className="sessionGroupActions">
            {canRename ? (
              <button
                type="button"
                className="sessionGroupRenameButton"
                onClick={() => {
                  setDraftTitle(title);
                  setIsEditing(true);
                }}
                disabled={isSaving}
              >
                Rename
              </button>
            ) : null}
            {onToggle ? (
              <button
                type="button"
                className="sessionGroupToggleButton"
                onClick={onToggle}
                disabled={isSaving}
              >
                <span className="sessionGroupToggle" aria-hidden="true">{collapsed ? "+" : "-"}</span>
                <span className="visuallyHidden">{collapsed ? "Expand group" : "Collapse group"}</span>
              </button>
            ) : null}
          </span>
        </div>
        {errorMessage ? <p className="sessionGroupError">{errorMessage}</p> : null}
        {collapsed ? null : <div className="sessionGroupList">{children}</div>}
      </div>
    </section>
  );
}
