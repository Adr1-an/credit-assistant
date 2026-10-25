"""Воронка клиента: шаги 4–10 и «после выдачи». Логика — в services/flow.py."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import (AdvanceMonthRequest, Application, ChooseOptionRequest, Contract, ContractAnswer,
                       ContractAskRequest, DialogMessageRequest, DialogState, Error, Estimate,
                       EstimateUpdateRequest, GoalsData, HandoffRequest, Notification, Offer, Okved,
                       OkvedSuggestRequest, Questionnaire, Schedule, SignCode, SignRequest, StatementSummary)
from ..services import flow
from ..services.applications import get_application, to_client

router = APIRouter()


def E(*codes):
    return {c: {"model": Error} for c in codes}


OPTS = {"response_model_exclude_none": True}


# ---------- шаг 4 ----------
@router.post("/applications/{id}/statement", tags=["application"], response_model=StatementSummary,
             responses=E(400, 404, 409), summary="Шаг 4. Загрузить выписку из другого банка", **OPTS)
async def upload_statement(id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    return flow.upload_statement(db, get_application(db, id), raw)


@router.post("/applications/{id}/questionnaire", tags=["application"], response_model=Application,
             responses=E(400, 404, 409), summary="Шаг 4. Анкета вместо выписки", **OPTS)
def questionnaire(id: str, body: Questionnaire, db: Session = Depends(get_db)):
    return to_client(flow.save_questionnaire(db, get_application(db, id), body.model_dump(exclude_none=True)))


# ---------- шаги 5–6 ----------
@router.get("/applications/{id}/dialog", tags=["goals"], response_model=DialogState, responses=E(404),
            summary="История ИИ-диалога", **OPTS)
def get_dialog(id: str, db: Session = Depends(get_db)):
    return flow.get_dialog(get_application(db, id))


@router.post("/applications/{id}/dialog", tags=["goals"], response_model=DialogState, responses=E(404, 409, 503),
             summary="Шаги 5–6. Сообщение клиента в ИИ-диалог", **OPTS)
def send_dialog(id: str, body: DialogMessageRequest, db: Session = Depends(get_db)):
    return flow.send_dialog_message(db, get_application(db, id), body.text)


@router.post("/applications/{id}/handoff", tags=["goals"], response_model=Application, responses=E(404, 409),
             summary="Передать заявку сотруднику (цель не удалось определить)", **OPTS)
def handoff(id: str, body: HandoffRequest, db: Session = Depends(get_db)):
    return to_client(flow.handoff(db, get_application(db, id), body.reason, body.text))


@router.put("/applications/{id}/goals", tags=["goals"], response_model=Estimate, responses=E(400, 404, 409),
            summary="Шаги 5–6. Сохранить цели и ответы", **OPTS)
def save_goals(id: str, body: GoalsData, db: Session = Depends(get_db)):
    return flow.save_goals(db, get_application(db, id), body.model_dump())


@router.post("/okved/suggest", tags=["goals"], response_model=list[Okved], responses=E(503),
             summary="ИИ подсказывает ОКВЭД по описанию бизнеса")
def suggest_okved(body: OkvedSuggestRequest):
    return flow.suggest_okved(body.text)


# ---------- шаги 7–8 ----------
@router.get("/applications/{id}/estimate", tags=["application"], response_model=Estimate, responses=E(404),
            summary="Шаг 7. Смета", **OPTS)
def get_estimate(id: str, db: Session = Depends(get_db)):
    return flow.get_estimate(get_application(db, id))


@router.put("/applications/{id}/estimate", tags=["application"], response_model=Estimate,
            responses=E(400, 404, 409), summary="Шаг 7. Клиент правит смету", **OPTS)
def update_estimate(id: str, body: EstimateUpdateRequest, db: Session = Depends(get_db)):
    return flow.update_estimate(db, get_application(db, id), [i.model_dump() for i in body.items])


@router.post("/applications/{id}/submit", tags=["application"], response_model=Application,
             responses=E(404, 409), summary="Шаг 8. Отправить заявку на решение", **OPTS)
def submit(id: str, db: Session = Depends(get_db)):
    return to_client(flow.submit(db, get_application(db, id)))


@router.post("/applications/{id}/info-response", tags=["application"], response_model=Application,
             responses=E(400, 404, 409), summary="Ответ клиента на запрос данных", **OPTS)
async def info_response(id: str, text: str = Form(..., max_length=2000), file: Optional[UploadFile] = File(None),
                        db: Session = Depends(get_db)):
    raw = await file.read() if file is not None else None
    return to_client(flow.answer_info_request(db, get_application(db, id), text, raw or None))


# ---------- шаги 9–10 ----------
@router.get("/applications/{id}/offers", tags=["offer"], response_model=list[Offer], responses=E(404, 409),
            summary="Шаг 9. Предложения", **OPTS)
def get_offers(id: str, db: Session = Depends(get_db)):
    return flow.get_offers(get_application(db, id))


@router.post("/applications/{id}/offers/{offerId}/select", tags=["offer"], response_model=Application,
             responses=E(404, 409), summary="Клиент выбрал предложение", **OPTS)
def select_offer(id: str, offerId: str, db: Session = Depends(get_db)):
    return to_client(flow.select_offer(db, get_application(db, id), offerId))


@router.get("/applications/{id}/contract", tags=["offer"], response_model=Contract, responses=E(404, 409),
            summary="Шаг 10. Договор с пояснениями", **OPTS)
def get_contract(id: str, db: Session = Depends(get_db)):
    return flow.get_contract(get_application(db, id))


@router.post("/applications/{id}/contract/ask", tags=["offer"], response_model=ContractAnswer,
             responses=E(400, 404, 409, 503), summary="«Что будет, если…» — вопрос по договору", **OPTS)
def ask_contract(id: str, body: ContractAskRequest, db: Session = Depends(get_db)):
    return flow.ask_contract(get_application(db, id), body.questionId, body.text)


@router.post("/applications/{id}/sign/code", tags=["offer"], response_model=SignCode, responses=E(404, 409),
             summary="Получить код подписи (показывается на экране, без SMS)")
def sign_code(id: str, db: Session = Depends(get_db)):
    return flow.request_sign_code(db, get_application(db, id))


@router.post("/applications/{id}/sign", tags=["offer"], response_model=Application, responses=E(400, 404, 409),
             summary="Подписать договор кодом", **OPTS)
def sign(id: str, body: SignRequest, db: Session = Depends(get_db)):
    return to_client(flow.sign(db, get_application(db, id), body.code))


# ---------- после выдачи ----------
@router.get("/applications/{id}/schedule", tags=["after"], response_model=Schedule, responses=E(404, 409),
            summary="График платежей после выдачи", **OPTS)
def schedule(id: str, db: Session = Depends(get_db)):
    return flow.get_schedule(get_application(db, id))


@router.get("/applications/{id}/notifications", tags=["after"], response_model=list[Notification],
            responses=E(404), summary="Уведомления (раннее предупреждение, рост лимита)", **OPTS)
def notifications(id: str, db: Session = Depends(get_db)):
    return flow.get_notifications(get_application(db, id))


@router.post("/applications/{id}/notifications/{notificationId}/choose", tags=["after"], response_model=Schedule,
             responses=E(404, 409), summary="Клиент выбрал вариант в уведомлении", **OPTS)
def choose(id: str, notificationId: str, body: ChooseOptionRequest, db: Session = Depends(get_db)):
    return flow.choose_notification_option(db, get_application(db, id), notificationId, body.option)


@router.post("/demo/applications/{id}/advance-month", tags=["demo"], response_model=list[Notification],
             responses=E(404, 409), summary="«Перемотать месяц» после выдачи", **OPTS)
def advance_month(id: str, body: AdvanceMonthRequest, db: Session = Depends(get_db)):
    return flow.advance_month(db, get_application(db, id), body.scenario)
