"""Независимая проверка tests/expected-results.json другим способом (не использует reference_*.py).

Запуск из корня репозитория: python tests/check_expected.py. Пусто = расхождений нет."""
import csv, json, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

R = Path(__file__).resolve().parents[1]
L = lambda p: json.loads((R / p).read_text(encoding="utf-8"))
def run():
    exp = {r["code"]: r for r in L("tests/expected-results.json")["results"]}
    cases = {c["code"]: c for c in L("tests/cases.json")["cases"]}
    egrip, bki, bankr, pas = L("mocks/data/egrip.json"), L("mocks/data/bki.json"), L("mocks/data/bankruptcy.json"), L("mocks/data/passports.json")
    issues = []
    bad = lambda *a: issues.append(" | ".join(str(x) for x in a))

    WINDOW = [f"2025-{m:02d}" for m in (10, 11, 12)] + [f"2026-{m:02d}" for m in range(1, 10)]

    # 1. Поля по статусу
    for code, e in exp.items():
        st = e["statusAfterSubmit"]
        errors = [c for c in e["checks"] if c["state"] == "ERROR"]
        stops = [c for c in e["checks"] if c["basket"] == "STOP"]
        if len(e["checks"]) != 6 or {c["source"] for c in e["checks"]} != {"PASSPORT", "FNS_EGRIP", "FNS_TAX_DEBT", "BKI", "FSSP", "BANKRUPTCY"}:
            bad(code, "не 6 разных проверок")
        if errors and (e["score"] or e["statusAfterConsent"] != "CHECKING"): bad(code, "ошибка сервиса, но есть баллы/не CHECKING")
        if stops and (e["score"] or e["statusAfterConsent"] != "REJECTED"): bad(code, "стоп, но есть баллы/не REJECTED")
        if not errors and not stops:
            if not e["score"]: bad(code, "нет баллов")
            if "estimate" not in e: bad(code, "нет сметы")
            if st in ("OFFER_READY", "MANUAL_REVIEW") and not e.get("offers"): bad(code, "нет предложений")
            if st in ("OFFER_READY", "MANUAL_REVIEW") and not e.get("recommendation"): bad(code, "нет рекомендации")
            if st == "REJECTED" and e.get("offers"): bad(code, "отказ с предложениями")
        if e["score"]:
            s = e["score"]
            if sum(f["points"] for f in s["factors"]) != s["total"]: bad(code, "сумма факторов != total")
            if sum(f["maxPoints"] for f in s["factors"]) != 100: bad(code, "maxPoints != 100")
            if any(not 0 <= f["points"] <= f["maxPoints"] for f in s["factors"]): bad(code, "баллы вне диапазона")
            for b in s["blocks"]:
                if s["blocks"][b] != sum(f["points"] for f in s["factors"] if f["block"] == b): bad(code, "блок", b)
            zone_status = {"GREEN": "OFFER_READY", "YELLOW": "MANUAL_REVIEW", "RED": "REJECTED"}[s["zone"]]
            if zone_status != st: bad(code, "зона и статус не согласованы")
            if s["zone"] == "RED" and (e["manualReasons"] or s["total"] >= 40): bad(code, "RED при ручной/≥40")
            if s["zone"] == "GREEN" and cases[code]["hasBusiness"] and (e["manualReasons"] or s["total"] < 80): bad(code, "GREEN нарушает правило")

    # 2. Выписки: суммы по месяцам из CSV против замысла (независимый разбор)
    for code, c in cases.items():
        if not c["statementFile"]:
            continue
        months = {}
        with open(R / "tests" / c["statementFile"], encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                m = row["date"][:7]
                d = months.setdefault(m, [0, 0])
                d[0 if row["direction"] == "IN" else 1] += int(row["amount"])
        for m in months:
            if m not in WINDOW: bad(code, "строка вне окна", m)
        # все поступления в демо — выручка: OTHER_IN должен быть 0
        e = exp[code]
        s = e["score"]
        if not s:
            continue
        n = len(months)
        Rv = Decimal(sum(v[0] for v in months.values())) / n
        Ev = Decimal(sum(v[1] for v in months.values())) / n
        age_ok = cases[code]["hasBusiness"]
        f = {x["code"]: x["points"] for x in s["factors"]}
        if "BUSINESS_CASH_BUFFER" in f and n >= 6 and Rv > 0:
            p = (Rv - Ev) / Rv * 100
            want = 15 if p >= 25 else 10 if p >= 15 else 5 if p >= 5 else 0
            if f["BUSINESS_CASH_BUFFER"] != want: bad(code, "остаток после расходов", f["BUSINESS_CASH_BUFFER"], want)
            t = (Decimal("0.8") * Rv - Ev) / Rv * 100
            want = 10 if t >= 10 else 7 if t >= 5 else 3 if t >= 0 else 0
            if f["IDEA_VERIFIED_STRESS_BUFFER"] != want: bad(code, "стресс-запас", f["IDEA_VERIFIED_STRESS_BUFFER"], want)
            weak = sum(1 for v in months.values() if Decimal(v[0]) < Decimal("0.7") * Rv)
            want = 15 if weak == 0 else 10 if weak <= 2 else 5 if weak <= 4 else 0
            if f["BUSINESS_STABILITY"] != want: bad(code, "стабильность", f["BUSINESS_STABILITY"], want)

    # 3. Предложения: независимый пересчёт графика
    def annuity_rows(P, rate, n, g):
        r = Decimal(str(rate)) / 1200
        debt, rows, pay = Decimal(P), [], None
        for k in range(1, n + 1):
            i = (debt * r).quantize(Decimal(1), ROUND_HALF_UP)
            if k <= g:
                pr = Decimal(0)
            else:
                if pay is None:
                    pay = (Decimal(P) * r / (1 - (1 + r) ** -(n - g))).quantize(Decimal(1), ROUND_HALF_UP)
                pr = debt if k == n else pay - i
            rows.append((pr, i)); debt -= pr
        return rows

    for code, e in exp.items():
        for o in e.get("offers") or []:
            monthly, over = {}, Decimal(0)
            for p in o["products"]:
                if p["product"] == "BANK_GUARANTEE":
                    over += p.get("fee", 0); continue
                if p["product"] == "OVERDRAFT":
                    x = (Decimal(p["amount"]) * Decimal(str(p["ratePercent"])) / 1200).quantize(Decimal(1), ROUND_HALF_UP)
                    for k in range(1, p["termMonths"] + 1): monthly[k] = monthly.get(k, 0) + x
                    if p["monthlyPayment"] != x: bad(code, o["kind"], "овердрафт платёж", p["monthlyPayment"], x)
                    continue
                rows = annuity_rows(p["amount"], p["ratePercent"], p["termMonths"], p.get("gracePeriodMonths", 0))
                if sum(r[0] for r in rows) != p["amount"]: bad(code, "долг не погашен")
                for k, (pr, i) in enumerate(rows, 1): monthly[k] = monthly.get(k, 0) + pr + i
                over += sum(r[1] for r in rows)
                if p["monthlyPayment"] != max(pr + i for pr, i in rows): bad(code, o["kind"], p["product"], "платёж", p["monthlyPayment"])
                if p["amount"] % 10000: bad(code, "сумма не кратна 10000")
            if o["firstMonthsPayment"] != monthly[1]: bad(code, o["kind"], "первый платёж", o["firstMonthsPayment"], monthly[1])
            if o["fullPayment"] != max(monthly.values()): bad(code, o["kind"], "полный платёж")
            if o["overpayment"] != over: bad(code, o["kind"], "переплата", o["overpayment"], over)
            if o["totalAmount"] != sum(p["amount"] for p in o["products"]): bad(code, o["kind"], "итог")
            # ставка: ключевая 14 + надбавка + поправка
            spread = {"LEASING": 4, "INVESTMENT_LOAN": 5, "CREDIT_LINE": 6, "OVERDRAFT": 7, "STARTER_LOAN": 8}
            adj = 2 if e["statusAfterSubmit"] == "MANUAL_REVIEW" else (-1 if e["score"]["total"] >= 90 else 0)
            for p in o["products"]:
                if p["product"] in spread and p["ratePercent"] != 14 + spread[p["product"]] + adj: bad(code, "ставка", p["product"], p["ratePercent"])
        # смета: итог и округление
        est = e.get("estimate")
        if est:
            tot = sum(i["amount"] for i in est["items"] if i["product"] != "PARTNER_SERVICE")
            if tot != est["total"]: bad(code, "итог сметы", tot, est["total"])
            if any(i["amount"] % 10000 for i in est["items"]): bad(code, "строка сметы не кратна 10000")
            main = (e.get("offers") or [None])[0]
            if main and not main["termsChanged"] and main["totalAmount"] != est["total"]: bad(code, "MAIN != смета без пометки")
        # SMALLER / ALTERNATIVE правила
        kinds = [o["kind"] for o in e.get("offers") or []]
        if kinds and kinds[0] != "MAIN": bad(code, "первое не MAIN")
        if len(kinds) > 3: bad(code, ">3 предложений")

    # 4. Паспорт T08: введённая дата отличается от эталона
    c = cases["T08"]["passport"]; ref = pas[f"{c['series']} {c['number']}"]
    if c["issueDate"] == ref["issueDate"]: bad("T08", "введённая дата выдачи совпадает с эталоном")

    return issues


if __name__ == "__main__":
    found = run()
    print("\n".join(found) if found else "Независимая проверка: расхождений нет")
    sys.exit(1 if found else 0)
