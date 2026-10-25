"""Воронка клиента: шаги 1–3 (создание заявки, согласие, повтор проверок).

Роутер — это «тонкий» слой: принять запрос, вызвать функцию из services/, вернуть ответ.
Вся логика — в services/, чтобы её было удобно тестировать и читать.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import Application, ConsentRequest, CreateApplicationRequest, Error
from ..services import applications as svc

router = APIRouter(tags=["application"])

ERR = {code: {"model": Error} for code in (400, 404, 409, 422, 503)}


@router.post("/applications", response_model=Application, status_code=201,
             responses={200: {"model": Application, "description": "Уже есть открытая заявка — возвращаем её"},
                        400: ERR[400]},
             summary="Шаг 1. Создать заявку по паспорту и ИНН", response_model_exclude_none=True)
def create_application(body: CreateApplicationRequest, response: Response, db: Session = Depends(get_db)):
    app, created = svc.create_application(db, body.passport.model_dump(exclude_none=True), body.hasBusiness, body.inn)
    if not created:
        response.status_code = 200
    return svc.to_client(app)


@router.get("/applications/{id}", response_model=Application, responses={404: ERR[404]},
            summary="Заявка целиком (для клиента, без баллов)", response_model_exclude_none=True)
def get_application(id: str, db: Session = Depends(get_db)):
    return svc.to_client(svc.get_application(db, id))


@router.post("/applications/{id}/consent", response_model=Application,
             responses={k: ERR[k] for k in (404, 409, 422, 503)},
             summary="Шаг 2. Согласие на проверку и запуск проверок", response_model_exclude_none=True)
def give_consent(id: str, body: ConsentRequest, db: Session = Depends(get_db)):
    return svc.to_client(svc.give_consent(db, svc.get_application(db, id)))


@router.post("/applications/{id}/checks", response_model=Application,
             responses={k: ERR[k] for k in (404, 409, 503)},
             summary="Шаг 3. Повторить проверки (если сервис не ответил)", response_model_exclude_none=True)
def retry_checks(id: str, db: Session = Depends(get_db)):
    return svc.to_client(svc.retry_checks(db, svc.get_application(db, id)))
