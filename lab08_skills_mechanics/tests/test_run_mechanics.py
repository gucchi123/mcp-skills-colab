"""ラボ 8 の入口 (run_mechanics.py) を回す。Claude は呼ばない (API キー無しで通ること)。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab08_")
os.environ["LAB_OUT"] = "out_mock"
os.environ["LLM_NO_KEY"] = "1"          # --count-tokens の試験でキーを探さない (API を呼ばない)
os.environ["ANTHROPIC_API_KEY"] = ""

from run_mechanics import main  # noqa: E402
from skill_mech import est_tokens, parse_frontmatter, parse_text, validate  # noqa: E402

MONTHLY, CONTRACT = "solaha-monthly-report", "solaha-contract-review"


class TestMechanics(unittest.TestCase):
    def test_real_skills_pass(self):
        r = main(["--part", "validate"])["validate"]
        self.assertEqual(set(r), {MONTHLY, CONTRACT})
        for name, v in r.items():
            self.assertEqual(v["failed"], [], name)
            self.assertIn("allowed-tools", v["frontmatter"])
        self.assertEqual(r[MONTHLY]["refs"], ["references/style.md"])

    def test_bad_samples_caught(self):
        r = main(["--part", "bad"])["bad"]
        self.assertIn("name = フォルダ名", r["Solaha_Report"])
        self.assertIn("本文が指すファイルが在る", r["Solaha_Report"])
        self.assertIn("description 1〜1024 文字", r["claude-helper"])
        self.assertIn("metadata は 文字列→文字列", r["claude-helper"])          # version: 1.0 は数になる
        self.assertIn("name に anthropic / claude を含まない", r["claude-helper"])
        self.assertIn("frontmatter がある", r["no-frontmatter"])

    def test_frontmatter_parser(self):
        fm = parse_frontmatter('name: a-b\nmetadata:\n  owner: x\n  version: "1.0"\nallowed-tools: Read Bash(python:*)')
        self.assertEqual(fm, {"name": "a-b", "metadata": {"owner": "x", "version": "1.0"},
                              "allowed-tools": "Read Bash(python:*)"})
        bad = [c.rule for c in validate(parse_text("---\nname: x--y\ndescription: <b>d</b>\n---\n本文\n"))]
        self.assertIn("name は a-z 0-9 - だけ・先頭末尾と連続のハイフン無し", bad)
        self.assertIn("name・description に XML タグが無い", bad)

    def test_levels_and_script_output(self):
        r = main(["--part", "levels", "--count-tokens"])["levels"]
        self.assertNotIn("count_tokens", r)                                       # キーが無いので実測しない
        m = r[MONTHLY]
        self.assertLess(m["l1"][0], m["l2"][0])                                   # 段階 1 は本文より小さい
        out = m["scripts"]["scripts/build_report.py"]
        self.assertGreater(out["output_chars"], 100)                              # 実際に走って出力が出た
        self.assertLess(out["output_chars"], out["source"][0])
        self.assertIn("references/reading_notes.md", r[CONTRACT]["l3"])

    def test_compare_scales(self):
        r = main(["--part", "compare", "--n", "2,20"])["compare"]["rows"]
        for n in ("2", "20"):
            x = r[n]
            self.assertLess(x["skill_l1"][1], x["skill_fired"][1])
            self.assertLess(x["skill_fired"][1], x["system_all"][1])
        self.assertGreater(r["20"]["system_all"][1] - r["2"]["system_all"][1],
                           5 * (r["20"]["skill_l1"][1] - r["2"]["skill_l1"][1]))  # 増え方が 5 倍以上違う

    def test_split_tools_exist(self):
        r = main(["--part", "split"])["split"]
        for name in (MONTHLY, CONTRACT):
            self.assertTrue(all(r[name]["mcp_tools"].values()), name)             # allowed-tools の道具はサーバに在る
        self.assertEqual(len(r[CONTRACT]["policy_candidates"]), 1)

    def test_all_writes_summary(self):
        main(["--all", "--name", "t"])
        self.assertTrue(os.path.exists(os.path.join(HERE, "out_mock", "summary_t.json")))

    def test_est_tokens(self):
        self.assertEqual(est_tokens("abcd"), 1)
        self.assertEqual(est_tokens("月次"), 2)


if __name__ == "__main__":
    unittest.main()
