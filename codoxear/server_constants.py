from __future__ import annotations

import math
import os
from pathlib import Path

from . import env_file as _env_file
from .agent_backend import get_agent_backend, normalize_agent_backend
from .util import default_app_dir as _default_app_dir


def _load_env_file(path: Path) -> dict[str, str]:
    return _env_file.load_env_file(path)


def _normalize_url_prefix(raw: str | None) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s == "/":
        return ""
    if "://" in s:
        raise ValueError("CODEX_WEB_URL_PREFIX must be a path prefix (not a URL)")
    if "?" in s or "#" in s:
        raise ValueError("CODEX_WEB_URL_PREFIX must not include '?' or '#'")
    if not s.startswith("/"):
        raise ValueError("CODEX_WEB_URL_PREFIX must start with '/'")
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    if s == "/":
        return ""
    return s


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
WEB_DIST_DIR = WEB_DIR / "dist"
LEGACY_STATIC_DIR = ROOT_DIR / "codoxear" / "static"
PACKAGED_WEB_DIST_DIR = LEGACY_STATIC_DIR / "dist"

APP_DIR = _default_app_dir()
STATIC_DIR = LEGACY_STATIC_DIR
STATIC_ASSET_VERSION_PLACEHOLDER = "__CODOXEAR_ASSET_VERSION__"
STATIC_ATTACH_MAX_BYTES_PLACEHOLDER = "__CODOXEAR_ATTACH_MAX_BYTES__"
STATIC_ASSET_VERSION_FILES = ("app.js", "app.css")
SOCK_DIR = APP_DIR / "socks"
PROC_ROOT = Path("/proc")
STATE_PATH = APP_DIR / "state.json"
HMAC_SECRET_PATH = APP_DIR / "hmac_secret"
UPLOAD_DIR = APP_DIR / "uploads"
HARNESS_PATH = APP_DIR / "harness.json"
ALIAS_PATH = APP_DIR / "session_aliases.json"
SIDEBAR_META_PATH = APP_DIR / "session_sidebar.json"
HIDDEN_SESSIONS_PATH = APP_DIR / "hidden_sessions.json"
FILE_HISTORY_PATH = APP_DIR / "session_files.json"
QUEUE_PATH = APP_DIR / "session_queues.json"
RECENT_CWD_PATH = APP_DIR / "recent_cwds.json"
CWD_GROUPS_PATH = APP_DIR / "cwd_groups.json"
PAGE_STATE_DB_PATH = APP_DIR / "sqlite.db"
VOICE_SETTINGS_PATH = APP_DIR / "voice_settings.json"
PUSH_SUBSCRIPTIONS_PATH = APP_DIR / "push_subscriptions.json"
DELIVERY_LEDGER_PATH = APP_DIR / "voice_delivery_ledger.json"
VAPID_PRIVATE_KEY_PATH = APP_DIR / "webpush_vapid_private.pem"

_DOTENV = (Path.cwd() / ".env").resolve()
if _DOTENV.exists():
    for _k, _v in _load_env_file(_DOTENV).items():
        os.environ.setdefault(_k, _v)

COOKIE_NAME = "codoxear_auth"
COOKIE_TTL_SECONDS = int(
    os.environ.get("CODEX_WEB_COOKIE_TTL_SECONDS", str(30 * 24 * 3600))
)
COOKIE_SECURE = os.environ.get("CODEX_WEB_COOKIE_SECURE", "0") == "1"
URL_PREFIX = _normalize_url_prefix(os.environ.get("CODEX_WEB_URL_PREFIX"))
COOKIE_PATH = (URL_PREFIX + "/") if URL_PREFIX else "/"
TMUX_SESSION_NAME = (
    os.environ.get("CODEX_WEB_TMUX_SESSION") or "codoxear"
).strip() or "codoxear"
TMUX_META_WAIT_SECONDS = 3.0
TMUX_SHORT_APP_DIR = Path("/tmp/codoxear")

