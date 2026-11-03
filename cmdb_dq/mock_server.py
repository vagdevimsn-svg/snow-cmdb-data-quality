"""Local mock of the ServiceNow Table API, serving a JSON export with Basic auth and paging.

Lets you exercise --live mode end to end without an instance:
    python -m cmdb_dq.mock_server --data sample_data/cmdb_export.json --port 8080
    SN_INSTANCE_URL=http://127.0.0.1:8080 SN_USER=demo SN_PASSWORD=demo python -m cmdb_dq --live
"""
from __future__ import annotations

import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def make_handler(tables: dict[str, list[dict]], user: str, password: str):
    expected = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (http.server naming)
            if self.headers.get("Authorization") != expected:
                return self._send(401, {"error": {"message": "User Not Authenticated"}})
            url = urlparse(self.path)
            prefix = "/api/now/table/"
            if not url.path.startswith(prefix):
                return self._send(404, {"error": {"message": "Not found"}})
            table = url.path[len(prefix):]
            if table not in tables:
                return self._send(400, {"error": {"message": f"Invalid table {table}"}})
            q = parse_qs(url.query)
            limit = int(q.get("sysparm_limit", ["10000"])[0])
            offset = int(q.get("sysparm_offset", ["0"])[0])
            fields = q.get("sysparm_fields", [""])[0].split(",") if q.get("sysparm_fields") else None
            rows = tables[table][offset:offset + limit]
            if fields:
                rows = [{k: r.get(k, "") for k in fields} for r in rows]
            return self._send(200, {"result": rows})

        def log_message(self, fmt, *args):  # keep test output quiet
            pass

    return Handler


def serve(data_path: str | Path, port: int = 8080, user: str = "demo", password: str = "demo",
          background: bool = False, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    tables = {"cmdb_ci": data.get("cmdb_ci", []), "cmdb_rel_ci": data.get("cmdb_rel_ci", [])}
    server = ThreadingHTTPServer((host, port), make_handler(tables, user, password))
    if background:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Mock ServiceNow Table API for local testing")
    ap.add_argument("--data", default="sample_data/cmdb_export.json")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    server = serve(args.data, args.port, host=args.host)
    print(f"Mock Table API on http://{args.host}:{args.port} (user demo / password demo)")
    server.serve_forever()


if __name__ == "__main__":
    main()
