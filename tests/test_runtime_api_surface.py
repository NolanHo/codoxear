import sys
import types
import unittest

from codoxear.runtime import RuntimeApi, build_server_runtime
from codoxear.runtime_api_exports import RUNTIME_API_EXPORTS
from codoxear.sessions.runtime_access import manager_runtime


class TestRuntimeApiSurface(unittest.TestCase):
    def test_build_server_runtime_keeps_route_modules_off_runtime_api(self) -> None:
        module = types.ModuleType("fake_server")
        module.static_dir = "/tmp/static"
        route_names = {
            "_http_assets_routes": object(),
            "_http_auth_routes": object(),
            "_http_events_routes": object(),
            "_http_notification_routes": object(),
            "_http_session_read_routes": object(),
            "_http_session_write_routes": object(),
            "_http_file_routes": object(),
        }
        for name, value in route_names.items():
            setattr(module, name, value)

        api = RuntimeApi(module, exports=("static_dir",))
        runtime = build_server_runtime(module, manager=object(), event_hub=object(), api=api)

        self.assertEqual(
            runtime.get_route_modules,
            (
                route_names["_http_assets_routes"],
                route_names["_http_auth_routes"],
                route_names["_http_events_routes"],
                route_names["_http_notification_routes"],
                route_names["_http_session_read_routes"],
                route_names["_http_file_routes"],
            ),
        )
        self.assertEqual(
            runtime.post_route_modules,
            (
                route_names["_http_auth_routes"],
                route_names["_http_notification_routes"],
                route_names["_http_session_write_routes"],
                route_names["_http_file_routes"],
            ),
        )
        self.assertEqual(runtime.api.static_dir, "/tmp/static")
        with self.assertRaises(AttributeError):
            _ = runtime.api.http_assets_routes

    def test_manager_runtime_fallback_allows_modules_without_route_attrs(self) -> None:
        module = types.ModuleType("fake_manager_runtime_module")
        module.EVENT_HUB = object()
        module.static_dir = "/tmp/static"
        module._build_runtime_api = lambda: RuntimeApi(module, exports=("static_dir",))

        manager_cls = type("ExternalManager", (), {"__module__": module.__name__})
        manager = manager_cls()
        original_module = sys.modules.get(module.__name__)
        sys.modules[module.__name__] = module
        try:
            runtime = manager_runtime(manager)
            self.assertIs(manager._runtime, runtime)
            self.assertIs(manager_runtime(manager), runtime)
        finally:
            if original_module is None:
                sys.modules.pop(module.__name__, None)
            else:
                sys.modules[module.__name__] = original_module

        self.assertEqual(runtime.api.static_dir, "/tmp/static")
        self.assertEqual(runtime.get_route_modules, ())
        self.assertEqual(runtime.post_route_modules, ())

    def test_runtime_api_exports_include_spawn_timeout_constant(self) -> None:
        self.assertIn("TMUX_META_WAIT_SECONDS", RUNTIME_API_EXPORTS)

    def test_runtime_api_exports_exclude_route_modules(self) -> None:
        for name in (
            "http_assets_routes",
            "http_auth_routes",
            "http_events_routes",
            "http_file_routes",
            "http_notification_routes",
            "http_session_read_routes",
            "http_session_write_routes",
        ):
            self.assertNotIn(name, RUNTIME_API_EXPORTS)


if __name__ == "__main__":
    unittest.main()
