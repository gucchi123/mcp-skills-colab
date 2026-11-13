"""ラボ 3 の入口 (run_first_server.py) を回す。Claude は呼ばない。"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from run_first_server import main  # noqa: E402


class TestFirstServer(unittest.TestCase):
    def test_step1_schema_from_hints(self):
        r = main(["--step", "1"])
        t = r["tools"][0]
        self.assertEqual(t["name"], "search_regulations")
        self.assertEqual(t["inputSchema"]["required"], ["keyword"])          # 既定値のある limit は必須でない
        self.assertNotIn("description", t["inputSchema"]["properties"]["keyword"])   # Args: は引数の説明にならない
        self.assertIn("Args:", t["description"])
        self.assertEqual(list(t["outputSchema"]["properties"]), ["result"])  # str は result に包まれる
        self.assertFalse(r["is_error"])

    def test_step2_structured_and_errors(self):
        r = main(["--step", "2"])
        self.assertEqual(r["search"][0]["doc_id"], "a-06")
        self.assertTrue(r["not_found"]["is_error"])
        self.assertIn("a-01〜a-13", r["not_found"]["text"])
        self.assertEqual(r["resource_templates"], ["regs://{doc_id}"])
        t = {x["name"]: x for x in r["tools"]}
        self.assertTrue(t["get_regulation"]["annotations"]["readOnlyHint"])
        self.assertEqual(t["search_regulations"]["inputSchema"]["properties"]["limit"]["maximum"], 10)

    def test_errors(self):
        rows = {x["case"].split(" ")[0]: x for x in main(["--errors"])["errors"]}
        self.assertTrue(all(x["is_error"] for x in rows.values()))
        self.assertTrue(rows["ToolError"]["text"].endswith("ある文書: a-01〜a-13"))
        self.assertEqual(rows["想定外の例外"]["text"], "Error executing tool get_regulation")   # 中身は届かない
        self.assertTrue(rows["想定外の例外"]["traceback_logged"])
        self.assertEqual(rows["無い道具の名前"]["text"], "Unknown tool: delete_regulation")

    def test_json(self):
        r = main(["--step", "2", "--json"])
        self.assertEqual([t["name"] for t in r["tools"]], ["search_regulations", "get_regulation"])

    def test_stdio(self):
        r = main(["--step", "2", "--stdio"])
        self.assertEqual(r["protocol"], "2026-07-28")
        self.assertEqual(r["first"], "a-11")


if __name__ == "__main__":
    unittest.main()
