"""Ошибки API в одном виде: { "code": "...", "message": "...", "details": {} }.

Код ошибки — из openapi.yaml → ErrorCode. Сайт показывает message, логика смотрит на code.
В коде бэка мы просто пишем: raise ApiError(409, "INVALID_STATUS", "...").
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("navigator")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"code": code, "message": message, "details": details or {}}


def not_found(what: str = "Заявка") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} не найдена")


def invalid_status(status: str, action: str) -> ApiError:
    return ApiError(409, "INVALID_STATUS", "Это действие сейчас недоступно",
                    {"status": status, "action": action})


def _field_path(loc) -> str:
    # loc выглядит как ("body", "passport", "series") — убираем "body"
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # FastAPI по умолчанию отвечает 422 в своём формате. Контракт хочет 400 и наш формат.
        problems = [{"field": _field_path(e["loc"]), "problem": e["msg"]} for e in exc.errors()]
        fields_ = [p["field"] for p in problems]
        if any(f.startswith("passport") for f in fields_):
            code, msg = "PASSPORT_INVALID", "Проверьте паспортные данные: серия — 4 цифры, номер — 6 цифр, даты — ГГГГ-ММ-ДД"
        elif any(f == "inn" for f in fields_):
            code, msg = "INN_INVALID", "ИНН должен состоять из 12 цифр"
        else:
            code, msg = "VALIDATION_ERROR", "Проверьте введённые данные"
        return JSONResponse(status_code=400, content=error_body(code, msg, {"fields": problems}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return JSONResponse(status_code=404, content=error_body("NOT_FOUND", "Не найдено"))
        return JSONResponse(status_code=exc.status_code,
                            content=error_body("VALIDATION_ERROR", str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # В ErrorCode нет кода для внутренней ошибки — см. «Вопросы к контракту», п. 21.
        log.exception("Необработанная ошибка: %s", exc)
        return JSONResponse(status_code=500, content=error_body(
            "INTERNAL_ERROR", "Что-то пошло не так. Попробуйте ещё раз чуть позже"))
