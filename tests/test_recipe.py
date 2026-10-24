"""Exercise recipe download failures through a real loopback HTTP server."""

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

from scripts.recipe import adapt, download

HELLO_SHA256 = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/missing":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"x" * 65537 if self.path == "/large" else b"hello\n")

    def log_message(self, format: str, *args: object) -> None:
        return


class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_download_and_checksum_guard(self) -> None:
        self.assertEqual(download(self.base + "/recipe", HELLO_SHA256), "hello\n")
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            download(self.base + "/recipe", "0" * 64)

    def test_http_failure_and_download_limit(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            download(self.base + "/missing", HELLO_SHA256)
        self.assertEqual(caught.exception.code, 404)
        with self.assertRaisesRegex(RuntimeError, "64 KiB"):
            download(self.base + "/large", HELLO_SHA256)

    def test_adaptation_preserves_steps_without_integrations(self) -> None:
        steps = "  - id: check\n    run: echo intact\n"
        spec = adapt("schedule: '*/5 * * * *'\nsecrets: []\nsteps:\n" + steps)
        self.assertTrue(spec.endswith("steps:\n" + steps))
        self.assertIn("pool: playground", spec)
        self.assertNotIn("schedule:", spec)
        self.assertNotIn("secrets:", spec)

    def test_missing_and_ambiguous_steps_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "one upstream steps block"):
            adapt("description: no steps\n")
        with self.assertRaisesRegex(RuntimeError, "one upstream steps block"):
            adapt("description: duplicate\nsteps:\n[]\nsteps:\n[]\n")


if __name__ == "__main__":
    unittest.main()
