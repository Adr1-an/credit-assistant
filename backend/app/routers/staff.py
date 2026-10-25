"""Кабинет сотрудника: /api/staff/... Здесь (и только здесь) видны баллы."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ApplicationStatus, Error, StaffApplicationCard, StaffApplicationListItem, StaffDecision, Zone
from ..services import staff
from ..services.applications import get_application

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/applications", response_model=list[StaffApplicationListItem], response_model_exclude_none=True,
            summary="Список всех заявок (спорные сверху)")
def list_applications(status: Optional[ApplicationStatus] = None, zone: Optional[Zone] = None,
                      db: Session = Depends(get_db)):
    return staff.list_items(db, status, zone)


@router.get("/applications/{id}", response_model=StaffApplicationCard, response_model_exclude_unset=True,
            responses={404: {"model": Error}}, summary="Карточка заявки для сотрудника")
def get_card(id: str, db: Session = Depends(get_db)):
    return staff.card(get_application(db, id))


@router.post("/applications/{id}/decision", response_model=StaffApplicationCard, response_model_exclude_unset=True,
             responses={c: {"model": Error} for c in (400, 404, 409)}, summary="Решение сотрудника")
def decide(id: str, body: StaffDecision, db: Session = Depends(get_db)):
    app = staff.decide(db, get_application(db, id), body.model_dump(exclude_none=True))
    return staff.card(app)
