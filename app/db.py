"""Подключение к PostgreSQL.

get_db() — «зависимость» FastAPI: на каждый запрос открывает сессию и закрывает её после.
Таблицы создаются при старте сервера (create_all) — для прототипа без миграций.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def init_engine(url: str | None = None):
    global _engine, _SessionLocal
    _engine = create_engine(url or get_settings().DATABASE_URL, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    return _engine or init_engine()


def create_tables() -> None:
    from . import models  # noqa: F401  — чтобы таблицы зарегистрировались в Base

    Base.metadata.create_all(get_engine())


def get_db() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
