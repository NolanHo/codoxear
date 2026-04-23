import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "codoxear"
SERVER = ROOT / "server.py"
VOICE_PUSH = ROOT / "voice_push.py"


class TestBackendSeamsSource(unittest.TestCase):
    def test_server_dispatches_http_routes_through_modules(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        runner = (ROOT / "http" / "server_runner.py").read_text(encoding="utf-8")
        self.assertIn("from .http.routes import assets as _http_assets_routes", source)
        self.assertIn("from .http.routes import sessions_read as _http_session_read_routes", source)
        self.assertIn("route_module.handle_get(runtime, self, path, u)", runner)
        self.assertIn("route_module.handle_post(runtime, self, path, u)", runner)

    def test_server_uses_payload_sidebar_and_pi_bridge_seams(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        delegates = (ROOT / "sessions" / "manager_delegates.py").read_text(encoding="utf-8")
        combined = source + "\n" + delegates
        self.assertIn("from .sessions import payloads as _session_payloads", source)
        self.assertIn("from .sessions import live_payloads as _session_live_payloads", source)
        self.assertIn("from .sessions import pi_session_files as _pi_session_files", source)
        self.assertIn("from .sessions import resume_candidates as _resume_candidates", source)
        self.assertIn("from .sessions import background as _session_background", source)
        self.assertIn("from .sessions import lifecycle as _session_lifecycle", source)
        self.assertIn("from .sessions import page_state as _page_state", source)
        self.assertIn("from .sessions import listing as _session_listing", source)
        self.assertIn("from .sessions import session_catalog as _session_catalog", source)
        self.assertIn("from .sessions import session_control as _session_control", source)
        self.assertIn("from .sessions import sidebar_state as _sidebar_state_module", source)
        self.assertIn("from .sessions import transport as _session_transport", source)
        self.assertIn("from .workspace import file_access as _workspace_file_access", source)
        self.assertIn("from .workspace import file_search as _workspace_file_search", source)
        self.assertIn("from .pi import ui_bridge as _pi_ui_bridge", source)
        self.assertIn("self._sidebar_state_facade().persist_session_ui_state()", combined)
        self.assertIn("_pi_ui_bridge.submit_ui_response(", combined)

    def test_server_builds_explicit_runtime_object(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("from .runtime import ServerRuntime, build_server_runtime", source)
        self.assertIn("RUNTIME = MANAGER._runtime", source)
        self.assertIn("build_server_runtime(", source)

    def test_file_routes_delegate_workspace_behavior_to_service_owner(self) -> None:
        source = (ROOT / "http" / "routes" / "files.py").read_text(encoding="utf-8")
        self.assertIn("from ...workspace import service as _workspace_service", source)
        self.assertIn("_workspace_service.read_session_file", source)
        self.assertIn("_workspace_service.search_session_files", source)
        self.assertIn("_workspace_service.list_session_files", source)
        self.assertIn("_workspace_service.write_session_file", source)
        self.assertIn("_workspace_service.inject_session_attachment", source)

    def test_session_routes_delegate_creation_to_owner_and_keep_server_listing_surfaces(self) -> None:
        read_source = (ROOT / "http" / "routes" / "sessions_read.py").read_text(encoding="utf-8")
        write_source = (ROOT / "http" / "routes" / "sessions_write.py").read_text(encoding="utf-8")
        self.assertIn("from ...sessions import creation as _session_creation", read_source)
        self.assertIn("_session_creation.read_new_session_defaults(", read_source)
        self.assertIn("sv._session_list_payload(", read_source)
        self.assertIn("sv._first_user_message_preview_from_log", read_source)
        self.assertIn("sv._first_user_message_preview_from_pi_session", read_source)
        self.assertIn("from ...sessions import creation as _session_creation", write_source)
        self.assertIn("_session_creation.parse_create_session_request(sv, obj)", write_source)

    def test_server_delegates_session_catalog_identity_lookups(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        delegates = (ROOT / "sessions" / "manager_delegates.py").read_text(encoding="utf-8")
        combined = source + "\n" + delegates
        self.assertIn("from .sessions import session_catalog as _session_catalog", source)
        self.assertIn("_session_catalog.service(self).runtime_session_id_for_identifier(session_id)", combined)
        self.assertIn("_session_catalog.service(self).durable_session_id_for_identifier(session_id)", combined)
        self.assertIn("_session_catalog.service(self).page_state_ref_for_session_id(session_id)", combined)
        self.assertIn("_session_catalog.service(self).get_session(session_id)", combined)
        self.assertIn("_session_catalog.service(self).list_sessions()", combined)
        self.assertIn("_session_catalog.service(self).refresh_session_meta(", combined)
        self.assertIn("_session_catalog.service(self).discover_existing(", combined)
        self.assertIn("_session_catalog.service(self).refresh_session_state(", combined)
        self.assertIn("_session_catalog.service(self).prune_dead_sessions()", combined)

    def test_server_delegates_session_control_send_and_queue_flows(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        delegates = (ROOT / "sessions" / "manager_delegates.py").read_text(encoding="utf-8")
        combined = source + "\n" + delegates
        self.assertIn("from .sessions import manager_delegates as _manager_delegates", source)
        self.assertIn("class SessionManager(_manager_delegates.SessionManagerDelegates)", source)
        for fragment in [
            "_session_control.service(self).send(session_id, text)",
            "_session_control.service(self).enqueue(session_id, text)",
            "_session_control.service(self).queue_list(session_id)",
            "_session_control.service(self).queue_delete(session_id, int(index))",
            "_session_control.service(self).queue_update(",
            "_session_control.service(self).spawn_web_session(",
            "_message_history.service(self).get_messages_page(",
            "_message_history.service(self).ensure_chat_index(",
            "_message_history.service(self).ensure_pi_chat_index(",
            "_message_history.service(self).mark_log_delta(",
            "_page_state.service(self).queue_len(session_id)",
            "_page_state.service(self).queue_enqueue_local(session_id, text)",
            "_page_state.service(self).files_get(session_id)",
            "_page_state.service(self).harness_get(session_id)",
            "_page_state.service(self).cwd_group_set(",
            "_session_background.service(self).probe_bridge_transport(",
            "_session_background.service(self).session_display_name(session_id)",
            "_session_background.service(self).observe_rollout_delta(",
            "_session_background.service(self).harness_sweep()",
            "_session_background.service(self).queue_sweep()",
            "_session_background.service(self).update_meta_counters()",
            "_session_lifecycle.service(self).catalog_record_for_ref(ref)",
            "_session_lifecycle.service(self).refresh_durable_session_catalog(force=force)",
            "_session_lifecycle.service(self).wait_for_live_session(",
            "_session_lifecycle.service(self).capture_runtime_bound_restart_state(",
            "_session_lifecycle.service(self).stage_runtime_bound_restart_state(",
            "_session_lifecycle.service(self).restore_runtime_bound_restart_state(",
            "_session_transport.service(self).get_state(session_id)",
            "_session_transport.service(self).get_tail(session_id)",
            "_session_transport.service(self).inject_keys(session_id, seq)",
            "_session_transport.service(self).kill_session(session_id)",
            "_session_payloads.service(RUNTIME, manager).session_details_payload(session_id)",
            "_session_payloads.service(RUNTIME).session_context_usage_payload(s, token_val)",
            "_session_payloads.service(RUNTIME).session_turn_timing_payload(",
            "_session_live_payloads.service(RUNTIME, manager).session_live_payload(",
            "_workspace_file_search.search_session_relative_files(",
            "_workspace_file_search.search_session_relative_files(",
            "_resume_candidates.service(RUNTIME).resume_candidate_from_log(",
            "_resume_candidates.service(RUNTIME).list_resume_candidates_for_cwd(",
            "_session_listing.service(RUNTIME).historical_session_id(",
        ]:
            self.assertIn(fragment, combined)

    def test_seam_modules_no_longer_use_bound_server_globals(self) -> None:
        files = [
            ROOT / "http" / "routes" / "assets.py",
            ROOT / "http" / "routes" / "auth.py",
            ROOT / "http" / "routes" / "events.py",
            ROOT / "http" / "routes" / "files.py",
            ROOT / "http" / "routes" / "notifications.py",
            ROOT / "http" / "routes" / "sessions_read.py",
            ROOT / "http" / "routes" / "sessions_write.py",
            ROOT / "sessions" / "payloads.py",
            ROOT / "sessions" / "live_payloads.py",
            ROOT / "pi" / "ui_bridge.py",
        ]
        for path in files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("_SERVER = None", source)
            self.assertNotIn("bind_server_runtime", source)
            self.assertNotIn("def _sv(", source)

    def test_server_runtime_exposes_pi_context_window_helper(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("_pi_model_context_window_impl", source)

    def test_voice_push_uses_attention_namespace(self) -> None:
        source = VOICE_PUSH.read_text(encoding="utf-8")
        self.assertIn("from .attention.derive import", source)
        self.assertIn("compact_notification_state", source)
        self.assertIn("final_response_attention_feed", source)
        self.assertIn("return final_response_attention_feed(", source)
        self.assertNotIn("from codoxear import server as sv", source)


if __name__ == "__main__":
    unittest.main()
