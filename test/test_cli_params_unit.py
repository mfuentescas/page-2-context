import http.server
import json
import os
import socketserver
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "page2context.py"
PYTHON = ROOT_DIR / ".venv" / "bin" / "python3"
if not PYTHON.exists():
    PYTHON = Path("python3")


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class CliParamsUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory(prefix="p2cxt_unit_")
        cls.www_dir = Path(cls.tmpdir.name)
        (cls.www_dir / "index.html").write_text(
            """<!DOCTYPE html><html><body><h1>page2context unit test</h1></body></html>""",
            encoding="utf-8",
        )
        handler = http.server.SimpleHTTPRequestHandler
        cls.httpd = _ReusableTCPServer(("127.0.0.1", 0), lambda *a, **k: handler(*a, directory=str(cls.www_dir), **k))
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.test_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=2)
        cls.tmpdir.cleanup()

    def run_tool(self, args):
        result = subprocess.run([str(PYTHON), str(SCRIPT), *args], capture_output=True, text=True)
        return result

    def run_tool_json(self, args):
        result = self.run_tool(args)
        payload = json.loads(result.stdout)
        return result, payload

    def test_help_contains_new_flags(self):
        result = self.run_tool(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--use-chrome", result.stdout)
        self.assertIn("--clean-chrome", result.stdout)
        self.assertIn("--runtime-env-dir", result.stdout)
        self.assertNotIn("--chrome-profile-dir", result.stdout)

    def test_runtime_env_dir_without_url(self):
        result, payload = self.run_tool_json(["--runtime-env-dir", "--json"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload.get("status"), "success")
        self.assertEqual(payload.get("message"), "Runtime environment directory resolved.")

        runtime_dir = payload.get("runtime_env_dir")
        self.assertIsInstance(runtime_dir, str)
        self.assertTrue(runtime_dir)
        self.assertTrue(os.path.isabs(runtime_dir))
        self.assertTrue(Path(runtime_dir).is_dir())

    def test_multiple_use_flags_fail(self):
        result, payload = self.run_tool_json(["--url", self.test_url, "--use-chrome", "--use-firefox", "--json"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload.get("status"), "error")
        self.assertIn("only one --use-*", payload.get("message", ""))

    def test_clean_browser_json_schema(self):
        result, payload = self.run_tool_json(["--clean-chrome", "--json"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload.get("status"), "success")
        self.assertNotIn("history_file", payload)
        self.assertIn("reclaimed_bytes", payload)
        self.assertIn("cleaned_browser_count", payload)

    def test_clean_temp_keeps_history_file(self):
        result, payload = self.run_tool_json(["--clean-temp", "--json"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload.get("status"), "success")
        self.assertIn("history_file", payload)

    def test_default_capture_uses_chrome(self):
        result, payload = self.run_tool_json(["--url", self.test_url, "--json"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload.get("status"), "success")
        self.assertEqual(payload.get("browser_profile", {}).get("browser"), "chrome")

    def test_use_chromium_capture(self):
        result, payload = self.run_tool_json(["--url", self.test_url, "--use-chromium", "--json"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload.get("status"), "success")
        self.assertEqual(payload.get("browser_profile", {}).get("browser"), "chromium")


if __name__ == "__main__":
    unittest.main()

