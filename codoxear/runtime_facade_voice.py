from __future__ import annotations

from typing import Any


class RuntimeFacadeVoiceMixin:
    def voice_settings_payload(self) -> dict[str, Any]:
        return {"ok": True, **self.manager.voice_settings_snapshot()}

    def voice_subscriptions_payload(self) -> dict[str, Any]:
        return {"ok": True, **self.manager.voice_subscriptions_snapshot()}

    def voice_notification_message_payload(self, message_id: str) -> dict[str, Any]:
        state = self.manager.voice_notification_state_for_message(message_id)
        if state is None:
            raise KeyError("unknown message")
        return {"ok": True, **state}

    def voice_notification_feed_payload(self, *, since_ts: float) -> dict[str, Any]:
        items = self.manager.voice_notification_feed_since(since_ts)
        return {"ok": True, "items": items}

    def audio_playlist_bytes(self) -> bytes:
        return self.manager.voice_playlist_bytes()

    def audio_segment_bytes(self, segment_name: str) -> bytes:
        return self.manager.voice_segment_bytes(segment_name)

    def voice_set_settings(self, obj: dict[str, Any]) -> dict[str, Any]:
        payload = self.manager.voice_set_settings(obj)
        return {"ok": True, **payload}

    def voice_upsert_subscription(self, obj: dict[str, Any]) -> dict[str, Any]:
        payload = self.manager.voice_upsert_subscription(
            subscription=obj.get("subscription"),
            user_agent=str(obj.get("user_agent") or ""),
            device_label=str(obj.get("device_label") or ""),
            device_class=str(obj.get("device_class") or ""),
        )
        return {"ok": True, **payload}

    def voice_toggle_subscription(self, *, endpoint: str, enabled: bool) -> dict[str, Any]:
        payload = self.manager.voice_toggle_subscription(
            endpoint=endpoint,
            enabled=enabled,
        )
        return {"ok": True, **payload}

    def voice_test_push_payload(self) -> dict[str, Any]:
        payload = self.manager.voice_send_test_push(session_display_name="Codoxear test")
        return {"ok": True, **payload}

    def audio_listener_heartbeat_payload(
        self,
        *,
        client_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        payload = self.manager.voice_listener_heartbeat(
            client_id=client_id,
            enabled=enabled,
        )
        return {"ok": True, **payload}

    def audio_test_announcement_payload(self) -> dict[str, Any]:
        payload = self.manager.voice_enqueue_test_announcement(
            session_display_name="Codoxear test"
        )
        return {"ok": True, **payload}
