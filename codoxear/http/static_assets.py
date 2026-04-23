from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any


def is_path_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def static_asset_version(runtime: Any, *, static_dir: Path | None = None) -> str:
    base_dir = runtime.api.STATIC_DIR if static_dir is None else static_dir
    base = base_dir.resolve()
    digest = hashlib.sha256()
    for rel in runtime.api.STATIC_ASSET_VERSION_FILES:
        path = (base / rel).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError(f"static asset escaped static dir: {path}")
        if not path.is_file():
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def read_static_bytes(runtime: Any, path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix != ".html":
        return data
    replacements = {
        runtime.api.STATIC_ASSET_VERSION_PLACEHOLDER.encode("ascii"): static_asset_version(
            runtime,
            static_dir=path.parent,
        ).encode("ascii"),
        runtime.api.STATIC_ATTACH_MAX_BYTES_PLACEHOLDER.encode("ascii"): str(
            runtime.api.ATTACH_UPLOAD_MAX_BYTES
        ).encode("ascii"),
    }
    for placeholder, value in replacements.items():
        if placeholder in data:
            data = data.replace(placeholder, value)
    return data


def candidate_web_dist_dirs(runtime: Any) -> list[Path]:
    out: list[Path] = []
    for candidate in (runtime.api.WEB_DIST_DIR, runtime.api.PACKAGED_WEB_DIST_DIR):
        if candidate not in out:
            out.append(candidate)
    return out


def served_web_dist_dir(runtime: Any) -> Path | None:
    for candidate in candidate_web_dist_dirs(runtime):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _hashed_asset_suffix(asset_path: str) -> str | None:
    stem = Path(asset_path).stem
    if "-" not in stem:
        return None
    suffix = stem.rsplit("-", 1)[-1].strip()
    return suffix or None


def _manifest_asset_token(asset_path: str) -> str | None:
    asset_path = asset_path.strip()
    if not asset_path:
        return None
    hashed = _hashed_asset_suffix(asset_path)
    if hashed:
        return hashed
    return hashlib.sha256(asset_path.encode("utf-8")).hexdigest()[:12]


def asset_version_from_manifest(manifest: dict[str, object]) -> str:
    if not isinstance(manifest, dict):
        return "dev"
    entry = manifest.get("src/main.tsx")
    if not isinstance(entry, dict):
        entry = manifest.get("index.html")
    if not isinstance(entry, dict):
        for value in manifest.values():
            if isinstance(value, dict) and value.get("file"):
                entry = value
                break
    if not isinstance(entry, dict):
        return "dev"
    parts: list[str] = []
    js_token = _manifest_asset_token(str(entry.get("file") or ""))
    if js_token:
        parts.append(js_token)
    css_files = entry.get("css")
    if isinstance(css_files, list):
        for css_path in css_files:
            css_token = _manifest_asset_token(str(css_path or ""))
            if css_token:
                parts.append(css_token)
    return "-".join(parts) or "dev"


def rewrite_web_index_html(runtime: Any, data: str) -> str:
    if not runtime.api.URL_PREFIX:
        return data
    prefix_body = re.escape(runtime.api.URL_PREFIX.lstrip("/"))
    pattern = rf'((?:href|src|content)=["\'])/(?!/|{prefix_body}/)'
    return re.sub(pattern, rf"\1{runtime.api.URL_PREFIX}/", data)


def read_web_index(runtime: Any) -> tuple[str, str]:
    dist_dir = served_web_dist_dir(runtime)
    if dist_dir is not None:
        dist_index = dist_dir / "index.html"
        return rewrite_web_index_html(
            runtime,
            dist_index.read_text(encoding="utf-8"),
        ), "text/html; charset=utf-8"
    legacy_index = runtime.api.LEGACY_STATIC_DIR / "index.html"
    return read_static_bytes(runtime, legacy_index).decode("utf-8"), "text/html; charset=utf-8"


def resolve_public_web_asset(runtime: Any, rel: str) -> Path | None:
    rel_path = Path(rel.lstrip("/"))
    active_dist_dir = served_web_dist_dir(runtime)
    if active_dist_dir is not None:
        dist_candidate = (active_dist_dir / rel_path).resolve()
        if is_path_within(active_dist_dir.resolve(), dist_candidate) and dist_candidate.is_file():
            return dist_candidate
    legacy_candidate = (runtime.api.LEGACY_STATIC_DIR / rel_path).resolve()
    if is_path_within(runtime.api.LEGACY_STATIC_DIR.resolve(), legacy_candidate) and legacy_candidate.is_file():
        return legacy_candidate
    return None


def content_type_for_path(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".webmanifest":
        return "application/manifest+json; charset=utf-8"
    if path.suffix == ".svg":
        return "image/svg+xml; charset=utf-8"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def cache_control_for_path(path: Path) -> str:
    if "/assets/" in path.as_posix():
        return "public, max-age=31536000, immutable"
    return "no-store"
