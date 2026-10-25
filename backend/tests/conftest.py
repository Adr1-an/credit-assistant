"""Общая подготовка для автотестов бэка.

- Заглушки запускаются отдельным процессом (python mocks/devserver.py) — бэк их не импортирует.
- База: TEST_DATABASE_URL (PostgreSQL), а если не задана — временный файл SQLite.
- Дата оценки фиксирована: 2026-10-24, как в tests/expected-results.json.

Запуск из папки backend/:  python -m pytest -q
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
TESTS_DATA = REPO / "tests"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


MOCKS_PORT = _free_port()
os.environ.update({
    "MOCKS_URL": f"http://127.0.0.1:{MOCKS_PORT}",
    "EVALUATION_DATE": "2026-10-24",
    "CONTRACT_DIR": str(REPO / "contract"),
    "TESTS_DIR": str(TESTS_DATA),
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL")
                    or f"sqlite:///{Path(os.environ.get('TMPDIR', '/tmp')) / 'navigator-test.db'}",
})


@pytest.fixture(scope="session", autouse=True)
def mocks_server():
    env = {**os.environ, "PORT": str(MOCKS_PORT), "MOCKS_QUIET": "1"}
    proc = subprocess.Popen([sys.executable, "devserver.py"], cwd=REPO / "mocks", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{MOCKS_PORT}/health", timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield
    proc.terminate()


@pytest.fixture(scope="session")
def app():
    from app.db import Base, get_engine, init_engine
    from app.main import create_app

    init_engine()
    Base.metadata.drop_all(get_engine())
    return create_app()


@pytest.fixture()
def client(app):
    """Новый клиент API на каждый тест; таблицы очищаются, чтобы тесты не мешали друг другу."""
    from fastapi.testclient import TestClient

    from app.db import Base, get_engine

    with TestClient(app) as c:  # with → запускается lifespan (create_tables)
        with get_engine().begin() as conn:
            for t in reversed(Base.metadata.sorted_tables):
                conn.execute(t.delete())
        yield c


def load(name: str):
    return json.loads((TESTS_DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def cases() -> dict:
    return {c["code"]: c for c in load("cases.json")["cases"]}


@pytest.fixture(scope="session")
def expected() -> dict:
    return {r["code"]: r for r in load("expected-results.json")["results"]}
