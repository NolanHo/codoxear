from __future__ import annotations

import json
import urllib.parse
from typing import Any

from ...runtime import ServerRuntime
from ...runtime_facade import build_runtime_facade


def _read_json_object(facade: Any, handler: Any) -> dict[str, Any]:
    body = facade.read_body(handler)
    body_text = body.decode("utf-8")
    if not body_text.strip():
        raise ValueError("empty request body")
    obj = json.loads(body_text)
    if not isinstance(obj, dict):
        raise ValueError("invalid json body (expected object)")
    return obj


def handle_get(runtime: ServerRuntime, handler: Any, path: str, u: Any) -> bool:
    facade = build_runtime_facade(runtime)

    if path == "/api/settings/voice":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.json_response(handler, 200, facade.voice_settings_payload())
        return True

    if path == "/api/notifications/subscription":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        facade.json_response(handler, 200, facade.voice_subscriptions_payload())
        return True

    if path == "/api/notifications/message":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        qs = urllib.parse.parse_qs(u.query)
        message_id = (qs.get("message_id") or [""])[0].strip()
        if not message_id:
            facade.json_response(handler, 400, {"error": "message_id required"})
            return True
        try:
            payload = facade.voice_notification_message_payload(message_id)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown message"})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/notifications/feed":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        qs = urllib.parse.parse_qs(u.query)
        since_raw = (qs.get("since") or ["0"])[0].strip()
        try:
            since_ts = float(since_raw or "0")
        except ValueError:
            facade.json_response(handler, 400, {"error": "invalid since"})
            return True
        facade.json_response(
            handler,
            200,
            facade.voice_notification_feed_payload(since_ts=since_ts),
        )
        return True

    if path == "/api/audio/live.m3u8":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        body = facade.audio_playlist_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/vnd.apple.mpegurl")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(body)
        return True

    if path.startswith("/api/audio/segments/"):
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        segment_name = path.split("/api/audio/segments/", 1)[1]
        try:
            raw = facade.audio_segment_bytes(segment_name)
        except FileNotFoundError:
            handler.send_error(404)
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "video/mp2t")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(raw)
        return True

    return False


def handle_post(runtime: ServerRuntime, handler: Any, path: str, _u: Any) -> bool:
    facade = build_runtime_facade(runtime)

    if path == "/api/settings/voice":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(facade, handler)
        try:
            payload = facade.voice_set_settings(obj)
        except ValueError as e:
            facade.json_response(handler, 400, {"error": str(e)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/notifications/subscription":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(facade, handler)
        try:
            payload = facade.voice_upsert_subscription(obj)
        except ValueError as e:
            facade.json_response(handler, 400, {"error": str(e)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/notifications/subscription/toggle":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(facade, handler)
        endpoint = obj.get("endpoint")
        enabled = obj.get("enabled")
        if not isinstance(endpoint, str) or not endpoint.strip():
            facade.json_response(handler, 400, {"error": "endpoint required"})
            return True
        if not isinstance(enabled, bool):
            facade.json_response(handler, 400, {"error": "enabled must be a boolean"})
            return True
        try:
            payload = facade.voice_toggle_subscription(endpoint=endpoint, enabled=enabled)
        except KeyError:
            facade.json_response(handler, 404, {"error": "unknown subscription"})
            return True
        except ValueError as e:
            facade.json_response(handler, 400, {"error": str(e)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/notifications/test_push":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        try:
            payload = facade.voice_test_push_payload()
        except ValueError as e:
            facade.json_response(handler, 400, {"error": str(e)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/audio/listener":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        obj = _read_json_object(facade, handler)
        client_id = obj.get("client_id")
        enabled = obj.get("enabled")
        if not isinstance(client_id, str) or not client_id.strip():
            facade.json_response(handler, 400, {"error": "client_id required"})
            return True
        if not isinstance(enabled, bool):
            facade.json_response(handler, 400, {"error": "enabled must be a boolean"})
            return True
        payload = facade.audio_listener_heartbeat_payload(
            client_id=client_id,
            enabled=enabled,
        )
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/audio/test_announcement":
        if not facade.require_auth(handler):
            handler._unauthorized()
            return True
        try:
            payload = facade.audio_test_announcement_payload()
        except ValueError as e:
            facade.json_response(handler, 400, {"error": str(e)})
            return True
        facade.json_response(handler, 200, payload)
        return True

    if path == "/api/hooks/notify":
        facade.read_body(handler)
        facade.json_response(handler, 200, {"ignored": True})
        return True

    return False
