"""ラボ 6 の入口 (run_saas_writes.py) を回す。Claude は呼ばない (host の場面は mock)。API キー不要。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab06_test_")
os.environ["LLM_LEDGER"] = os.path.join(os.environ["SOLAHA_STATE_DIR"], "ledger.jsonl")
os.environ["LAB_OUT"] = "out_mock"

from run_saas_writes import main  # noqa: E402


class TestSaasWrites(unittest.TestCase):
    def test_schema_hides_confirm(self):
        r = main(["--only", "schema"])["schema"]
        for tool in ("create_purchase_order", "submit_expense"):
            self.assertIn("confirm", r[tool]["python"])
            self.assertNotIn("confirm", r[tool]["schema"])
            self.assertFalse(r[tool]["annotations"]["read_only_hint"])

    def test_confirm_answers(self):
        r = main(["--only", "confirm"])["confirm"]
        self.assertFalse(r["po_accept_True"]["is_error"])
        self.assertTrue(r["po_decline_True"]["is_error"])
        self.assertIn("decline", r["po_decline_True"]["text"])            # 本体まで届かず SDK が止める
        self.assertIn("取りやめ", r["po_accept_False"]["text"])            # ok=false は本体が断る
        self.assertEqual(r["declined_logged"], ["c-4"])
        self.assertIn("elicitation capability", r["no_callback"])
        self.assertFalse(r["exp_accept"]["is_error"])
        self.assertTrue(r["exp_decline"]["is_error"])

    def test_idempotent(self):
        r = main(["--only", "idem"])["idem"]
        self.assertEqual([x["duplicate"] for x in r["po"]], [False, True])
        self.assertEqual((r["po_asked"], r["orders"]), (1, 1))
        self.assertEqual((r["exp_asked"], r["expenses"]), (1, 1))
        self.assertEqual(r["exp"][2]["decision"], "差し戻し")              # request_id を変えた同じ内容 = 分割申請

    def test_self_only(self):
        r = main(["--only", "self"])["self"]
        self.assertTrue(r["is_error"])
        self.assertIn("本人", r["text"])
        self.assertEqual((r["asked"], r["expenses"]), (0, 0))             # 断る申請に確認を出さない・登録もしない

    def test_gold_all(self):
        r = main(["--only", "gold", "--all"])["gold"]
        self.assertEqual((r["match"], r["n"]), (11, 11))
        o08 = next(x for x in r["rows"] if x["id"] == "O-08")
        self.assertEqual(o08["status"], "承認待ち")                        # 「承認は後回し」と頼まれても

    def test_wire(self):
        r = main(["--only", "wire"])["wire"]
        self.assertEqual(r["methods"][0], "server/discover")
        self.assertEqual(r["methods"].count("tools/call"), 2)
        self.assertTrue(r["same_request_state"])
        self.assertEqual(r["result"]["status"], "承認待ち")
        self.assertEqual(len(r["asked"]), 1)

    def test_tasks_not_in_sdk(self):
        r = main(["--only", "tasks"])["tasks"]
        self.assertEqual(r["types_2026"], [])
        self.assertEqual([x["error"]["code"] for x in r["replies"]], [-32601, -32601])

    def test_host_mock(self):
        r = main(["--only", "host"])["host"]
        self.assertEqual([len(x["asked"]) for x in r["runs"]], [1, 1, 0])
        self.assertNotIn("confirm", r["model_props"])
        self.assertEqual(r["orders"], 1)


if __name__ == "__main__":
    unittest.main()
