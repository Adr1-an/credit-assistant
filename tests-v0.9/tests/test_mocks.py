"""Тесты заглушек по HTTP. Запуск из корня репозитория: python -m unittest discover -s tests -v

Поднимают devserver.py на свободном порту (без внешних пакетов) и проверяют ответы
по contract/mocks-contract.md и tests/passport-tests.json.
"""
import datetime as dt
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mocks"))
sys.path.insert(0, str(ROOT / "tests"))
import devserver  # noqa: E402
import reference_scoring as ref  # noqa: E402

SEED = ROOT / "tests"


def load(name):
    return json.loads((SEED / name).read_text(encoding="utf-8"))


class MocksHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        devserver.Handler.log_message = lambda *a: None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), devserver.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    # ---- общее ----
    def test_health(self):
        self.assertEqual(self.req("GET", "/health"), (200, {"status": "ok"}))

    def test_unknown_inn_404(self):
        st, js = self.req("GET", "/fns/egrip/500100732259")
        self.assertEqual((st, js["code"]), (404, "NOT_FOUND"))

    def test_bad_inn_400(self):
        self.assertEqual(self.req("GET", "/bankruptcy/123")[0], 400)

    def test_wrong_method(self):
        self.assertEqual(self.req("GET", "/passport/check")[0], 405)

    def test_error_shape(self):
        st, js = self.req("GET", "/nope")
        self.assertEqual(st, 404)
        self.assertEqual(set(js), {"code", "message"})

    # ---- каждый тестовый клиент ----
    def test_all_cases_all_services(self):
        for case in load("cases.json")["cases"]:
            with self.subTest(case["code"]):
                p, inn = case["passport"], case["inn"]
                st, js = self.req("GET", f"/fns/egrip/{inn}")
                if case["hasBusiness"]:
                    self.assertEqual(st, 200)
                    self.assertEqual(js["inn"], inn)
                    self.assertEqual(js["status"], "ACTIVE")
                    self.assertFalse([k for k in js if k.startswith("_")])
                else:
                    self.assertEqual((st, js["code"]), (404, "NOT_IP"))
                st, js = self.req("GET", f"/fns/tax-debt/{inn}")
                self.assertEqual(st, 200)
                self.assertEqual(set(js), {"inn", "hasDebt", "debtAmount", "asOf"})
                st, js = self.req("POST", "/bki/report", {"passport": p, "inn": inn})
                if case["code"] == "T10":
                    self.assertEqual((st, js["code"]), (503, "SERVICE_UNAVAILABLE"))
                else:
                    self.assertEqual(st, 200)
                    self.assertIn("reportAsOf", js)
                    for loan in js["loans"]:
                        self.assertEqual(set(loan), {"type", "openedAt", "amount", "balance", "monthlyPayment",
                                                     "status", "currentOverdueDays", "overdues"})
                st, js = self.req("POST", "/fssp/search", {k: p[k] for k in ("lastName", "firstName", "middleName", "birthDate")})
                self.assertEqual((st, js), (200, {"proceedings": []}))
                st, js = self.req("GET", f"/bankruptcy/{inn}")
                self.assertEqual(st, 200)
                self.assertEqual(set(js), {"inn", "inProcedure", "stage", "startedAt", "completedAt"})
                st, js = self.req("POST", "/passport/check", p)
                self.assertEqual(st, 200)
                if case["code"] == "T08":
                    self.assertEqual(js, {"valid": True, "reason": None, "holderMatch": False, "mismatchFields": ["ISSUE_DATE"]})
                else:
                    self.assertEqual(js, {"valid": True, "reason": None, "holderMatch": True, "mismatchFields": []})

    def test_bankruptcy_scenarios(self):
        by = {c["code"]: c["inn"] for c in load("cases.json")["cases"]}
        self.assertEqual(self.req("GET", f"/bankruptcy/{by['T04']}")[1]["stage"], "REALIZATION")
        self.assertEqual(self.req("GET", f"/bankruptcy/{by['T09']}")[1]["completedAt"], "2024-01-15")

    def test_fssp_name_normalization(self):
        c = next(x for x in load("cases.json")["cases"] if x["code"] == "T07")  # Соловьёв Пётр
        body = {"lastName": "  солОВЬЕВ ", "firstName": "петр", "middleName": "Николаевич", "birthDate": c["passport"]["birthDate"]}
        self.assertEqual(self.req("POST", "/fssp/search", body)[0], 200)

    # ---- паспорт: P01–P16 ----
    def test_passport_acceptance(self):
        for t in load("passport-tests.json")["tests"]:
            with self.subTest(t["id"]):
                st, js = self.req("POST", "/passport/check", t["request"])
                self.assertEqual(st, t["expected"]["status"])
                for k, v in t["expected"]["response"].items():
                    self.assertEqual(js[k], v)
                # эталонные ФИО и даты никогда не возвращаются
                self.assertFalse({"lastName", "firstName", "birthDate", "issueDate"} & set(js))

    # ---- выписки ----
    def test_statements_parse(self):
        for case in load("cases.json")["cases"]:
            if case["statementFile"]:
                with self.subTest(case["code"]):
                    s, why = ref.parse_statement((SEED / case["statementFile"]).read_text(encoding="utf-8"), dt.date(2026, 10, 24))
                    self.assertIsNotNone(s, why)
                    self.assertEqual(s["otherIn"], 0)

    def test_bad_statements_rejected(self):
        for name in ("empty.csv", "not-csv.csv", "wrong-columns.csv", "bad-amount.csv"):
            with self.subTest(name):
                s, why = ref.parse_statement((SEED / "statements/bad" / name).read_text(encoding="utf-8"), dt.date(2026, 10, 24))
                self.assertIsNone(s)

    def test_classification_examples(self):
        # Контрольные примеры из mocks-contract.md
        for purpose, cinn, exp in [
            ("Оплата по договору поставки №15", "7801234567", "CUSTOMER"),
            ("Эквайринг. Реестр операций по картам", "", "ACQUIRING"),
            ("Зачисление кредита по договору", "7701234567", "OTHER_IN"),
            ("Возврат оплаты по договору", "7701234567", "OTHER_IN"),
            ("Оплата по счету", "", "OTHER_IN"),
            ("СБП перевод", "", "OTHER_IN"),
            ("Оплата услуг", "7701234567", "CUSTOMER"),
        ]:
            self.assertEqual(ref.classify_in(purpose, cinn), exp, purpose)

    def test_expected_results_up_to_date(self):
        import reference_offers
        before = (SEED / "expected-results.json").read_text(encoding="utf-8")
        self.assertEqual(ref.main(), 0)
        self.assertEqual(reference_offers.main(), 0)
        self.assertEqual((SEED / "expected-results.json").read_text(encoding="utf-8"), before,
                         "expected-results.json устарел: запусти reference_scoring.py и reference_offers.py")

    def test_offers_rules(self):
        for r in load("expected-results.json")["results"]:
            for o in r.get("offers") or []:
                with self.subTest(r["code"], kind=o["kind"]):
                    self.assertLessEqual(len(r["offers"]), 3)
                    self.assertEqual(o["totalAmount"], sum(p["amount"] for p in o["products"]))
                    self.assertTrue(all(p["amount"] % 10000 == 0 for p in o["products"]))
                    self.assertLessEqual(o["firstMonthsPayment"], o["fullPayment"])


if __name__ == "__main__":
    unittest.main()
