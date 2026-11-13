"""ラボ 7 の入口 (run_remote_auth.py) を回す。HTTP のサーバを子プロセスで 1 回立てて全場面を見る。Claude は呼ばない。"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ["SOLAHA_STATE_DIR"] = tempfile.mkdtemp(prefix="lab07_test_")
os.environ["LAB_OUT"] = "out_mock"

import run_remote_auth  # noqa: E402

KEY = "ab" * 32       # 試験だけの鍵。画面に出ないことを確かめる


class TestRemoteAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        buf = io.StringIO()
        with mock.patch.object(run_remote_auth.secrets, "token_hex", return_value=KEY), contextlib.redirect_stdout(buf):
            cls.r = run_remote_auth.main(["--users", "U-01,U-02,U-05"])
        cls.out = buf.getvalue()

    def test_noauth_and_metadata(self):
        self.assertEqual(self.r["noauth"]["status"], 401)
        self.assertIn('resource_metadata="http://127.0.0.1:', self.r["noauth"]["www_authenticate"])
        meta = next(v for k, v in self.r["prm"].items() if k.endswith("/mcp"))
        self.assertEqual(meta["status"], 200)
        self.assertEqual(meta["body"]["scopes_supported"], ["crm.read"])
        self.assertEqual(self.r["prm"]["/.well-known/oauth-protected-resource"]["status"], 404)

    def test_token_table(self):
        st = {x["case"]: (x["status"], x["error"]) for x in self.r["tokens"]["rows"]}
        for case in ("トークン無し", "形が違う (ただの文字)", "署名を書き換えた", "宛先が別のサーバ", "期限切れ (5 秒前)"):
            self.assertEqual(st[case], (401, "invalid_token"), case)
        self.assertEqual(st["範囲が inventory.read"], (403, "insufficient_scope"))
        self.assertEqual(st["U-02 crm.read"][0], 200)
        u99 = next(x for x in self.r["tokens"]["rows"] if x["case"].startswith("知らない"))
        self.assertTrue(u99["get_customer"].startswith("✗"))            # HTTP は通るが道具が断る

    def test_token_decides_user(self):
        self.assertEqual(len(self.r["users"]["U-01"]), 5)
        self.assertEqual(self.r["users"]["U-02"], [])
        self.assertIn("contact.email", self.r["users"]["U-05"])
        self.assertEqual(len(self.r["envuser"]["hidden"]), 5)            # サーバの SOLAHA_USER=U-04 は効かない
        self.assertNotIn("U-04", self.r["envuser"]["audit_users"])

    def test_no_key_or_full_token_on_screen(self):
        self.assertNotIn(KEY, self.out)
        self.assertIsNone(re.search(r"v1\.[A-Za-z0-9_\-]{20,}", self.out))
        self.assertEqual(self.r["decode"]["claims"]["sub"], "U-02")
        self.assertNotEqual(os.environ.get("SOLAHA_DEMO_AUTH_KEY"), KEY)   # 実行のあと鍵は元に戻す


if __name__ == "__main__":
    unittest.main()
