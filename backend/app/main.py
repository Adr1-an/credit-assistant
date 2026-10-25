"""Точка входа сервера.

Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000 (из папки backend/)
Все запросы — под /api, Swagger — на /docs.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import create_tables
from .errors import install_error_handlers
from .routers import applications, flow, reference, staff

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Умный финансовый навигатор для ИП — API",
        version="0.9.0",
        description="Сервер по контракту v0.9 (contract/openapi.yaml). Деньги — целые рубли, "
                    "клиент работает с заявкой по id, сотрудник — через /api/staff.",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                       allow_methods=["*"], allow_headers=["*"])
    for r in (reference.router, applications.router, flow.router, staff.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
