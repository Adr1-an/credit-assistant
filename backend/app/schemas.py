"""Схемы запросов и ответов — копия components.schemas из contract/openapi.yaml.

Зачем это нужно:
1) FastAPI проверяет входящие данные по этим схемам (неверно — 400 VALIDATION_ERROR);
2) по ним строится Swagger на /docs — фронт видит то же, что в контракте;
3) ответ сервера пропускается через схему, поэтому лишнее поле (например, баллы
   в клиентском Application) просто не может «утечь» наружу.

Названия полей — camelCase, как в контракте. Необязательные поля = None и в ответ не попадают.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------- перечисления (enum) ----------
ApplicationStatus = Literal["DRAFT", "CHECKING", "COLLECTING", "MANUAL_REVIEW", "INFO_REQUESTED",
                            "OFFER_READY", "SIGNING", "ISSUED", "REJECTED"]
NextAction = Literal["GIVE_CONSENT", "WAIT", "RETRY_CHECKS", "UPLOAD_STATEMENT", "SET_GOALS",
                     "REVIEW_ESTIMATE", "SUBMIT", "ANSWER_INFO_REQUEST", "CHOOSE_OFFER", "SIGN", "NONE"]
Zone = Literal["GREEN", "YELLOW", "RED"]
GoalType = Literal["EQUIPMENT", "NEW_LOCATION", "INVENTORY", "CASH_GAP", "TENDER", "MARKETING",
                   "START_BUSINESS", "OTHER"]
ProductType = Literal["LEASING", "INVESTMENT_LOAN", "CREDIT_LINE", "OVERDRAFT", "BANK_GUARANTEE",
                      "PARTNER_SERVICE", "REVENUE_BASED_LOAN", "STARTER_LOAN"]
CostCategory = Literal["EQUIPMENT", "PREMISES", "INVENTORY", "STAFF", "MARKETING", "TENDER", "BUFFER"]
CheckSource = Literal["FNS_EGRIP", "FNS_TAX_DEBT", "BKI", "FSSP", "BANKRUPTCY", "PASSPORT"]
NotificationOption = Literal["POSTPONE_PAYMENT", "INTEREST_ONLY", "RESTRUCTURE", "OVERDRAFT",
                             "ACCEPT_LIMIT", "DECLINE"]

DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"


class Model(BaseModel):
    # extra="forbid" — неизвестное поле во входящем JSON — это ошибка, а не «тихо проигнорировать»
    model_config = ConfigDict(extra="forbid")


class OutModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _real_date(v: str) -> str:
    dt.date.fromisoformat(v)  # бросит ValueError для 2026-02-30
    return v


# ---------- шаг 1: паспорт и ИНН ----------
class Passport(Model):
    lastName: str = Field(min_length=1)
    firstName: str = Field(min_length=1)
    middleName: Optional[str] = None
    birthDate: str = Field(pattern=DATE_PATTERN)
    series: str = Field(pattern=r"^[0-9]{4}$")
    number: str = Field(pattern=r"^[0-9]{6}$")
    issueDate: str = Field(pattern=DATE_PATTERN)

    @field_validator("birthDate", "issueDate")
    @classmethod
    def _dates(cls, v: str) -> str:
        return _real_date(v)

    @field_validator("lastName", "firstName")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("не может быть пустым")
        return v


class CreateApplicationRequest(Model):
    passport: Passport
    hasBusiness: bool
    inn: Optional[str] = Field(default=None, pattern=r"^[0-9]{12}$")


class ConsentRequest(Model):
    agreed: Literal[True]


# ---------- ответы ----------
class Error(OutModel):
    code: str
    message: str
    details: dict = {}


class Okved(OutModel):
    code: str
    name: str


class CheckResult(OutModel):
    source: CheckSource
    state: Literal["OK", "WARNING", "FAIL", "ERROR"]
    basket: Literal["NONE", "STOP", "MINUS", "MANUAL"]
    code: Optional[str] = None
    clientText: Optional[str] = None


class BusinessInfo(OutModel):
    okved: Optional[Okved] = None
    registrationDate: Optional[str] = None
    ageMonths: Optional[int] = None
    region: Optional[str] = None


class InfoRequest(OutModel):
    text: Optional[str] = None
    requestedBy: Optional[Literal["SYSTEM", "STAFF"]] = None


class Rejection(OutModel):
    text: Optional[str] = None
    advice: Optional[list[str]] = Field(default=None, max_length=3)
    retryAfterMonths: Optional[int] = None


class Application(OutModel):
    """Заявка глазами клиента. Баллов здесь нет и быть не может."""
    id: str
    status: ApplicationStatus
    statusText: str
    nextAction: NextAction
    hasBusiness: bool
    applicantName: Optional[str] = None
    inn: Optional[str] = None
    business: Optional[BusinessInfo] = None
    checks: Optional[list[CheckResult]] = None
    hasStatement: Optional[bool] = None
    hasQuestionnaire: Optional[bool] = None
    goals: Optional[list[GoalType]] = None
    reviewDeadline: Optional[dt.datetime] = None
    infoRequest: Optional[InfoRequest] = None
    rejection: Optional[Rejection] = None
    createdAt: dt.datetime
    updatedAt: dt.datetime


class HealthResponse(OutModel):
    status: Literal["ok"]
    aiAvailable: bool


# ---------- вопросы (GET /question-sets) ----------
class Question(OutModel):
    id: str
    field: str
    text: str
    type: Literal["money", "number", "months", "boolean", "choice", "text", "okved"]
    options: Optional[list[str]] = None
    required: bool
    unknownAllowed: bool


class QuestionGroup(OutModel):
    title: str
    questions: list[Question]


class GoalQuestionSet(QuestionGroup):
    goalType: GoalType


class QuestionSets(OutModel):
    version: str
    note: Optional[str] = None
    common: QuestionGroup
    goals: list[GoalQuestionSet]


# ---------- демо ----------
class DemoClient(OutModel):
    passport: Passport
    inn: Optional[str] = None
    hasBusiness: bool
    businessName: Optional[str] = None
    scenario: str
    hasStatement: Optional[bool] = None
    suggestedClientText: Optional[str] = None


GoalValue = Union[bool, int, float, str, None]


# ---------- шаг 4: выписка и анкета ----------
class MonthlyRow(OutModel):
    month: str
    income: int
    expense: int


class TopCustomer(OutModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    sharePercent: Optional[float] = None


class StatementSummary(OutModel):
    periodFrom: str
    periodTo: str
    monthsCovered: int
    avgMonthlyIncome: int
    avgMonthlyExpense: int
    monthly: Optional[list[MonthlyRow]] = None
    expenseByCategory: Optional[dict[str, int]] = None
    topCustomers: Optional[list[TopCustomer]] = None
    otherBankLoanPaymentsMonthly: Optional[int] = None
    warnings: Optional[list[str]] = None


class Questionnaire(Model):
    monthlyRevenue: int = Field(ge=0)
    monthlyExpenses: int = Field(ge=0)
    hasOtherLoans: Optional[bool] = None
    otherLoansMonthlyPayment: Optional[int] = Field(default=None, ge=0)
    employees: Optional[int] = Field(default=None, ge=0)


# ---------- шаги 5–6: цели ----------
class GoalAnswer(Model):
    questionId: str
    value: GoalValue = None


class GoalItem(Model):
    goalType: GoalType
    answers: list[GoalAnswer]


class GoalsData(Model):
    source: Literal["FORM", "AI"]
    goals: list[GoalItem] = Field(max_length=3)
    commonAnswers: Optional[list[GoalAnswer]] = None
    clientText: Optional[str] = None


class DialogMessage(OutModel):
    role: Literal["CLIENT", "ASSISTANT"]
    text: str
    at: dt.datetime


class DialogState(OutModel):
    state: Literal["ASKING", "SUMMARY", "ESCALATED"]
    messages: list[DialogMessage]
    currentQuestionId: Optional[str] = None
    quickReplies: Optional[list[str]] = None
    collected: Optional[GoalsData] = None
    summaryText: Optional[str] = None


class DialogMessageRequest(Model):
    text: str = Field(max_length=2000)


class HandoffRequest(Model):
    reason: Literal["GOAL_UNCLEAR"]
    text: Optional[str] = Field(default=None, max_length=2000)


class OkvedSuggestRequest(Model):
    text: str = Field(max_length=500)


# ---------- шаг 7: смета ----------
class EstimateItem(OutModel):
    id: str
    category: CostCategory
    title: str
    amount: int
    source: Literal["CLIENT", "STATEMENT", "INDUSTRY", "RULE"]
    product: ProductType
    excluded: Optional[bool] = None
    note: Optional[str] = None


class Estimate(OutModel):
    items: list[EstimateItem]
    total: int
    startSmallerSuggested: Optional[bool] = None


class EstimateEdit(Model):
    id: str
    amount: Optional[int] = Field(default=None, ge=0)
    excluded: Optional[bool] = None


class EstimateUpdateRequest(Model):
    items: list[EstimateEdit]


# ---------- шаг 9: предложения ----------
class Partner(OutModel):
    name: Optional[str] = None
    discountPercent: Optional[float] = None


class OfferProduct(OutModel):
    product: ProductType
    title: Optional[str] = None
    amount: int
    termMonths: int
    ratePercent: float
    gracePeriodMonths: Optional[int] = None
    monthlyPayment: int
    fee: Optional[int] = None
    note: Optional[str] = None
    coversItems: Optional[list[str]] = None
    partner: Optional[Partner] = None


class Payback(OutModel):
    good: Optional[int] = None
    normal: Optional[int] = None
    bad: Optional[int] = None


class PartnerService(OutModel):
    title: str
    amount: int
    withDiscount: int
    discountPercent: float


class Offer(OutModel):
    id: str
    kind: Literal["MAIN", "SMALLER", "ALTERNATIVE"]
    termsChanged: Optional[bool] = None
    products: list[OfferProduct]
    totalAmount: int
    firstMonthsPayment: int
    fullPayment: int
    overpayment: int
    paybackMonths: Optional[Payback] = None
    whyItFits: list[str] = Field(max_length=3)
    partnerServices: Optional[list[PartnerService]] = None


# ---------- шаг 10: договор и подпись ----------
class ContractClause(OutModel):
    id: str
    title: str
    legalText: str
    plainText: str
    important: bool


class FaqItem(OutModel):
    id: str
    question: str


class Contract(OutModel):
    clauses: list[ContractClause]
    summary: list[str] = Field(min_length=3, max_length=3)
    faq: list[FaqItem]
    downloadUrl: Optional[str] = None


class ContractAskRequest(Model):
    questionId: Optional[str] = None
    text: Optional[str] = Field(default=None, max_length=500)


class ContractAnswer(OutModel):
    answer: str
    source: Literal["FAQ", "AI"]
    disclaimer: Optional[str] = None


class SignCode(OutModel):
    code: str
    expiresAt: dt.datetime


class SignRequest(Model):
    code: str = Field(pattern=r"^[0-9]{6}$")
    understood: Literal[True]


# ---------- после выдачи ----------
class SchedulePayment(OutModel):
    date: str
    total: int
    principal: int
    interest: int
    status: Literal["PAID", "UPCOMING", "POSTPONED"]


class Schedule(OutModel):
    payments: list[SchedulePayment]
    remainingDebt: int
    nextPayment: Optional[SchedulePayment] = None


class Notification(OutModel):
    id: str
    kind: Literal["EARLY_WARNING", "LIMIT_INCREASE", "INFO"]
    text: str
    options: Optional[list[NotificationOption]] = None
    chosen: Optional[NotificationOption] = None
    createdAt: dt.datetime


class ChooseOptionRequest(Model):
    option: NotificationOption


class AdvanceMonthRequest(Model):
    scenario: Literal["NORMAL", "REVENUE_DROP", "GROWTH"]


# ---------- кабинет сотрудника ----------
class ScoreFactor(OutModel):
    code: str
    block: Literal["BUSINESS", "OWNER", "IDEA", "INDUSTRY"]
    points: int
    maxPoints: int
    reason: str


class ScoreFlag(OutModel):
    code: str
    basket: Literal["STOP", "MINUS", "MANUAL"]
    text: str


class Score(OutModel):
    total: int = Field(ge=0, le=100)
    zone: Zone
    factors: list[ScoreFactor]
    flags: Optional[list[ScoreFlag]] = None


class StaffApplicationListItem(OutModel):
    id: str
    status: ApplicationStatus
    applicantName: str
    okvedName: Optional[str] = None
    requestedAmount: Optional[int] = None
    scoreTotal: Optional[int] = None
    zone: Optional[Zone] = None
    needsAttention: bool
    createdAt: dt.datetime


class HistoryEntry(OutModel):
    at: dt.datetime
    actor: Literal["CLIENT", "SYSTEM", "STAFF"]
    fromStatus: Optional[ApplicationStatus] = None
    toStatus: ApplicationStatus
    comment: Optional[str] = None


class BreakEvenComparison(OutModel):
    goalIndex: int
    goalType: GoalType
    questionId: Literal["start.breakEven", "location.breakEven"]
    okvedCode: str
    clientMonths: int
    industryMonths: int
    differenceMonths: int
    sourceType: Literal["SYNTHETIC", "OFFICIAL"]
    dataAsOf: Optional[str] = None
    text: str


class Handoff(OutModel):
    reason: Literal["GOAL_UNCLEAR"]
    text: Optional[str] = None
    at: dt.datetime


class Recommendation(OutModel):
    action: Optional[Literal["APPROVE", "CHANGE_TERMS", "REQUEST_INFO", "REJECT"]] = None
    text: Optional[str] = None


class StaffApplicationCard(OutModel):
    application: Application
    passport: Optional[Passport] = None
    statement: Optional[StatementSummary] = None
    questionnaire: Optional[Questionnaire] = None
    goals: Optional[GoalsData] = None
    estimate: Optional[Estimate] = None
    score: Optional[Score] = None
    breakEvenComparisons: Optional[list[BreakEvenComparison]] = None
    handoff: Optional[Handoff] = None
    dialog: Optional[DialogState] = None
    recommendation: Optional[Recommendation] = None
    offers: Optional[list[Offer]] = None
    aiSummary: Optional[str] = None
    history: list[HistoryEntry]


class NewTerms(Model):
    amount: Optional[int] = None
    termMonths: Optional[int] = None


class StaffDecision(Model):
    action: Literal["APPROVE", "CHANGE_TERMS", "REQUEST_INFO", "REJECT"]
    comment: str = Field(min_length=1)
    newTerms: Optional[NewTerms] = None
    infoRequestText: Optional[str] = None
    advice: Optional[list[str]] = Field(default=None, max_length=3)
