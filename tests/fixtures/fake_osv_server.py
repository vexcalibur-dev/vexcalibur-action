from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a fake OSV-compatible test server."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--port-file", type=Path, required=True)
    parser.add_argument("--request-log", type=Path, required=True)
    args = parser.parse_args()

    request_log = args.request_log
    request_log.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(content_length)
            try:
                payload = json.loads(request_body)
            except json.JSONDecodeError:
                self._write_json(400, {"error": "request body must be JSON"})
                return

            with request_log.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "path": self.path,
                            "body": payload,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

            if self.path != "/v1/querybatch":
                self._write_json(404, {"error": "unsupported endpoint"})
                return

            queries = payload.get("queries", [])
            if not isinstance(queries, list):
                self._write_json(400, {"error": "queries must be a list"})
                return

            self._write_json(
                200, {"results": [_result_for_query(query) for query in queries]}
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            response_body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    actual_port = server.server_address[1]
    args.port_file.parent.mkdir(parents=True, exist_ok=True)
    args.port_file.write_text(f"{actual_port}\n", encoding="utf-8")
    server.serve_forever()


def _result_for_query(query: object) -> dict[str, Any]:
    if not isinstance(query, dict):
        return {}
    package = query.get("package")
    if not isinstance(package, dict):
        return {}
    if package.get("purl") != "pkg:pypi/django@1.2":
        return {}
    return {
        "vulns": [
            {
                "id": "GHSA-action-django-0001",
                "modified": "2026-01-01T00:00:00Z",
            }
        ]
    }


if __name__ == "__main__":
    main()
