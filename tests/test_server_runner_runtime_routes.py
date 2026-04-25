import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from codoxear.http import server_runner


class _HandlerHarness:
    def __init__(self, path: str, body: bytes = b"") -> None:
        self.path = path
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.errors: list[int] = []

    def send_error(self, status: int) -> None:
        self.errors.append(status)

    def send_response(self, _status: int) -> None:
        return

    def send_header(self, _key: str, _value: str) -> None:
        return

    def end_headers(self) -> None:
        return


class TestServerRunnerRouteDispatch(unittest.TestCase):
    def test_get_dispatch_uses_runtime_route_collection(self) -> None:
        route = SimpleNamespace(handle_get=Mock(return_value=True))
        runtime = SimpleNamespace(
            api=SimpleNamespace(
                URL_PREFIX="",
                strip_url_prefix=lambda prefix, path: path,
                json_response=Mock(),
            ),
            get_route_modules=(route,),
            post_route_modules=(),
        )
        handler = _HandlerHarness("/api/ping")

        server_runner.make_handler(runtime).do_GET(handler)  # type: ignore[arg-type]

        route.handle_get.assert_called_once()
        runtime.api.json_response.assert_not_called()
        self.assertEqual(handler.errors, [])

    def test_post_dispatch_uses_runtime_route_collection(self) -> None:
        route = SimpleNamespace(handle_post=Mock(return_value=True))
        runtime = SimpleNamespace(
            api=SimpleNamespace(
                URL_PREFIX="",
                strip_url_prefix=lambda prefix, path: path,
                json_response=Mock(),
            ),
            get_route_modules=(),
            post_route_modules=(route,),
        )
        handler = _HandlerHarness("/api/ping", body=b"{}")

        server_runner.make_handler(runtime).do_POST(handler)  # type: ignore[arg-type]

        route.handle_post.assert_called_once()
        runtime.api.json_response.assert_not_called()
        self.assertEqual(handler.errors, [])


if __name__ == "__main__":
    unittest.main()
