"""Сервис-заглушка внешних систем на FastAPI. Порт 8090.

Запуск: uvicorn app:app --host 0.0.0.0 --port 8090
Вся логика — в logic.py, здесь только HTTP-обёртка.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import logic

app = FastAPI(
    title="Заглушки внешних сервисов",
    version="1.0.0",
    description="ЕГРИП, налоги, БКИ, ФССП, банкротство, паспорт. Данные синтетические. Правила — contract/mocks-contract.md.",
)


async def _body(request: Request):
    if request.method != "POST":
        return None
    try:
        return await request.json()
    except Exception:
        return None


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def dispatch(path: str, request: Request):
    status, payload = logic.route(request.method, "/" + path, await _body(request))
    return JSONResponse(status_code=status, content=payload)
