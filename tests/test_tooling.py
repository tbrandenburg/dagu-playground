"""Test the real client over loopback HTTP, without mocked transports."""

import argparse
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.client import ApiError, Client, wait
from scripts.manage import integer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, payload = {
            "/api/v1/missing": (404, {"message": "not found"}),
            "/api/v1/broken": (503, {"message": "coordinator unavailable"}),
            "/api/v1/list": (200, []),
            "/api/v1/dags/job/dag-runs/rejected": (
                200,
                {"dagRun": {"statusLabel": "rejected"}},
            ),
            "/api/v1/workers": (
                200,
                {
                    "errors": [],
                    "workers": [
                        {"id": "online", "healthStatus": "healthy"},
                        {"id": "stale", "healthStatus": "offline"},
                    ],
                },
            ),
        }.get(self.path, (200, {"ok": True}))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, format: str, *args: object) -> None:
        return


class ToolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client = Client(f"http://127.0.0.1:{cls.server.server_port}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_status_codes_are_preserved(self) -> None:
        for path, status in (("missing", 404), ("broken", 503)):
            with self.subTest(path=path), self.assertRaises(ApiError) as caught:
                self.client.request(path)
            self.assertEqual(caught.exception.status, status)
            self.assertIn(f"HTTP {status}", str(caught.exception))

    def test_success_and_worker_health_filter(self) -> None:
        self.assertEqual(self.client.request("ok"), {"ok": True})
        self.assertEqual([worker["id"] for worker in self.client.workers()], ["online"])

    def test_invalid_response_and_terminal_failure(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "JSON object"):
            self.client.request("list")
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            self.client.finished("job", "rejected")

    def test_wait_success_and_timeout(self) -> None:
        self.assertEqual(wait(lambda: "ready", "success", timeout=0), "ready")
        with self.assertRaisesRegex(TimeoutError, "never-ready"):
            wait(lambda: False, "never-ready", timeout=0)

    def test_integer_boundaries_and_invalid_values(self) -> None:
        self.assertEqual(integer("1", 1, 5), 1)
        self.assertEqual(integer("5", 1, 5), 5)
        for value in ("0", "6", "x", "1.5"):
            with (
                self.subTest(value=value),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                integer(value, 1, 5)

    def test_connection_failure_is_not_empty_success(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        client = Client(f"http://127.0.0.1:{port}")
        with self.assertRaises(ConnectionError) as caught:
            client.request("workers")
        self.assertIn("Cannot reach", str(caught.exception))
        self.assertIn(str(port), str(caught.exception))

    def test_port_boundaries_and_empty_topology(self) -> None:
        self.assertEqual(integer("1024", 1024, 65535), 1024)
        self.assertEqual(integer("65535", 1024, 65535), 65535)
        for value in ("1023", "65536"):
            with (
                self.subTest(value=value),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                integer(value, 1024, 65535)
        with self.assertRaisesRegex(RuntimeError, "No running workers"):
            self.client.ready(0)


if __name__ == "__main__":
    unittest.main()
