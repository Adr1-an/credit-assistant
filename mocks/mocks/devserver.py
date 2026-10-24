"""Запуск заглушек без установки пакетов (только стандартная библиотека Python).

Нужен, если FastAPI не установлен: python devserver.py  → http://localhost:8090
Ведёт себя так же, как app.py: использует тот же logic.route().
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import logic


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send(*logic.route("GET", self.path))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            body = None
        self._send(*logic.route("POST", self.path, body))

    def log_message(self, fmt, *args):
        if os.environ.get("MOCKS_QUIET") != "1":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    print(f"Заглушки: http://localhost:{port}  (данные: {logic.DATA_DIR})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
