"""ラボ 10 の試験。モデルは呼ばない (--probe は同梱の CLI につなぐだけ・費用 0)。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab10_")
os.environ["LLM_LEDGER"] = os.path.join(os.environ["SOLAHA_STATE_DIR"], "ledger.jsonl")
os.environ["LAB_OUT"] = "out_mock"

import anyio  # noqa: E402

import run_agent  # noqa: E402
import run_api  # noqa: E402


class TestLab10(unittest.TestCase):
    def test_probe_loads_servers_and_skills(self):
        r = run_agent.main(["--probe"])
        self.assertEqual({s["name"]: s["status"] for s in r["servers"]},
                         {"report": "connected", "contract": "connected", "kb": "connected", "inventory": "connected"})
        self.assertEqual(sorted(s["name"] for s in r["skills"]), ["solaha-contract-review", "solaha-monthly-report"])
        self.assertEqual(r["mcp_tools"], 11)
        inv = next(s for s in r["servers"] if s["name"] == "inventory")
        self.assertIn(("create_purchase_order", "書き込みあり"), [tuple(t) for t in inv["tools"]])

    def test_run_refuses_without_key(self):
        old = {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "LLM_NO_KEY")}
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["LLM_NO_KEY"] = "1"
        try:
            with self.assertRaises(SystemExit):
                run_agent.main(["--task", "report", "--run"])
            with self.assertRaises(SystemExit):
                run_api.main(["--run"])
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_shell_allows_only_skill_scripts(self):
        ok = ["$env:PYTHONIOENCODING='utf-8'; python -I .claude/skills/solaha-monthly-report/scripts/build_report.py"
              " sales.json inquiries.json inventory.json",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py sales.json inquiries.json inventory.json > report.md",
              r"python .claude\skills\solaha-contract-review\scripts\check.py c.json",
              r"python -I .claude\skills\solaha-monthly-report\scripts\build_report.py report_2026-09\sales.json"
              r" report_2026-09\inquiries.json report_2026-09\inventory.json > report_2026-09\report.md",
              # 2026-10-25 の本物の実行で、以前の判定 (正規表現) が誤って断ったコマンド
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py sales.json inquiries.json inventory.json"
              " | Out-File -Encoding utf8 report.md; Get-Content -Encoding utf8 report.md",
              r"cd report_2026-09; python -I ..\.claude\skills\solaha-monthly-report\scripts\build_report.py sales.json"
              r" inquiries.json inventory.json | Out-File -Encoding utf8 report.md; Get-Content report.md -Encoding utf8",
              r"python -I .\.claude\skills\solaha-monthly-report\scripts\build_report.py .\report_2026-09\sales.json"
              r" .\report_2026-09\inquiries.json .\report_2026-09\inventory.json",
              "python " + os.path.join(run_agent.WORKSPACE, ".claude", "skills", "solaha-monthly-report", "scripts", "build_report.py")
              + " sales.json"]
        ng = ["python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json; Remove-Item x",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json | Out-File ..\\x.md",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json | Set-Content x.md",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json && del x",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py $(Get-Item x).json",
              "cd ..; python lab10_mcp_x_skills/workspace/.claude/skills/solaha-monthly-report/scripts/build_report.py a.json",
              "cd ..\\..; python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json",
              "Get-Content report.md", "python -c print(1)",
              "python other.py a.json", "python .claude/skills/other/scripts/x.py",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py ..\\..\\secret.json",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py a.json > ..\\x.md", "Remove-Item report.md",
              r"python .claude/skills/solaha-monthly-report/scripts/build_report.py C:\Users\x\a.json",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py /etc/a.json",
              "python .claude/skills/solaha-monthly-report/scripts/build_report.py a/../../b.json"]
        for c in ok:
            self.assertTrue(run_agent.skill_script_command(c), c)
        for c in ng:
            self.assertFalse(run_agent.skill_script_command(c), c)

    def test_file_edit_only_in_workspace(self):
        ws = run_agent.WORKSPACE
        self.assertTrue(run_agent.check_file_edit(os.path.join(ws, "report.md"))[0])
        self.assertTrue(run_agent.check_file_edit("out/report.md")[0])
        self.assertFalse(run_agent.check_file_edit(os.path.join(ws, ".claude", "skills", "x", "SKILL.md"))[0])
        self.assertFalse(run_agent.check_file_edit(os.path.join(ws, "..", "run_agent.py"))[0])
        self.assertFalse(run_agent.check_file_edit(r"C:\Windows\x.md")[0])

    def test_read_text_any(self):
        p = os.path.join(os.environ["SOLAHA_STATE_DIR"], "r.md")
        for enc, bom in (("utf-16-le", b"\xff\xfe"), ("utf-8", b"")):
            with open(p, "wb") as f:
                f.write(bom + "売上合計: 30,784,000 円".encode(enc))
            self.assertEqual(run_agent.read_text_any(p), "売上合計: 30,784,000 円")

    def test_task_without_run_calls_nothing(self):
        self.assertEqual(run_agent.main(["--task", "report"]), {})

    def test_score_report(self):
        exp = anyio.run(run_agent.expected_report, "2026-09")
        good = run_agent.score_report("前置き\n" + exp + "\n4. 次の一手 候補: …", exp)
        self.assertEqual(good["matched"], good["numeric_lines"])
        self.assertGreater(good["numeric_lines"], 5)
        bad = run_agent.score_report(exp.replace("30,784,000", "30,780,000"), exp)
        self.assertLess(bad["matched"], bad["numeric_lines"])

    def test_dry_requests(self):
        r = run_api.main(["--dry"])
        sk, cn = r["skills_request"], r["connector_request"]
        self.assertEqual(sk["tools"][0]["type"], "code_execution_20260521")
        self.assertEqual(sk["container"]["skills"][0]["type"], "custom")
        self.assertIn("mcp-client-2025-11-20", cn["betas"])
        self.assertEqual(cn["tools"][0]["mcp_server_name"], cn["mcp_servers"][0]["name"])


if __name__ == "__main__":
    unittest.main()
