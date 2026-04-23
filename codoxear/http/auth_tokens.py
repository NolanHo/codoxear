from __future__ import annotations

import base64
import hmac
import json
from typing import Any


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_dec(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))


def sign_cookie(payload: dict[str, Any], *, secret: bytes) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = hmac.new(secret, raw, "sha256").digest()
    return f"{_b64u(raw)}.{_b64u(sig)}"


def verify_cookie(value: str, *, secret: bytes, now_ts: float) -> dict[str, Any] | None:
    try:
        body_part, sig_part = value.split(".", 1)
        raw = _b64u_dec(body_part)
        sig = _b64u_dec(sig_part)
        want = hmac.new(secret, raw, "sha256").digest()
        if not hmac.compare_digest(sig, want):
            return None
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        exp_raw = payload.get("exp")
        if exp_raw is None:
            return None
        exp = int(exp_raw)
        if exp <= int(now_ts):
            return None
        return payload
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_cookies(header: str | None) -> dict[str, str]:
    if not header:
        return {}
    out: dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def require_auth(handler: Any, *, cookie_name: str, secret: bytes, now_ts: float) -> bool:
    cookies = parse_cookies(handler.headers.get("Cookie"))
    token = cookies.get(cookie_name)
    if not token:
        return False
    return verify_cookie(token, secret=secret, now_ts=now_ts) is not None


def set_auth_cookie(
    handler: Any,
    *,
    cookie_name: str,
    cookie_path: str,
    cookie_ttl_seconds: int,
    cookie_secure: bool,
    secret: bytes,
    now_ts: float,
) -> None:
    exp = int(now_ts) + cookie_ttl_seconds
    token = sign_cookie({"exp": exp}, secret=secret)
    attrs = [
        f"{cookie_name}={token}",
        f"Path={cookie_path}",
        "HttpOnly",
        "SameSite=Strict",
        f"Max-Age={cookie_ttl_seconds}",
    ]
    forwarded_proto_raw = handler.headers.get("X-Forwarded-Proto")
    forwarded_proto = (
        str(forwarded_proto_raw).lower() if forwarded_proto_raw is not None else ""
    )
    if cookie_secure or forwarded_proto == "https":
        attrs.append("Secure")
    handler.send_header("Set-Cookie", "; ".join(attrs))
