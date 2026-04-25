import errno
import json
import threading
import unittest
from unittest.mock import patch

from codoxear.pi_broker_protocol import PiBrokerSocketProtocol


class _FakeReadFile:
    def __init__(
        self,
        line: bytes = b"",
        *,
        readline_exc: BaseException | None = None,
    ) -> None:
        self._line = line
        self._readline_exc = readline_exc
        self.closed = False

    def readline(self) -> bytes:
        if self._readline_exc is not None:
            raise self._readline_exc
        return self._line

    def close(self) -> None:
        self.closed = True


class _FakeConn:
    def __init__(
        self,
        line: bytes = b"",
        *,
        readline_exc: BaseException | None = None,
        sendall_exc: BaseException | None = None,
    ) -> None:
        self.file = _FakeReadFile(line, readline_exc=readline_exc)
        self._sendall_exc = sendall_exc
        self.sent: list[bytes] = []
        self.sendall_calls = 0
        self.closed = False

    def makefile(self, _mode: str) -> _FakeReadFile:
        return self.file

    def sendall(self, data: bytes) -> None:
        self.sendall_calls += 1
        if self._sendall_exc is not None:
            raise self._sendall_exc
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


class _FakeBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = None
        self.close_calls = 0

    def _close(self) -> None:
        self.close_calls += 1


def _request_line(payload: object) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def _sent_payloads(conn: _FakeConn) -> list[dict[str, object]]:
    return [json.loads(chunk.decode("utf-8")) for chunk in conn.sent]


class TestPiBrokerSocketProtocol(unittest.TestCase):
    def test_handle_conn_returns_error_for_malformed_json(self) -> None:
        protocol = PiBrokerSocketProtocol(_FakeBroker())
        conn = _FakeConn(b'{"cmd":\n')

        protocol.handle_conn(conn)

        self.assertTrue(conn.file.closed)
        self.assertTrue(conn.closed)
        self.assertEqual(len(conn.sent), 1)
        payload = _sent_payloads(conn)[0]
        self.assertIn("Expecting value", str(payload["error"]))
        self.assertIn("column", str(payload["error"]))

    def test_handle_conn_returns_unknown_cmd_for_non_object_request(self) -> None:
        protocol = PiBrokerSocketProtocol(_FakeBroker())
        conn = _FakeConn(_request_line(["state"]))

        protocol.handle_conn(conn)

        self.assertEqual(_sent_payloads(conn), [{"error": "unknown cmd"}])
        self.assertTrue(conn.file.closed)
        self.assertTrue(conn.closed)

    def test_handle_conn_returns_unknown_cmd_for_unknown_command(self) -> None:
        protocol = PiBrokerSocketProtocol(_FakeBroker())
        conn = _FakeConn(_request_line({"cmd": "bogus"}))

        protocol.handle_conn(conn)

        self.assertEqual(_sent_payloads(conn), [{"error": "unknown cmd"}])
        self.assertTrue(conn.file.closed)
        self.assertTrue(conn.closed)

    def test_handle_conn_suppresses_disconnected_peer_errors_from_read(self) -> None:
        protocol = PiBrokerSocketProtocol(_FakeBroker())
        conn = _FakeConn(
            readline_exc=ConnectionResetError(
                errno.ECONNRESET,
                "Connection reset by peer",
            )
        )

        protocol.handle_conn(conn)

        self.assertEqual(conn.sendall_calls, 0)
        self.assertEqual(conn.sent, [])
        self.assertTrue(conn.file.closed)
        self.assertTrue(conn.closed)

    def test_handle_conn_swallows_broken_pipe_while_reporting_errors(self) -> None:
        protocol = PiBrokerSocketProtocol(_FakeBroker())
        conn = _FakeConn(
            _request_line({"cmd": "state"}),
            sendall_exc=BrokenPipeError(errno.EPIPE, "Broken pipe"),
        )

        with patch.object(protocol, "_dispatch_command", side_effect=RuntimeError("boom")):
            protocol.handle_conn(conn)

        self.assertEqual(conn.sendall_calls, 1)
        self.assertTrue(conn.file.closed)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
