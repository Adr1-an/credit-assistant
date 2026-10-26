"""Справочники и демо: /health, /question-sets, /okved, /demo/clients, /demo/statements/{inn}, /demo/reset."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import ai, refdata
from ..db import get_db
from ..errors import ApiError
from ..models import Application, HistoryEntry
from ..schemas import DemoClient, Error, HealthResponse, Okved, QuestionSets

router = APIRouter()


@router.get("/health", tags=["system"], response_model=HealthResponse, summary="Сервер жив, доступен ли ИИ")
def health():
    try:
        available = bool(ai.is_available())
    except Exception:  # ИИ упал при проверке — значит недоступен
        available = False
    return {"status": "ok", "aiAvailable": available}


@router.get("/question-sets", tags=["goals"], response_model=QuestionSets, response_model_exclude_none=True,
            summary="Список уточняющих вопросов по целям")
def question_sets():
    return refdata.question_sets()


@router.get("/okved", tags=["goals"], response_model=list[Okved], responses={400: {"model": Error}},
            summary="Поиск ОКВЭД по названию или коду")
def search_okved(query: str = Query(min_length=2)):
    return refdata.search_okved(query)


@router.get("/demo/clients", tags=["demo"], response_model=list[DemoClient], response_model_exclude_none=True,
            summary="Тестовые клиенты (для жюри)")
def demo_clients():
    return refdata.demo_clients()


@router.get("/demo/statements/{inn}", tags=["demo"], response_class=FileResponse,
            responses={200: {"content": {"text/csv": {}}}, 404: {"model": Error}},
            summary="Скачать тестовую выписку для ИНН")
def demo_statement(inn: str):
    path = refdata.demo_statement_path(inn)
    if path is None:
        raise ApiError(404, "NOT_FOUND", "Тестовой выписки для этого ИНН нет")
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=f"{inn}.csv")


@router.post("/demo/reset", tags=["demo"], summary="Удалить все заявки и историю (сброс для повторной демонстрации)")
def demo_reset(db: Session = Depends(get_db)):
    # Вся база в этом прототипе — синтетические тестовые данные (см. README), поэтому
    # полный сброс без подтверждения на сервере безопасен. Подтверждение — на фронте.
    deleted = db.query(Application).count()
    db.query(HistoryEntry).delete()
    db.query(Application).delete()
    db.commit()
    return {"status": "ok", "deletedApplications": deleted}
