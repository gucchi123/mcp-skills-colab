"""ラボ 5 の入口 (run_internal_data.py) を回す。Claude は呼ばない (API キー不要)。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab05_test_")
os.environ["LAB_OUT"] = "out_mock"

from run_internal_data import main  # noqa: E402


class TestInternalData(unittest.TestCase):
    def test_resources(self):
        r = main(["--only", "resources"])["resources"]
        self.assertEqual(r["crm"]["resources"], ["crm://policy"])
        self.assertEqual(r["kb"]["templates"], ["kb://regulations/{doc_id}"])
        self.assertIn("Error creating resource from template", r["bad_uri_error"])
        self.assertEqual(r["audit_before"], r["audit_after"])              # 資料の読み出しは監査ログに残らない

    def test_visibility_matches_gold(self):
        r = main(["--only", "visibility"])["visibility"]
        self.assertEqual((r["match"], r["n"]), (18, 18))
        self.assertEqual(r["hidden"]["C-002"]["U-02"], [])                 # C-002 の担当営業 (課長)
        self.assertIn("contact.email", r["hidden"]["C-002"]["U-05"])       # 窓口はメールを見ない
        self.assertEqual(r["hidden"]["IND-001"]["U-05"], [])               # 個人の連絡先は窓口だけ
        self.assertIn("name", r["hidden"]["IND-001"]["U-04"])              # 部長でも個人の氏名は見ない

    def test_visibility_all_189(self):
        r = main(["--only", "visibility", "--all"])["visibility"]
        self.assertEqual((r["match"], r["n"]), (189, 189))

    def test_audit(self):
        r = main(["--only", "audit"])["audit"]
        self.assertEqual([(e["user"], e["tool"]) for e in r["rows"]],
                         [("U-01", "get_customer"), ("U-05", "get_customer"), ("U-09", "get_customer"),
                          ("U-02", "find_customer")])
        self.assertIn("利用者が決まっていません", r["no_user_error"])
        self.assertNotIn("contact01", str(r["rows"]))                      # 値そのものはログに書かない

    def test_cache_and_report(self):
        r = main(["--only", "cache,report"])
        self.assertEqual((r["cache"]["crm"]["tools_ttl_ms"], r["cache"]["crm"]["tools_scope"]), (300000, "public"))
        self.assertEqual((r["cache"]["inventory"]["tools_ttl_ms"], r["cache"]["inventory"]["tools_scope"]), (0, "private"))
        self.assertTrue(r["report"]["all_ok"])
        self.assertEqual(len(r["report"]["rows"]), 5)

    def test_state_dir_restored(self):
        before = os.environ["SOLAHA_STATE_DIR"]
        r = main(["--only", "cache"])
        self.assertEqual(os.environ["SOLAHA_STATE_DIR"], before)
        self.assertNotEqual(r["state_dir"], before)


if __name__ == "__main__":
    unittest.main()