_CODEX_HOME_ENV = os.environ.get("CODEX_HOME")
if _CODEX_HOME_ENV is None or (not _CODEX_HOME_ENV.strip()):
    CODEX_HOME = Path.home() / ".codex"
else:
    CODEX_HOME = Path(_CODEX_HOME_ENV)
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
CODEX_CONFIG_PATH = CODEX_HOME / "config.toml"
PI_NATIVE_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions"
MODELS_CACHE_PATH = CODEX_HOME / "models_cache.json"
PI_HOME = get_agent_backend("pi").home()
PI_SESSIONS_DIR = get_agent_backend("pi").sessions_dir()
PI_SETTINGS_PATH = PI_HOME / "agent" / "settings.json"
PI_MODELS_PATH = PI_HOME / "agent" / "models.json"
PI_AUTH_PATH = PI_HOME / "agent" / "auth.json"
DEFAULT_AGENT_BACKEND = normalize_agent_backend(
    os.environ.get("CODEX_WEB_DEFAULT_AGENT_BACKEND"), default="pi"
)
SUPPORTED_REASONING_EFFORTS = ("xhigh", "high", "medium", "low")
SUPPORTED_PI_REASONING_EFFORTS = ("off", "minimal", "low", "medium", "high", "xhigh")
PI_COMMANDS_CACHE_TTL_SECONDS = float(
    os.environ.get("CODEX_WEB_PI_COMMANDS_CACHE_TTL_SECONDS", "45.0")
)
PI_MODELS_CACHE_NAMESPACE = "pi_models"

