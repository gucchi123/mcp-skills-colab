"""ラボ 2 の部品: MCP の電文 (JSON-RPC) を自分の手で送って、返事をそのまま見る。

  StdioWire   サーバを子プロセスで立て、標準入力に 1 行 1 通の JSON を書き、標準出力から 1 行ずつ読む
  start_http  サーバを Streamable HTTP で子プロセスに立てる (http_kb.py)。終わったら必ず止める
  meta()      2026-07-28 の「封筒」。どの要求にも params._meta として付ける
  shorten()   画面に出すために、長い文字・長い並びを縮める (中身の形はそのまま)

🔴 2026-07-28 には initialize の握手もセッション ID もない。毎回の要求が _meta に「版・名乗り・できること」を持つ。
"""
from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "2026-07-28"
CLIENT_INFO = {"name": "lab02-raw", "version": "0.1"}


def meta(version: str = VERSION) -> dict:
    """要求ごとに付ける _meta (版・クライアントの名乗り・クライアントができること)。"""
    return {"io.modelcontextprotocol/protocolVersion": version,
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            "io.modelcontextprotocol/clientCapabilities": {}}


def request(rid: int, method: str, params: dict | None = None, with_meta: bool = True) -> dict:
    p = dict(params or {})
    if with_meta:
        p["_meta"] = meta()
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": p}


def shorten(obj, s: int = 60, n: int = 3, depth: int = 5):
    """長い文字は s 字で切り、並びは n 個まで、深い所は {…} にする。画面で読むための縮め方。"""
    if isinstance(obj, str):
        t = obj.replace("\n", "⏎")
        return t if len(t) <= s else t[:s] + f"…(全{len(obj)}字)"
    if isinstance(obj, list):
        out = [shorten(x, s, n, depth - 1) for x in obj[:n]]
        if len(obj) > n:
            out.append(f"…ほか {len(obj) - n} 個")
        return out
    if isinstance(obj, dict):
        if depth <= 0:
            return "{…}"
        return {k: shorten(v, s, n, depth - 1) for k, v in obj.items()}
    return obj


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def hide_meta(req: dict) -> dict:
    """2 通目からは _meta を毎回同じなので短く見せる。"""
    r = json.loads(json.dumps(req))
    if "_meta" in r.get("params", {}):
        r["params"]["_meta"] = "…(上と同じ _meta)"
    return r


_STATE: list[str] = []


def state_env(user: str = "U-05") -> dict:
    """子プロセスのサーバに渡す環境変数。利用者は起動した人 (SOLAHA_USER)。書き込み先 (監査ログ) は一時フォルダ。"""
    if not _STATE:
        _STATE.append(os.environ.get("SOLAHA_STATE_DIR") or tempfile.mkdtemp(prefix="lab02_"))
    return {**os.environ, "PYTHONUTF8": "1", "SOLAHA_USER": user, "SOLAHA_STATE_DIR": _STATE[0]}


def _log_file(name: str):
    d = state_env()["SOLAHA_STATE_DIR"]
    os.makedirs(d, exist_ok=True)
    return open(os.path.join(d, f"lab02_{name}.log"), "ab")


class StdioWire:
    """with StdioWire() as w: resp = w.send(req)   (サーバ = python -m servers.kb)"""

    def __init__(self, module: str = "servers.kb", timeout: float = 15.0):
        self.module, self.timeout = module, timeout
        self.lines: queue.Queue = queue.Queue()

    def __enter__(self):
        self._log = _log_file("stdio")
        self.p = subprocess.Popen([sys.executable, "-m", self.module], cwd=ROOT, env=state_env(),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log)
        threading.Thread(target=self._read, daemon=True).start()
        return self

    def _read(self):
        for ln in self.p.stdout:
            self.lines.put(ln)

    def send(self, msg: dict):
        """1 通書く。id があれば返事 1 行を読んで dict で返す (通知なら None)。"""
        self.p.stdin.write((dumps(msg) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        if "id" not in msg:
            return None
        return json.loads(self.lines.get(timeout=self.timeout).decode("utf-8"))

    def __exit__(self, *exc):
        try:
            self.p.stdin.close()
            self.p.wait(5)
        except Exception:
            self.p.kill()
            self.p.wait(5)
        self._log.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HttpServer:
    """with HttpServer() as url: ...   (http_kb.py を子プロセスで立て、抜けるときに止める)"""

    def __enter__(self) -> str:
        import httpx2 as httpx
        self.port = free_port()
        self._log = _log_file("http")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "http_kb.py"), "--port", str(self.port)],
                                  cwd=ROOT, env=state_env(), stdout=self._log, stderr=self._log)
        base = f"http://127.0.0.1:{self.port}"
        for _ in range(150):
            try:
                httpx.get(base + "/", timeout=0.3)
                break
            except Exception:
                if self.p.poll() is not None:
                    raise RuntimeError("HTTP のサーバが起動できませんでした")
                time.sleep(0.1)
        return base + "/mcp"

    def __exit__(self, *exc):
        self.p.terminate()
        try:
            self.p.wait(10)
        except Exception:
            self.p.kill()
        self._log.close()
