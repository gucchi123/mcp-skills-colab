"""ラボ 2 の入口 (run_protocol.py) を回す。Claude は呼ばない。子プロセスのサーバを立てて、終わったら止める。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab02_")

from run_protocol import main  # noqa: E402


class TestProtocol(unittest.TestCase):
    def test_stdio_raw(self):
        rows = main(["--part", "stdio"])["stdio"]
        self.assertEqual([r["method"] for r in rows][:3], ["server/discover", "tools/list", "tools/call"])
        disc = rows[0]["response"]["result"]
        self.assertEqual(disc["supportedVersions"], ["2026-07-28"])
        tl = rows[1]["response"]["result"]
        self.assertEqual((tl["ttlMs"], tl["cacheScope"]), (300000, "public"))     # kb.py の cache_hints
        call = rows[2]["response"]["result"]
        self.assertFalse(call["isError"])
        self.assertEqual(call["structuredContent"]["result"][0]["doc_id"], "a-06")
        self.assertTrue(all("error" not in r["response"] for r in rows))

    def test_legacy_initialize(self):
        r = main(["--part", "legacy"])["legacy"]
        self.assertEqual(r["init_first"]["version"], "2025-11-25")             # 2026-07-28 を頼んでも古い版で答える
        self.assertEqual(r["init_first"]["then_modern"]["code"], -32600)
        self.assertEqual(r["init_after_modern"]["code"], -32022)
        self.assertEqual(r["no_meta"]["code"], -32602)

    def test_http(self):
        r = main(["--part", "http"])["http"]
        self.assertEqual(r["tools_list"]["status"], 200)
        self.assertIsNone(r["tools_list"]["session"])                          # セッション ID は付かない
        self.assertEqual(r["tools_list"]["content_type"], "application/json")
        self.assertEqual(r["mismatch"]["status"], 400)
        self.assertEqual(r["mismatch"]["error"]["code"], -32020)
        self.assertTrue(r["legacy_init"]["session"])                            # 古い方式だけセッション ID
        # Client: 2 回目の list_tools は送らない (キャッシュ)、bypass で 1 通
        self.assertEqual(r["client"]["posts"], ["server/discover", "tools/list", "tools/list", "tools/call"])

    def test_client_same_as_wire(self):
        r = main(["--part", "client"])["client"]
        self.assertEqual(r["protocol"], "2026-07-28")
        self.assertTrue(r["same_as_wire"])
        self.assertEqual(r["tools"], ["search_regulations", "get_regulation"])


if __name__ == "__main__":
    unittest.main()
