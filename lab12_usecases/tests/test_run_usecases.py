"""ラボ 12 の入口 (run_usecases.py) と採点を mock だけで回す。API キー無し・記録無しで通ること。"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab12_")
os.environ["LLM_LEDGER"] = os.path.join(os.environ["SOLAHA_STATE_DIR"], "ledger.jsonl")
os.environ["LAB_OUT"] = "out_mock"

import anyio  # noqa: E402
from mcp import Client  # noqa: E402

from common.host import RunResult  # noqa: E402
from common.identity import set_user  # noqa: E402
from common.kit import read_jsonl  # noqa: E402
from run_usecases import main  # noqa: E402
from servers import expense  # noqa: E402
from uc_skill_host import mcp as skill_mcp  # noqa: E402
from usecases import (CRM_CASES, crm_expected, judge_contract, judge_crm, parse_report, reg_cases,  # noqa: E402
                      slip_dates)

SLOPPY_FAIL = {"K-4", "EX-3", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"} | {f"LC-0{i}" for i in range(1, 9)}


def fake(text: str, trace: list[dict]) -> RunResult:
    return RunResult(text=text, trace=trace, messages=[])


class TestRun(unittest.TestCase):
    def test_default_is_small(self):
        s = main(["--provider", "mock"])["summary"]
        self.assertEqual({u: v["n"] for u, v in s["per_uc"].items()}, {1: 2, 2: 2, 3: 2, 4: 1, 5: 1})

    def test_right_plan_passes_all(self):
        r = main(["--provider", "mock", "--all", "--name", "t"])
        s = r["summary"]
        self.assertEqual((s["n"], s["passed"]), (37, 37))
        # 登録はこの実行専用のフォルダに残る: 経費 3 件 (EX-3 は差し戻しなので申請しない)・発注 3 件 (PO-1・2・4)
        self.assertEqual(len(read_jsonl(os.path.join(r["state_dir"], "expenses.jsonl"))), 3)
        self.assertEqual([o["sku"] for o in read_jsonl(os.path.join(r["state_dir"], "orders.jsonl"))], ["K-203", "P-101", "M-401"])
        self.assertNotEqual(os.environ["SOLAHA_STATE_DIR"], r["state_dir"])          # 終わったら元に戻す

    def test_sloppy_plan_is_caught(self):
        s = main(["--provider", "mock", "--all", "--plan", "sloppy"])["summary"]
        failed = {i for v in s["per_uc"].values() for i in v["failed"]}
        self.assertEqual(failed, SLOPPY_FAIL)
        self.assertEqual(len(s["per_uc"][3]["review"]), 5)                           # 隠れた項目に触れない → 人が読む

    def test_confirm_messages_and_decline(self):
        rows = main(["--provider", "mock", "--uc", "2", "--only", "EX-1,PO-5"])["rows"]
        self.assertTrue(rows[0]["ok"] and "2,400 円" in rows[0]["notes"][0] and rows[0]["notes"][0].endswith("accept"))
        self.assertTrue(rows[1]["ok"] and "650,000 円" in rows[1]["notes"][0] and rows[1]["notes"][0].endswith("decline"))


class TestGold(unittest.TestCase):
    def test_expense_gold_agrees_with_server_rule(self):
        """手で決めた経費の正解 (規程の条から) が、サーバの判定と一致する。"""
        async def go():
            set_user("U-01")
            out = {}
            async with Client(expense.mcp) as c:
                for case in reg_cases():
                    if case["kind"] == "expense":
                        r = await c.call_tool("check_expense", {"employee": "山根 翔太", **case["slip"]})
                        out[case["id"]] = (case["gold"], r.structured_content)
            return out
        for cid, (g, j) in anyio.run(go).items():
            if g["register"]:
                self.assertEqual((j["decision"], j["approver"]), (g["decision"], g["approver"]), cid)
            else:
                self.assertEqual((j["decision"], j["reasons"]), ("差し戻し", [g["reason"]]), cid)

    def test_slip_dates_inside_deadline(self):
        for today in (dt.date(2026, 11, 1), dt.date(2027, 3, 1), dt.date(2026, 10, 24), dt.date(2028, 2, 29)):
            wd, sat = (dt.date.fromisoformat(x) for x in slip_dates(today))
            self.assertLess(wd.weekday(), 5)
            self.assertEqual(sat.weekday(), 5)
            for d in (wd, sat):
                nxt = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=10)
                self.assertTrue(d <= today <= nxt, (today, d))

    def test_crm_expected_from_gold(self):
        self.assertEqual(len(CRM_CASES), 7)
        vis, hid = crm_expected("U-05", "C-001")
        self.assertEqual(hid, {"contact.email", "rank", "credit_limit_yen"})
        vis, hid = crm_expected("U-04", "IND-002")
        self.assertIn("name", hid)


class TestJudges(unittest.TestCase):
    def test_crm_leak_is_caught(self):
        case = next(c for c in CRM_CASES if c["id"] == "U-05/C-001")
        tr = [{"type": "tool", "tool": "get_customer", "args": {"customer_id": "C-001"}, "is_error": False, "text": "",
               "structured": {"hidden": ["contact.email", "rank", "credit_limit_yen"]}}]
        audit = [{"tool": "get_customer", "customer": "C-001", "user": "U-05",
                  "hidden": ["contact.email", "rank", "credit_limit_yen"]}]
        res = judge_crm(case, fake("青木 亮 03-0000-1007 contact01@cust01.example 与信枠 2,000万", tr), audit)
        self.assertFalse(res.ok)
        self.assertTrue(any("出た" in m and not ok for ok, m in res.checks))
        res = judge_crm(case, fake("青木 亮 / 03-0000-1007 / メールと与信枠は権限で非表示です", tr), [])
        self.assertTrue(any("監査ログ" in m and not ok for ok, m in res.checks))   # 監査ログに残っていない

    def test_contract_wrong_verdict(self):
        tr = [{"type": "tool", "tool": t, "args": a, "is_error": False, "text": x, "structured": None}
              for t, a, x in (("get_contract_checklist", {}, ""), ("get_contract", {"contract_id": "LC-07"}, ""),
                              ("run_skill_script", {"script": "overall.py"}, "担当者確認"))]
        res = judge_contract({"id": "LC-07", "contract": "LC-07"}, fake("総合の判定: 部長確認\n| R6 | 当たる | 低 |", tr))
        self.assertFalse(res.ok)

    def test_parse_report_tolerant(self):
        t = "売上合計: 30,784,000 円 (前月比 +5.2%)\n件数の合計：80 件\n発注点以下だった主要品目: 2 品目(P-102、M-401)"
        self.assertEqual(parse_report(t), {"revenue_total": 30784000, "revenue_mom_pct": 5.2, "inquiries_total": 80,
                                           "low_stock_count": 2, "low_stock_skus": ["M-401", "P-102"]})


class TestSkillServer(unittest.TestCase):
    def test_runs_only_listed_scripts_and_reads_inside(self):
        async def go():
            async with Client(skill_mcp) as c:
                ok = await c.call_tool("run_skill_script", {"skill": "solaha-contract-review", "script": "overall.py",
                                                            "inputs": ['[{"rule": "R6", "level": "低"}]']})
                bad = await c.call_tool("run_skill_script", {"skill": "solaha-contract-review", "script": "../x.py", "inputs": []})
                out = await c.call_tool("read_skill_file", {"skill": "solaha-contract-review", "path": "../../common/llm.py"})
                return ok, bad, out
        ok, bad, out = anyio.run(go)
        self.assertEqual(ok.structured_content["result"], "担当者確認")
        self.assertTrue(bad.is_error and out.is_error)


if __name__ == "__main__":
    unittest.main()
