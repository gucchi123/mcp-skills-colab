"""ラボ 9 の入口 (run_build_skill.py) を mock だけで回す。API キー無し・記録無しで通ること。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab09_")
os.environ["LLM_LEDGER"] = os.path.join(os.environ["SOLAHA_STATE_DIR"], "ledger.jsonl")
os.environ["LAB_OUT"] = "out_mock"

from run_build_skill import compare, main, parse_report  # noqa: E402
from skill_host import SkillError, SkillLoader  # noqa: E402

from common.kit import data_path, read_json  # noqa: E402

MONTHLY, CONTRACT = "solaha-monthly-report", "solaha-contract-review"


class TestLoader(unittest.TestCase):
    def test_probes_as_expected(self):
        r = main(["--part", "loader"])
        self.assertEqual(r["unexpected"], 0)
        self.assertIn("load_skill", r["tools"])
        self.assertIn("mcp__report__get_monthly_sales", r["tools"])

    def test_path_guards(self):
        ld = SkillLoader()
        for bad in ["../../common/llm.py", "..\\..\\common\\llm.py", "/etc/passwd", "C:/Windows/win.ini", "SKILL.md"]:
            with self.assertRaises(SkillError, msg=bad):
                ld.read_skill_file(MONTHLY, bad)
        with self.assertRaises(SkillError):                       # scripts/ の外の .py は実行しない
            ld.run_skill_script(MONTHLY, "references/style.md")
        with self.assertRaises(SkillError):                       # 別のスキルのスクリプトも指せない
            ld.run_skill_script(MONTHLY, "../../solaha-contract-review/scripts/overall.py")
        self.assertEqual(ld.run_skill_script(CONTRACT, "overall.py", {"args": ["[]"]}).strip(), "問題なし")

    def test_description_override(self):
        ld = SkillLoader(descriptions={MONTHLY: "レポートを作る。"})
        self.assertEqual(ld.skills[MONTHLY]["description"], "レポートを作る。")
        self.assertNotEqual(SkillLoader().skills[MONTHLY]["description"], "レポートを作る。")   # 元は変わらない


class TestTrigger(unittest.TestCase):
    def test_keyword_plan_all(self):
        s = main(["--provider", "mock", "--part", "trigger", "--all"])["summary"]
        self.assertEqual(s["n"], 20)
        self.assertEqual(set(s["wrong"]), {"T-08", "T-09", "T-15", "T-17", "T-20"})
        m = s["scores"][MONTHLY]
        self.assertEqual((m["tp"], m["picked"], m["expected"]), (8, 9, 10))
        self.assertEqual(s["scores"]["none"], {"ok": 3, "n": 5})

    def test_vague_is_wired(self):
        r = main(["--provider", "mock", "--part", "trigger", "--only", "T-01", "--variant", "vague"])
        self.assertEqual(r["summary"]["variant"], "vague")
        self.assertEqual(r["rows"][0]["picked"], MONTHLY)          # mock は説明文を読まないので同じ


class TestEndToEnd(unittest.TestCase):
    def test_one_month_matches_gold(self):
        r = main(["--provider", "mock", "--month", "2026-08"])
        row = r["rows"][0]
        self.assertEqual(row["mismatch"], [])
        self.assertTrue(all(row["steps"].values()), row["steps"])
        self.assertEqual(row["called"][0], "load_skill")

    def test_all_months(self):
        s = main(["--provider", "mock", "--all", "--name", "t"])["summary"]
        self.assertEqual(len(s["all_numbers_ok"]), 5)
        self.assertTrue(os.path.exists(os.path.join(HERE, "out_mock", "summary_t.json")))

    def test_check_catches_changed_numbers(self):
        """照合が本物であること: レポートの数字を 1 つ書き換えると、違うと出る。"""
        r = main(["--provider", "mock", "--month", "2026-09"])
        text = r["rows"][0]["text"]
        gold = read_json(data_path("report", "gold_numbers.json"))["2026-09"]
        self.assertEqual(compare(parse_report(text), gold), [])
        total = f"{gold['revenue_total']:,}"
        changed = text.replace(total, f"{gold['revenue_total'] + 1000:,}")
        self.assertEqual(compare(parse_report(changed), gold), ["revenue_total"])
        self.assertIn("low_stock_skus", compare(parse_report(text.replace("品目（", "品目（X-999、")), gold))


if __name__ == "__main__":
    unittest.main()