DEFAULT_HOST = os.environ.get("CODEX_WEB_HOST", "::")
DEFAULT_PORT = int(os.environ.get("CODEX_WEB_PORT", "8743"))
USE_LEGACY_WEB = os.environ.get("CODOXEAR_USE_LEGACY_WEB", "0") == "1"
HARNESS_DEFAULT_IDLE_MINUTES = 5
HARNESS_DEFAULT_MAX_INJECTIONS = 10
HARNESS_SWEEP_SECONDS = float(os.environ.get("CODEX_WEB_HARNESS_SWEEP_SECONDS", "2.5"))
QUEUE_SWEEP_SECONDS = float(os.environ.get("CODEX_WEB_QUEUE_SWEEP_SECONDS", "1.0"))
VOICE_PUSH_SWEEP_SECONDS = float(
    os.environ.get("CODEX_WEB_VOICE_PUSH_SWEEP_SECONDS", "1.0")
)
QUEUE_IDLE_GRACE_SECONDS = float(
    os.environ.get("CODEX_WEB_QUEUE_IDLE_GRACE_SECONDS", "10.0")
)
BRIDGE_TRANSPORT_PROBE_STALE_SECONDS = float(
    os.environ.get("CODEX_WEB_BRIDGE_TRANSPORT_PROBE_STALE_SECONDS", "2.0")
)
BRIDGE_TRANSPORT_RPC_TIMEOUT_SECONDS = float(
    os.environ.get("CODEX_WEB_BRIDGE_TRANSPORT_RPC_TIMEOUT_SECONDS", "0.35")
)
BRIDGE_OUTBOUND_FAILURE_MAX_ATTEMPTS = int(
    os.environ.get("CODEX_WEB_BRIDGE_OUTBOUND_FAILURE_MAX_ATTEMPTS", "3")
)
BRIDGE_OUTBOUND_FAILURE_MAX_AGE_SECONDS = float(
    os.environ.get("CODEX_WEB_BRIDGE_OUTBOUND_FAILURE_MAX_AGE_SECONDS", "8.0")
)
HARNESS_MAX_SCAN_BYTES = int(
    os.environ.get("CODEX_WEB_HARNESS_MAX_SCAN_BYTES", str(8 * 1024 * 1024))
)
DISCOVER_MIN_INTERVAL_SECONDS = float(
    os.environ.get("CODEX_WEB_DISCOVER_MIN_INTERVAL_SECONDS", "60.0")
)
CHAT_INIT_SEED_SCAN_BYTES = int(
    os.environ.get("CODEX_WEB_CHAT_INIT_SEED_SCAN_BYTES", str(512 * 1024))
)
CHAT_INIT_MAX_SCAN_BYTES = int(
    os.environ.get("CODEX_WEB_CHAT_INIT_MAX_SCAN_BYTES", str(128 * 1024 * 1024))
)
CHAT_INDEX_INCREMENT_BYTES = int(
    os.environ.get("CODEX_WEB_CHAT_INDEX_INCREMENT_BYTES", str(2 * 1024 * 1024))
)
CHAT_INDEX_RESEED_THRESHOLD_BYTES = int(
    os.environ.get("CODEX_WEB_CHAT_INDEX_RESEED_THRESHOLD_BYTES", str(16 * 1024 * 1024))
)
CHAT_INDEX_MAX_EVENTS = int(os.environ.get("CODEX_WEB_CHAT_INDEX_MAX_EVENTS", "12000"))
METRICS_WINDOW = int(os.environ.get("CODEX_WEB_METRICS_WINDOW", "256"))
FILE_READ_MAX_BYTES = int(
    os.environ.get("CODEX_WEB_FILE_READ_MAX_BYTES", str(2 * 1024 * 1024))
)
FILE_HISTORY_MAX = int(os.environ.get("CODEX_WEB_FILE_HISTORY_MAX", "20"))
FILE_SEARCH_LIMIT = int(os.environ.get("CODEX_WEB_FILE_SEARCH_LIMIT", "120"))
FILE_SEARCH_TIMEOUT_SECONDS = float(
    os.environ.get("CODEX_WEB_FILE_SEARCH_TIMEOUT_SECONDS", "0.75")
)
FILE_SEARCH_MAX_CANDIDATES = int(
    os.environ.get("CODEX_WEB_FILE_SEARCH_MAX_CANDIDATES", "200000")
)
GIT_DIFF_MAX_BYTES = int(
    os.environ.get("CODEX_WEB_GIT_DIFF_MAX_BYTES", str(800 * 1024))
)
GIT_DIFF_TIMEOUT_SECONDS = float(
    os.environ.get("CODEX_WEB_GIT_DIFF_TIMEOUT_SECONDS", "4.0")
)
GIT_WORKTREE_TIMEOUT_SECONDS = float(
    os.environ.get("CODEX_WEB_GIT_WORKTREE_TIMEOUT_SECONDS", "10.0")
)
GIT_CHANGED_FILES_MAX = int(os.environ.get("CODEX_WEB_GIT_CHANGED_FILES_MAX", "400"))
ATTACH_UPLOAD_MAX_BYTES = int(
    os.environ.get("CODEX_WEB_ATTACH_MAX_BYTES", str(16 * 1024 * 1024))
)
ATTACH_UPLOAD_BODY_MAX_BYTES = int(
    os.environ.get(
        "CODEX_WEB_ATTACH_BODY_MAX_BYTES",
        str((4 * ((ATTACH_UPLOAD_MAX_BYTES + 2) // 3)) + (64 * 1024)),
    )
)
FILE_LIST_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".svn",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
        ".venv",
    }
)
MARKDOWN_EXTENSIONS = frozenset({"md", "markdown", "mdown", "mkd"})
TEXTUAL_EXTENSIONS = frozenset(
    {
        "bash",
        "c",
        "cc",
        "cfg",
        "conf",
        "cpp",
        "css",
        "csv",
        "diff",
        "go",
        "h",
        "hpp",
        "htm",
        "html",
        "ini",
        "java",
        "js",
        "json",
        "jsonl",
        "log",
        "md",
        "markdown",
        "mdown",
        "mkd",
        "patch",
        "py",
        "rs",
        "scss",
        "sh",
        "sql",
        "svg",
        "toml",
        "ts",
        "tsx",
        "txt",
        "xml",
        "yaml",
        "yml",
        "zsh",
    }
)
TEXTUAL_FILENAMES = frozenset({"dockerfile", "license", "makefile", "readme"})
SIDEBAR_PRIORITY_HALF_LIFE_SECONDS = 8.0 * 3600.0
SIDEBAR_PRIORITY_LAMBDA = math.log(2.0) / SIDEBAR_PRIORITY_HALF_LIFE_SECONDS
RECENT_CWD_MAX = int(os.environ.get("CODEX_WEB_RECENT_CWD_MAX", "256"))
HARNESS_PROMPT_PREFIX = """Unattended-mode instructions (optimize for 8+ hours, minimal turns, minimal repetition, maximal progress)

- Maintain four internal sections:
  1. Deliverables
     - The concrete outputs the agent owes the user by the end of the task.
     - Stable unless the user changes the request.
  2. Completed
     - Verified facts already established while producing the Deliverables.
  3. Next actions
     - Ordered concrete steps from the current state toward the Deliverables.
  4. Parked user decisions
     - Decisions or inputs that only the user can provide.

- Working rules:
  - Keep these sections internal. Surface them only when yielding is necessary.
  - Default to continuing in the same turn.
  - Before each action, reason until the approach, failure modes, and verification path are clear.
  - Exploration should happen through reading, tracing, inspection, and reasoning.
  - Avoid trial and error.
  - Resolve crashes, bugs, and design mistakes yourself unless a true user decision is required.
  - Use the strongest available verification.
  - Do not repeat the same command, edit, or analysis without a concrete new reason.

- Yield only when:
  - all Deliverables are finished and supported by Completed;
  - the only remaining gap is a Parked user decision;
  - or the next step is irreversible or high-risk and needs explicit user confirmation.

- End-of-turn gate (only when yielding is necessary):
  - Run a clean-room adversarial review via a dedicated subagent.
  - Give it: user intent, Deliverables, Completed, remaining Next actions, Parked user decisions, constraints, and changed artifacts.
  - Apply findings before yielding, or surface the exact remaining user decision or risk.
"""

SESSION_LIST_ROW_KEYS = (
    "session_id",
    "runtime_id",
    "thread_id",
    "display_name",
    "title",
    "alias",
    "first_user_message",
    "cwd",
    "agent_backend",
    "owned",
    "busy",
    "queue_len",
    "git_branch",
    "transport",
    "blocked",
    "snoozed",
    "historical",
    "pending_startup",
    "focused",
)
SESSION_LIST_PAGE_SIZE = 50
SESSION_LIST_GROUP_PAGE_SIZE = 12
SESSION_LIST_RECENT_GROUP_LIMIT = 12
SESSION_HISTORY_PAGE_SIZE = 300
SESSION_LIST_FALLBACK_GROUP_KEY = "__no_working_directory__"


__all__ = [
    "_normalize_url_prefix",
    "ROOT_DIR",
    "WEB_DIR",
    "WEB_DIST_DIR",
    "LEGACY_STATIC_DIR",
    "PACKAGED_WEB_DIST_DIR",
    "APP_DIR",
    "STATIC_DIR",
    "STATIC_ASSET_VERSION_PLACEHOLDER",
    "STATIC_ATTACH_MAX_BYTES_PLACEHOLDER",
    "STATIC_ASSET_VERSION_FILES",
    "SOCK_DIR",
    "PROC_ROOT",
    "STATE_PATH",
    "HMAC_SECRET_PATH",
    "UPLOAD_DIR",
    "HARNESS_PATH",
    "ALIAS_PATH",
    "SIDEBAR_META_PATH",
    "HIDDEN_SESSIONS_PATH",
    "FILE_HISTORY_PATH",
    "QUEUE_PATH",
    "RECENT_CWD_PATH",
    "CWD_GROUPS_PATH",
    "PAGE_STATE_DB_PATH",
    "VOICE_SETTINGS_PATH",
    "PUSH_SUBSCRIPTIONS_PATH",
    "DELIVERY_LEDGER_PATH",
    "VAPID_PRIVATE_KEY_PATH",
    "_DOTENV",
    "COOKIE_NAME",
    "COOKIE_TTL_SECONDS",
    "COOKIE_SECURE",
    "URL_PREFIX",
    "COOKIE_PATH",
    "TMUX_SESSION_NAME",
    "TMUX_META_WAIT_SECONDS",
    "TMUX_SHORT_APP_DIR",
    "CODEX_HOME",
    "CODEX_SESSIONS_DIR",
    "CODEX_CONFIG_PATH",
    "PI_NATIVE_SESSIONS_DIR",
    "MODELS_CACHE_PATH",
    "PI_HOME",
    "PI_SESSIONS_DIR",
    "PI_SETTINGS_PATH",
    "PI_MODELS_PATH",
    "PI_AUTH_PATH",
    "DEFAULT_AGENT_BACKEND",
    "SUPPORTED_REASONING_EFFORTS",
    "SUPPORTED_PI_REASONING_EFFORTS",
    "PI_COMMANDS_CACHE_TTL_SECONDS",
    "PI_MODELS_CACHE_NAMESPACE",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "USE_LEGACY_WEB",
    "HARNESS_DEFAULT_IDLE_MINUTES",
    "HARNESS_DEFAULT_MAX_INJECTIONS",
    "HARNESS_SWEEP_SECONDS",
    "QUEUE_SWEEP_SECONDS",
    "VOICE_PUSH_SWEEP_SECONDS",
    "QUEUE_IDLE_GRACE_SECONDS",
    "BRIDGE_TRANSPORT_PROBE_STALE_SECONDS",
    "BRIDGE_TRANSPORT_RPC_TIMEOUT_SECONDS",
    "BRIDGE_OUTBOUND_FAILURE_MAX_ATTEMPTS",
    "BRIDGE_OUTBOUND_FAILURE_MAX_AGE_SECONDS",
    "HARNESS_MAX_SCAN_BYTES",
    "DISCOVER_MIN_INTERVAL_SECONDS",
    "CHAT_INIT_SEED_SCAN_BYTES",
    "CHAT_INIT_MAX_SCAN_BYTES",
    "CHAT_INDEX_INCREMENT_BYTES",
    "CHAT_INDEX_RESEED_THRESHOLD_BYTES",
    "CHAT_INDEX_MAX_EVENTS",
    "METRICS_WINDOW",
    "FILE_READ_MAX_BYTES",
    "FILE_HISTORY_MAX",
    "FILE_SEARCH_LIMIT",
    "FILE_SEARCH_TIMEOUT_SECONDS",
    "FILE_SEARCH_MAX_CANDIDATES",
    "GIT_DIFF_MAX_BYTES",
    "GIT_DIFF_TIMEOUT_SECONDS",
    "GIT_WORKTREE_TIMEOUT_SECONDS",
    "GIT_CHANGED_FILES_MAX",
    "ATTACH_UPLOAD_MAX_BYTES",
    "ATTACH_UPLOAD_BODY_MAX_BYTES",
    "FILE_LIST_IGNORED_DIRS",
    "MARKDOWN_EXTENSIONS",
    "TEXTUAL_EXTENSIONS",
    "TEXTUAL_FILENAMES",
    "SIDEBAR_PRIORITY_HALF_LIFE_SECONDS",
    "SIDEBAR_PRIORITY_LAMBDA",
    "RECENT_CWD_MAX",
    "HARNESS_PROMPT_PREFIX",
    "SESSION_LIST_ROW_KEYS",
    "SESSION_LIST_PAGE_SIZE",
    "SESSION_LIST_GROUP_PAGE_SIZE",
    "SESSION_LIST_RECENT_GROUP_LIMIT",
    "SESSION_HISTORY_PAGE_SIZE",
    "SESSION_LIST_FALLBACK_GROUP_KEY",
]
