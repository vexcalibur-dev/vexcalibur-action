from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from helpers import REPO_ROOT


class FakeOsvServerTests(unittest.TestCase):
    def test_fake_osv_server_handles_querybatch_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port_file = root / "port"
            request_log = root / "requests.jsonl"
            server = subprocess.Popen(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests" / "fixtures" / "fake_osv_server.py"),
                    "--port-file",
                    str(port_file),
                    "--request-log",
                    str(request_log),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                port = _wait_for_port_file(port_file, server)
                response = _post_json(
                    f"http://127.0.0.1:{port}/v1/querybatch",
                    {
                        "queries": [
                            {"package": {"purl": "pkg:pypi/django@1.2"}},
                            {"package": {"purl": "pkg:npm/minimist@0.0.8"}},
                        ]
                    },
                )

                self.assertEqual(
                    response,
                    {
                        "results": [
                            {
                                "vulns": [
                                    {
                                        "id": "GHSA-action-django-0001",
                                        "modified": "2026-01-01T00:00:00Z",
                                    }
                                ]
                            },
                            {},
                        ]
                    },
                )
                self.assertEqual(
                    json.loads(request_log.read_text(encoding="utf-8")),
                    {
                        "path": "/v1/querybatch",
                        "body": {
                            "queries": [
                                {"package": {"purl": "pkg:pypi/django@1.2"}},
                                {"package": {"purl": "pkg:npm/minimist@0.0.8"}},
                            ]
                        },
                    },
                )
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                if server.stderr is not None:
                    server.stderr.close()


def _wait_for_port_file(port_file: Path, server: subprocess.Popen[str]) -> int:
    for _ in range(50):
        if port_file.exists():
            return int(port_file.read_text(encoding="utf-8"))
        if server.poll() is not None:
            stderr = "" if server.stderr is None else server.stderr.read()
            raise AssertionError(f"fake OSV server exited early: {stderr}")
        time.sleep(0.1)
    raise AssertionError("fake OSV server did not write its port file")


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
