"""Генератор тестовых данных по утверждённой модели баллов БА (v1, 24.10.2026).

Запуск из корня репозитория: python tests/build_seed.py
Пересоздаёт tests/demo-clients.json, tests/cases.json, tests/statements/*.csv,
mocks/data/*.json и contract/okved.json. Ожидаемые результаты считает reference_scoring.py.
Все данные синтетические: ИНН, паспорта, ФИО и суммы вымышлены.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CONTRACT = ROOT / "contract"
MOCK_DATA = ROOT / "mocks" / "data"

# Окно выписки при дате оценки 2026-10-24: 12 завершённых месяцев
WINDOW = [f"2025-{m:02d}" for m in (10, 11, 12)] + [f"2026-{m:02d}" for m in range(1, 10)]


def inn_check(prefix10: str) -> str:
    d = [int(c) for c in prefix10]
    c1 = sum(a * b for a, b in zip(d, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])) % 11 % 10
    d.append(c1)
    c2 = sum(a * b for a, b in zip(d, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])) % 11 % 10
    return prefix10 + str(c1) + str(c2)


def inn_valid(inn: str) -> bool:
    return len(inn) == 12 and inn.isdigit() and inn_check(inn[:10]) == inn


OKVED = {
    "10.71": "Производство хлеба и мучных кондитерских изделий, тортов и пирожных недлительного хранения",
    "13.92": "Производство готовых текстильных изделий, кроме одежды",
    "14.13": "Производство прочей верхней одежды",
    "43.39": "Производство прочих отделочных и завершающих работ",
    "45.20": "Техническое обслуживание и ремонт автотранспортных средств",
    "45.32": "Торговля розничная автомобильными деталями, узлами и принадлежностями",
    "47.11": "Торговля розничная преимущественно пищевыми продуктами, включая напитки, и табачными изделиями в неспециализированных магазинах",
    "47.76": "Торговля розничная цветами и другими растениями, семенами и удобрениями в специализированных магазинах",
    "47.91": "Торговля розничная по почте или по информационно-коммуникационной сети Интернет",
    "49.41": "Деятельность автомобильного грузового транспорта",
    "56.10": "Деятельность ресторанов и услуги по доставке продуктов питания",
    "56.30": "Подача напитков",
    "62.01": "Разработка компьютерного программного обеспечения",
    "73.11": "Деятельность рекламных агентств",
    "85.41": "Образование дополнительное детей и взрослых",
    "93.13": "Деятельность фитнес-центров",
    "95.23": "Ремонт обуви и прочих изделий из кожи",
    "96.02": "Предоставление услуг парикмахерскими и салонами красоты",
}

# ---------------------------------------------------------------------------
# Клиенты. Поля, которых нет, берутся из DEFAULTS (раздел 9 модели БА).
# ---------------------------------------------------------------------------

def loan(type_, status, opened, amount, balance, payment, cur=0, overdues=()):
    return {"type": type_, "openedAt": opened, "amount": amount, "balance": balance,
            "monthlyPayment": payment, "status": status, "currentOverdueDays": cur,
            "overdues": [dict(date=d, days=n, amount=a) for d, n, a in overdues]}


T01_LOAN = loan("BUSINESS_LOAN", "ACTIVE", "2023-01-01", 1200000, 500000, 25000)
T01_STATEMENT = {"months": {m: (1200000, 900000) for m in WINDOW}, "loanPayment": 25000}

CLIENTS = [
    dict(code="T01", demo=True, fio=("Кузнецова", "Елена", "Андреевна"), inn="990001000164",
         passport=("9940", "000101"), birth="1988-05-20", issue="2018-06-14",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Санкт-Петербург",
         businessName="ИП Кузнецова — швейный цех",
         scenario="Зелёная зона: 94 балла, автоматическое одобрение",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1), statement=T01_STATEMENT,
         goals=[("NEW_LOCATION", [("location.premises", "RENT_FOUND"), ("location.renovation", 400000),
                                  ("location.equipment", 1500000), ("location.staff", 6),
                                  ("location.sameAsFirst", True), ("location.breakEven", 14)]),
                ("MARKETING", [("marketing.what", "Реклама в соцсетях и на картах"), ("marketing.budget", 50000),
                               ("marketing.months", 3)])], amount=None,
         text="Хочу открыть второй швейный цех такой же, как первый: помещение нашла, нужен ремонт, оборудование и реклама"),
    dict(code="T02", demo=True, fio=("Смирнов", "Алексей", "Викторович"), inn="990001000238",
         passport=("9940", "000102"), birth="1989-02-15", issue="2019-04-10",
         hasBusiness=True, reg="2023-10-01", okved="45.20", region="Казань",
         businessName="ИП Смирнов — автосервис",
         scenario="Жёлтая зона: 64 балла, просрочка 60 дней в 2024 году — решает сотрудник",
         bki=dict(loans=[loan("CONSUMER_LOAN", "ACTIVE", "2023-02-01", 800000, 300000, 20000,
                              overdues=[("2024-10-15", 60, 50000)])], requestsLast30Days=1),
         statement={"months": {m: (950000, 760000) for m in WINDOW}, "loanPayment": 20000},
         goal=("EQUIPMENT", [("equipment.what", "Подъёмник и стенд развала-схождения"), ("equipment.price", 800000),
                             ("equipment.purpose", "EXPANSION")]), amount=800000,
         text="Нужен второй подъёмник и стенд развала-схождения, примерно 800 тысяч"),
    dict(code="T03", demo=True, fio=("Белова", "Надежда", "Игоревна"), inn="990001000301",
         passport=("9940", "000103"), birth="1986-03-11", issue="2016-04-15",
         hasBusiness=True, reg="2022-10-01", okved="47.76", region="Краснодар",
         businessName="ИП Белова — цветочный магазин",
         scenario="Красная зона: 32 балла, выручка резко упала — автоматический отказ с советами",
         bki=dict(loans=[loan("BUSINESS_LOAN", "ACTIVE", "2024-03-01", 300000, 150000, 10000)], requestsLast30Days=0),
         statement={"months": {**{m: (200000, 150000) for m in WINDOW[:6]},
                               **{m: (20000, 150000) for m in WINDOW[6:9]},
                               **{m: (5000, 150000) for m in WINDOW[9:]}}, "loanPayment": 10000},
         goal=("CASH_GAP", [("cashgap.amount", 300000)]), amount=300000,
         text="Не хватает денег на аренду и закупку, нужно 300 тысяч"),
    dict(code="T04", demo=True, fio=("Ковалёв", "Михаил", "Олегович"), inn="990001000485",
         passport=("9940", "000104"), birth="1984-06-01", issue="2014-07-21",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Москва",
         businessName="ИП Ковалёв — пошив штор",
         scenario="Стоп-фактор: идёт процедура банкротства — отказ сразу после проверок",
         bki=dict(loans=[loan("CONSUMER_LOAN", "CLOSED", "2021-05-01", 200000, 0, 0)], requestsLast30Days=0),
         bankruptcy=dict(inProcedure=True, stage="REALIZATION", startedAt="2026-01-10", completedAt=None),
         statement=None, goal=("EQUIPMENT", [("equipment.what", "Раскройный стол"), ("equipment.price", 400000),
                                             ("equipment.purpose", "REPLACEMENT")]), amount=400000,
         text="Нужен новый раскройный стол"),
    dict(code="T05", demo=True, fio=("Романов", "Иван", "Сергеевич"), inn="990001000559",
         passport=("9940", "000105"), birth="1993-09-14", issue="2020-10-02",
         hasBusiness=False, plannedOkved="10.71", region="Новосибирск",
         businessName="Иван Романов — хочет открыть пекарню",
         scenario="Стартап, автоодобрение: 51 балл, хорошая кредитная история, сумма до 200 000 ₽",
         bki=dict(loans=[loan("CONSUMER_LOAN", "CLOSED", "2024-01-01", 120000, 0, 0)], requestsLast30Days=0),
         statement=None,
         goal=("START_BUSINESS", [("start.okved", "10.71"), ("start.ownFunds", 100000), ("start.experience", 4),
                                  ("start.needs", "Печь, тестомес, витрина"), ("start.breakEven", 12)]),
         amount=150000, text="Хочу открыть мини-пекарню, нужно 150 тысяч на печь и тестомес"),
    dict(code="T06", demo=True, fio=("Орлова", "Мария", "Дмитриевна"), inn="990001000622",
         passport=("9940", "000106"), birth="1995-12-17", issue="2021-02-15",
         hasBusiness=False, plannedOkved="10.71", region="Екатеринбург",
         businessName="Мария Орлова — хочет открыть пекарню",
         scenario="Стартап к сотруднику: 43 балла, нет кредитной истории, сумма 700 000 ₽",
         bki=dict(loans=[], requestsLast30Days=0), statement=None,
         goal=("START_BUSINESS", [("start.okved", "10.71"), ("start.ownFunds", 300000), ("start.experience", 3),
                                  ("start.needs", "Помещение, печь, витрины"), ("start.breakEven", 11)]),
         amount=700000, text="Хочу открыть пекарню, нужно 700 тысяч, своих вложу 300"),
    dict(code="T07", demo=True, fio=("Соловьёв", "Пётр", "Николаевич"), inn="990001000703",
         passport=("9940", "000107"), birth="1982-10-09", issue="2013-03-12",
         hasBusiness=True, reg="2021-10-01", okved="45.20", region="Самара",
         businessName="ИП Соловьёв — ремонт автомобилей",
         scenario="Без выписки, только анкета: 36 баллов, всегда к сотруднику (не автоотказ)",
         bki=dict(loans=[loan("BUSINESS_LOAN", "ACTIVE", "2024-05-01", 500000, 250000, 15000)], requestsLast30Days=0),
         statement=None,
         questionnaire=dict(monthlyRevenue=600000, monthlyExpenses=450000, hasOtherLoans=True,
                            otherLoansMonthlyPayment=15000, employees=3),
         goal=("INVENTORY", [("inventory.items", "Запчасти и расходники"), ("inventory.amount", 500000)]),
         amount=500000, text="Хочу закупить запчасти на 500 тысяч"),
    dict(code="T08", demo=True, fio=("Сидоров", "Артём", "Павлович"), inn="990001000870",
         passport=("9940", "000108"), birth="1987-05-05", issue="2018-06-14", enteredIssue="2017-06-14",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Тверь",
         businessName="ИП Сидоров — текстильная мастерская",
         scenario="Паспорт не совпал (дата выдачи): 94 балла, но к сотруднику",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1), statement=T01_STATEMENT,
         goal=("EQUIPMENT", [("equipment.what", "Вышивальная машина"), ("equipment.price", 1000000),
                             ("equipment.purpose", "EXPANSION")]), amount=1000000,
         text="Хочу купить вышивальную машину за 1 млн"),
    dict(code="T09", demo=True, fio=("Васильева", "Ольга", "Петровна"), inn="990001000943",
         passport=("9940", "000109"), birth="1984-08-29", issue="2016-07-24",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Ярославль",
         businessName="ИП Васильева — пошив постельного белья",
         scenario="Банкротство завершено менее 5 лет назад: 94 балла, но к сотруднику",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1), statement=T01_STATEMENT,
         bankruptcy=dict(inProcedure=False, stage="COMPLETED", startedAt="2019-02-01", completedAt="2024-01-15"),
         goal=("EQUIPMENT", [("equipment.what", "Оверлоки"), ("equipment.price", 1000000),
                             ("equipment.purpose", "EXPANSION")]), amount=1000000,
         text="Нужны новые оверлоки на 1 млн"),
    dict(code="T10", demo=True, fio=("Фёдорова", "Дарья", "Александровна"), inn="990001001048",
         passport=("9940", "000110"), birth="1985-10-21", issue="2017-11-23",
         hasBusiness=True, reg="2022-10-01", okved="10.71", region="Пермь",
         businessName="ИП Фёдорова — кондитерская",
         scenario="Бюро кредитных историй недоступно (503): заявка ждёт повтора проверок",
         bki=dict(loans=[], requestsLast30Days=0), statement=None, failures=["BKI"],
         goal=("EQUIPMENT", [("equipment.what", "Холодильная витрина"), ("equipment.price", 300000),
                             ("equipment.purpose", "EXPANSION")]), amount=300000,
         text="Нужна холодильная витрина"),
    # ---- краевые случаи (раздел 10 модели) — не показываются жюри в списке ----
    dict(code="E01", demo=False, fio=("Гусев", "Роман", "Ильич"), inn=None,
         passport=("9940", "000111"), birth="1990-04-12", issue="2015-05-20",
         hasBusiness=True, reg="2026-08-01", okved="45.20", region="Тула",
         businessName="ИП Гусев — шиномонтаж", scenario="ИП 2 месяца, выписка 2 месяца: 42 / YELLOW",
         bki=dict(loans=[], requestsLast30Days=0),
         statement={"months": {"2026-08": (300000, 250000), "2026-09": (300000, 250000)}, "loanPayment": 0},
         goal=("EQUIPMENT", [("equipment.what", "Шиномонтажный станок"), ("equipment.price", 250000),
                             ("equipment.purpose", "EXPANSION")]), amount=250000, text="Нужен станок"),
    dict(code="E02", demo=False, fio=("Лебедева", "Анна", "Сергеевна"), inn=None,
         passport=("9940", "000112"), birth="1991-07-07", issue="2016-08-01",
         hasBusiness=True, reg="2026-02-01", okved="47.76", region="Сочи",
         businessName="ИП Лебедева — цветочная лавка", scenario="ИП 8 месяцев, выписка 8 месяцев: 57 / YELLOW",
         bki=dict(loans=[], requestsLast30Days=0),
         statement={"months": {m: (v * 1000, 315000) for m, v in zip(
             [f"2026-{i:02d}" for i in range(2, 10)], [320, 330, 340, 350, 350, 360, 370, 380])}, "loanPayment": 0},
         goal=("INVENTORY", [("inventory.items", "Цветы к праздникам"), ("inventory.amount", 200000)]),
         amount=200000, text="Закупка цветов к праздникам"),
    dict(code="E03", demo=False, fio=("Морозов", "Денис", "Андреевич"), inn=None,
         passport=("9940", "000113"), birth="1988-01-30", issue="2013-02-15",
         hasBusiness=True, reg="2026-04-01", okved="45.20", region="Воронеж",
         businessName="ИП Морозов — автомойка", scenario="ИП 6 месяцев, выписка 4 месяца: 32 / YELLOW (не RED)",
         bki=dict(loans=[loan("CAR_LOAN", "ACTIVE", "2024-06-01", 900000, 600000, 10000)], requestsLast30Days=0),
         statement={"months": {m: (400000, 300000) for m in ["2026-06", "2026-07", "2026-08", "2026-09"]},
                    "loanPayment": 10000},
         goal=("EQUIPMENT", [("equipment.what", "Аппарат высокого давления"), ("equipment.price", 150000),
                             ("equipment.purpose", "EXPANSION")]), amount=150000, text="Нужен аппарат"),
    dict(code="E04", demo=False, fio=("Никитина", "Ирина", "Олеговна"), inn=None,
         passport=("9940", "000114"), birth="1987-11-11", issue="2017-12-01",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Иваново",
         businessName="ИП Никитина — швейный цех", scenario="Как T01, но нет операций за февраль 2026: 94 / YELLOW",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1),
         statement={"months": {m: (1200000, 900000) for m in WINDOW if m != "2026-02"}, "loanPayment": 25000},
         goal=("EQUIPMENT", [("equipment.what", "Швейные машины"), ("equipment.price", 1000000),
                             ("equipment.purpose", "EXPANSION")]), amount=1000000, text="Швейные машины"),
    dict(code="E05", demo=False, fio=("Захаров", "Олег", "Иванович"), inn=None,
         passport=("9940", "000115"), birth="1980-03-03", issue="2015-04-04",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Владимир",
         businessName="ИП Захаров — пошив спецодежды", scenario="Банкротство завершено ровно 5 лет назад (2021-10-24): 94 / GREEN",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1), statement=T01_STATEMENT,
         bankruptcy=dict(inProcedure=False, stage="COMPLETED", startedAt="2020-01-15", completedAt="2021-10-24"),
         goal=("EQUIPMENT", [("equipment.what", "Швейные машины"), ("equipment.price", 1000000),
                             ("equipment.purpose", "EXPANSION")]), amount=1000000, text="Швейные машины"),
    dict(code="E06", demo=False, fio=("Павлова", "Светлана", "Юрьевна"), inn=None,
         passport=("9940", "000116"), birth="1983-09-09", issue="2014-10-10",
         hasBusiness=True, reg="2022-10-01", okved="13.92", region="Рязань",
         businessName="ИП Павлова — пошив штор", scenario="Банкротство завершено 2021-10-25, пять лет ещё не прошло: 94 / YELLOW",
         bki=dict(loans=[T01_LOAN], requestsLast30Days=1), statement=T01_STATEMENT,
         bankruptcy=dict(inProcedure=False, stage="COMPLETED", startedAt="2020-01-15", completedAt="2021-10-25"),
         goal=("EQUIPMENT", [("equipment.what", "Швейные машины"), ("equipment.price", 1000000),
                             ("equipment.purpose", "EXPANSION")]), amount=1000000, text="Швейные машины"),
]

# Личные ИНН для краевых случаев: 990001001xxx с правильными контрольными цифрами
_n = 105
for c in CLIENTS:
    if c["inn"] is None:
        c["inn"] = inn_check(f"990001{_n:04d}")
        _n += 7


# ---------------------------------------------------------------------------
# Выписки CSV
# ---------------------------------------------------------------------------
CUSTOMERS = [("ООО Текстильторг", "7701234567"), ("ООО Домашний уют", "7802345678"), ("ООО Сервис-Плюс", "5403456789")]
ACQ_SHARE = 4  # каждое 4-е поступление — эквайринг (≈25%)


def statement_rows(st: dict) -> list[dict]:
    rows = []
    for month, (income, expense) in sorted(st["months"].items()):
        y, m = month.split("-")
        # Поступления: 75% от покупателей тремя платежами, 25% эквайринг
        acq = income // ACQ_SHARE
        cust = income - acq
        parts = [cust // 3, cust // 3, cust - 2 * (cust // 3)]
        for i, (amt, day) in enumerate(zip(parts, (5, 15, 25))):
            name, cinn = CUSTOMERS[i]
            if amt > 0:
                rows.append(dict(date=f"{y}-{m}-{day:02d}", amount=amt, direction="IN", counterparty=name,
                                 counterpartyInn=cinn, purpose=f"Оплата по договору поставки №{i + 11}"))
        if acq > 0:
            rows.append(dict(date=f"{y}-{m}-28", amount=acq, direction="IN", counterparty="АО Банк-эквайер",
                             counterpartyInn="7700000001", purpose="Эквайринг. Реестр операций по картам"))
        # Списания: сумма ровно expense
        lp = st["loanPayment"]
        rest = expense - lp
        assert rest >= 0
        rent, salary, taxes = rest * 15 // 100, rest * 40 // 100, rest * 10 // 100
        materials = rest - rent - salary - taxes
        out = [(3, rent, "ИП Арендодатель", "780212345678", "Аренда помещения"),
               (10, salary, "Зарплатный проект", "", "Выплата заработной платы"),
               (12, materials, "ООО Поставщик материалов", "7712345670", "Оплата материалов по счёту"),
               (20, taxes, "УФК по г. Москве (ФНС России)", "7727406020", "Уплата налогов и страховых взносов"),
               (22, lp, "Банк-кредитор", "7700000002", "Платёж по кредитному договору")]
        for day, amt, name, cinn, purpose in out:
            if amt > 0:
                rows.append(dict(date=f"{y}-{m}-{day:02d}", amount=amt, direction="OUT", counterparty=name,
                                 counterpartyInn=cinn, purpose=f"{purpose} за {m}.{y}"))
    rows.sort(key=lambda r: (r["date"], r["direction"]))
    return rows


COLUMNS = ["date", "amount", "direction", "counterparty", "counterpartyInn", "purpose"]


def write_csv(path: Path, rows: list[dict]):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, delimiter=";", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def passport_obj(c, entered=True):
    last, first, middle = c["fio"]
    return {"series": c["passport"][0], "number": c["passport"][1], "lastName": last, "firstName": first,
            "middleName": middle, "birthDate": c["birth"],
            "issueDate": c.get("enteredIssue", c["issue"]) if entered else c["issue"]}


def goals_data(c):
    goals = c.get("goals") or [c["goal"]]
    return {"source": "FORM",
            "goals": [{"goalType": g, "answers": [{"questionId": q, "value": v} for q, v in ans]} for g, ans in goals],
            "commonAnswers": [{"questionId": "common.amount", "value": c["amount"]}],
            "clientText": c["text"]}


def build():
    for c in CLIENTS:
        assert inn_valid(c["inn"]), c["code"]
    assert len({c["inn"] for c in CLIENTS}) == len(CLIENTS)
    assert len({c["passport"] for c in CLIENTS}) == len(CLIENTS)

    MOCK_DATA.mkdir(parents=True, exist_ok=True)
    st_dir = TESTS / "statements"
    if st_dir.exists():
        shutil.rmtree(st_dir)
    (st_dir / "bad").mkdir(parents=True)

    egrip, tax, bki, fssp, bankr, passports, fail = {}, {}, {}, [], {}, {}, {"byInn": {}, "byPassport": {}}
    demo, cases = [], []
    for c in CLIENTS:
        last, first, middle = c["fio"]
        inn = c["inn"]
        if c["hasBusiness"]:
            egrip[inn] = {"inn": inn, "fullName": f"{last} {first} {middle}", "status": "ACTIVE",
                          "registrationDate": c["reg"], "terminationDate": None,
                          "okvedMain": {"code": c["okved"], "name": OKVED[c["okved"]]}, "okvedExtra": [],
                          "region": c["region"]}
        else:
            egrip[inn] = {"_notIp": True, "_comment": "Личный ИНН, ИП не зарегистрирован → 404 NOT_IP"}
        tax[inn] = {"inn": inn, "hasDebt": False, "debtAmount": 0, "asOf": "2026-10-01"}
        bki[inn] = {"reportAsOf": "2026-10-24", **c["bki"]}
        fssp.append({"inn": inn, "lastName": last, "firstName": first, "middleName": middle,
                     "birthDate": c["birth"], "proceedings": []})
        bankr[inn] = {"inn": inn, **c.get("bankruptcy", dict(inProcedure=False, stage=None, startedAt=None,
                                                             completedAt=None))}
        p = passport_obj(c, entered=False)
        passports[f"{p['series']} {p['number']}"] = {"valid": True, "reason": None, "lastName": last,
                                                     "firstName": first, "middleName": middle,
                                                     "birthDate": c["birth"], "issueDate": c["issue"]}
        if c.get("failures"):
            fail["byInn"][inn] = c["failures"]
        if c["statement"]:
            write_csv(st_dir / f"{inn}.csv", statement_rows(c["statement"]))
        if c["demo"]:
            demo.append({"code": c["code"], "passport": passport_obj(c), "inn": inn,
                         "hasBusiness": c["hasBusiness"], "businessName": c["businessName"],
                         "scenario": c["scenario"], "hasStatement": bool(c["statement"]),
                         "suggestedClientText": c["text"]})
        cases.append({"code": c["code"], "demo": c["demo"], "scenario": c["scenario"], "inn": inn,
                      "hasBusiness": c["hasBusiness"], "passport": passport_obj(c),
                      "statementFile": f"statements/{inn}.csv" if c["statement"] else None,
                      "questionnaire": c.get("questionnaire"), "goalsData": goals_data(c),
                      "plannedOkved": c.get("plannedOkved")})

    # Плохие файлы выписки для краевых случаев
    (st_dir / "bad" / "empty.csv").write_text("", encoding="utf-8")
    (st_dir / "bad" / "not-csv.csv").write_text("Это не выписка, а просто текст.\nВторая строка.\n", encoding="utf-8")
    (st_dir / "bad" / "wrong-columns.csv").write_text(
        "Дата;Сумма;Описание\n2026-03-01;120000;Оплата по договору\n", encoding="utf-8")
    write_csv(st_dir / "bad" / "short-2-months.csv",
              statement_rows({"months": {"2026-08": (300000, 250000), "2026-09": (300000, 250000)}, "loanPayment": 0}))
    write_csv(st_dir / "bad" / "bad-amount.csv",
              [dict(date="2026-03-01", amount="120000,50", direction="IN", counterparty="ООО Текстильторг",
                    counterpartyInn="7701234567", purpose="Оплата по договору поставки")])

    # Паспортные приёмочные тесты P01–P14 (docs/passport-test-cases.md), серия 9941
    ivanova = {"lastName": "Иванова", "firstName": "Мария", "middleName": "Сергеевна",
               "birthDate": "1988-05-20", "issueDate": "2018-06-14"}
    passports.update({
        "9941 000001": {"valid": True, "reason": None, **ivanova},
        "9941 000005": {"valid": False, "reason": "LOST", **ivanova},
        "9941 000006": {"valid": True, "reason": None, "lastName": "Иванова", "firstName": "Мария",
                        "middleName": "Сергеевна", "issueDate": "2018-06-14"},
        "9941 000008": {"valid": True, "reason": None, **ivanova},
        "9941 000010": {"valid": True, "reason": None, **ivanova, "lastName": "Елкина"},
        "9941 000011": {"valid": True, "reason": None, **ivanova, "lastName": "Петрова", "middleName": None},
        "9941 000013": {"_rawResponse": {"valid": True, "reason": "LOST", "holderMatch": True, "mismatchFields": []}},
        "9941 000014": {"_rawResponse": {"valid": False, "reason": None, "holderMatch": None, "mismatchFields": []}},
    })
    fail["byPassport"]["9941 000008"] = ["PASSPORT"]

    def q(number, **chg):
        body = {"series": "9941", "number": number, **ivanova}
        body.update(chg)
        return {k: v for k, v in body.items() if v is not ...}

    ok = lambda m=(): {"status": 200, "response": {"valid": True, "reason": None, "holderMatch": not m, "mismatchFields": list(m)}}
    ptests = [
        ("P01", "Полное совпадение", q("000001"), ok(), "PASSPORT_VALID / NONE"),
        ("P02", "Другая фамилия", q("000001", lastName="Иванов"), ok(["LAST_NAME"]), "PASSPORT_HOLDER_MISMATCH / MANUAL"),
        ("P03", "Другая дата рождения", q("000001", birthDate="1988-05-21"), ok(["BIRTH_DATE"]), "PASSPORT_HOLDER_MISMATCH / MANUAL"),
        ("P04", "Другая дата выдачи", q("000001", issueDate="2018-06-15"), ok(["ISSUE_DATE"]), "PASSPORT_HOLDER_MISMATCH / MANUAL"),
        ("P05", "Паспорт утерян", q("000005"), {"status": 200, "response": {"valid": False, "reason": "LOST", "holderMatch": None, "mismatchFields": []}}, "PASSPORT_INVALID / STOP"),
        ("P06", "В эталоне нет даты рождения", q("000006"), {"status": 200, "response": {"valid": True, "reason": None, "holderMatch": None, "mismatchFields": []}}, "PASSPORT_HOLDER_UNKNOWN / MANUAL"),
        ("P07", "Паспорта нет в эталоне", q("000007"), {"status": 404, "response": {"code": "NOT_FOUND"}}, "PASSPORT_HOLDER_UNKNOWN / MANUAL"),
        ("P08", "Сервис недоступен", q("000008"), {"status": 503, "response": {"code": "SERVICE_UNAVAILABLE"}}, "state=ERROR, CHECKING, RETRY_CHECKS"),
        ("P09", "Фамилия заглавными", q("000001", lastName="ИВАНОВА"), ok(), "PASSPORT_VALID / NONE"),
        ("P10", "Ё вместо Е", q("000010", lastName="Ёлкина"), ok(), "PASSPORT_VALID / NONE"),
        ("P11", "Отчества нет у обоих", q("000011", lastName="Петрова", middleName=...), ok(), "PASSPORT_VALID / NONE"),
        ("P12", "Отчества нет только в запросе", q("000001", middleName=...), ok(["MIDDLE_NAME"]), "PASSPORT_HOLDER_MISMATCH / MANUAL"),
        ("P13", "Противоречие: valid=true и reason=LOST", q("000013"), {"status": 200, "response": {"valid": True, "reason": "LOST", "holderMatch": True, "mismatchFields": []}}, "PASSPORT_CHECK_CONFLICT / MANUAL"),
        ("P14", "Противоречие: valid=false и reason=null", q("000014"), {"status": 200, "response": {"valid": False, "reason": None, "holderMatch": None, "mismatchFields": []}}, "PASSPORT_CHECK_CONFLICT / MANUAL"),
        ("P15", "Несколько различий — порядок полей", q("000001", lastName="Иванов", issueDate="2018-06-15", firstName="Мариа"), ok(["LAST_NAME", "FIRST_NAME", "ISSUE_DATE"]), "PASSPORT_HOLDER_MISMATCH / MANUAL"),
        ("P16", "Неверный формат номера", q("12345"), {"status": 400, "response": {"code": "VALIDATION_ERROR"}}, "Ошибка ввода, не STOP"),
    ]
    passport_tests = [{"id": i, "title": t, "request": r, "expected": e, "serverResult": s} for i, t, r, e, s in ptests]

    def dump(name, obj):
        (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    note = "Синтетические данные для прототипа. ИНН, паспорта и ФИО вымышлены и не принадлежат реальным людям."
    dump("mocks/data/egrip.json", egrip)
    dump("mocks/data/tax-debt.json", tax)
    dump("mocks/data/bki.json", bki)
    dump("mocks/data/fssp.json", fssp)
    dump("mocks/data/bankruptcy.json", bankr)
    dump("mocks/data/passports.json", passports)
    dump("mocks/data/failures.json", fail)
    dump("tests/demo-clients.json", demo)
    dump("tests/passport-tests.json", {"note": "Приёмочные тесты паспортной заглушки (вариант Б). Серия 9941 — только для тестов.",
                                 "tests": passport_tests})
    dump("contract/okved.json", [{"code": k, "name": v} for k, v in sorted(OKVED.items())])
    dump("tests/cases.json", {"version": "1.0", "note": note, "evaluationDate": "2026-10-24", "cases": cases})
    print(f"тестовые данные: {len(CLIENTS)} клиентов ({len(demo)} для демо), выписок: {sum(1 for c in CLIENTS if c['statement'])}")


if __name__ == "__main__":
    sys.exit(build())
