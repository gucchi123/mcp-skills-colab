"""ラボ 4 の入口 (run_tool_design.py) と部品を mock だけで回す。API キー無し・記録無しで通ること。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab04_")
os.environ["LLM_LEDGER"] = os.path.join(os.environ["SOLAHA_STATE_DIR"], "ledger.jsonl")
os.environ["LAB_OUT"] = "out_mock"

import anyio  # noqa: E402

from common import llm as L  # noqa: E402
from common.host import Host  # noqa: E402
from run_tool_design import main  # noqa: E402
from tool_variants import (VAGUE, first_tool_use, load_questions, make_tools, route, score_row,  # noqa: E402
                           server_of)


def base_tools() -> list[dict]:
    async def get():
        async with Host(user="U-01", provider=L.MockProvider()) as h:
            return h.tools
    return anyio.run(get)


class TestVariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = base_tools()
        cls.qs = {q["id"]: q for q in load_questions()}

    def test_questions(self):
        self.assertEqual(len(self.qs), 40)
        self.assertEqual(sum(1 for q in self.qs.values() if q["first_tool"] is None), 2)

    def test_variants_change_only_what_they_say(self):
        good, _ = make_tools("good", self.base)
        vague, _ = make_tools("vague", self.base)
        names, back = make_tools("names", self.base)
        self.assertEqual(len(good), 17)
        self.assertEqual([t["name"] for t in vague], [t["name"] for t in good])
        self.assertTrue(all(t["description"] == VAGUE[t["name"].split("__")[-1]] for t in vague))
        self.assertEqual([t["name"] for t in names], [f"tool{i:02d}" for i in range(1, 18)])
        self.assertEqual([t["description"] for t in names], [t["description"] for t in good])
        self.assertEqual(back["tool01"], good[0]["name"])
        self.assertEqual([t["input_schema"] for t in vague], [t["input_schema"] for t in good])
        self.assertEqual(self.base[0]["name"], "mcp__kb__search_regulations")      # 元は書き換えない

    def test_subset_is_domain_only(self):
        sub, _ = make_tools("subset", self.base, self.qs["TS-13"])                  # 在庫の問い
        self.assertEqual({server_of(t["name"]) for t in sub}, {"inventory"})
        sub, _ = make_tools("subset", self.base, self.qs["TS-39"])                  # 道具の要らない問い → kb
        self.assertEqual({server_of(t["name"]) for t in sub}, {"kb"})

    def test_router_reads_descriptions(self):
        q = self.qs["TS-13"]["question"]
        self.assertEqual(route(q, make_tools("good", self.base)[0])[0], "mcp__inventory__get_stock")
        self.assertNotEqual(route(q, make_tools("vague", self.base)[0])[0], "mcp__inventory__get_stock")

    def test_first_tool_use_and_scoring(self):
        resp = {"content": [{"type": "text", "text": "調べます"}, {"type": "tool_use", "id": "a", "name": "tool06", "input": {}},
                            {"type": "tool_use", "id": "b", "name": "tool01", "input": {}}]}
        self.assertEqual(first_tool_use(resp)[0], "tool06")
        self.assertEqual(first_tool_use({"content": [{"type": "text", "text": "晴れです"}]}), (None, "晴れです"))
        _, back = make_tools("names", self.base)
        self.assertTrue(score_row(self.qs["TS-13"], "tool06", back)["ok"])          # tool06 = get_stock
        r = score_row(self.qs["TS-13"], "tool99", back)                             # 渡していない名前
        self.assertEqual((r["pred"], r["ok"]), ("?tool99", False))
        self.assertTrue(score_row(self.qs["TS-39"], None, back)["ok"])              # 道具なしが正解


class TestRun(unittest.TestCase):
    def test_default_is_small(self):
        s = main(["--provider", "mock"])["summary"]
        self.assertEqual(s["n_questions"], 4)
        self.assertEqual(list(s["variants"]), ["good"])

    def test_all_variants(self):
        r = main(["--provider", "mock", "--all", "--variant", "all", "--name", "t"])
        v = r["summary"]["variants"]
        self.assertEqual(list(v), ["good", "vague", "names", "subset"])
        self.assertTrue(all(x["n"] == 40 for x in v.values()))
        self.assertGreater(v["good"]["first_ok"], v["vague"]["first_ok"])           # 筋書きは渡された説明で選ぶ
        self.assertLess(v["vague"]["block"]["chars"], v["good"]["block"]["chars"])
        self.assertLess(v["subset"]["block"]["chars_avg"], v["good"]["block"]["chars"])
        self.assertEqual(v["subset"]["block"]["tools_max"], 3)
        self.assertEqual(len(r["rows"]), 160)
        d = os.path.join(HERE, "out_mock")
        with open(os.path.join(d, "summary_t.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["n_questions"], 40)

    def test_same_answer_every_time(self):
        a = main(["--provider", "mock", "--all", "--variant", "names"])["rows"]
        b = main(["--provider", "mock", "--all", "--variant", "names"])["rows"]
        self.assertEqual([x["pred"] for x in a], [x["pred"] for x in b])

    def test_describe(self):
        r = main(["--describe"])
        self.assertLess(r["vague"]["chars"], r["good"]["chars"])
        self.assertLess(r["subset"]["max_chars"], r["good"]["chars"])


if __name__ == "__main__":
    unittest.main()
