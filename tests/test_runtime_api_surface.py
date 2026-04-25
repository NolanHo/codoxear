import types
import unittest

from codoxear.runtime import RuntimeApi, build_server_runtime
from codoxear.runtime_api_exports import RUNTIME_API_EXPORTS


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
