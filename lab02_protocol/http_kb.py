"""社内規程のサーバ (servers/kb.py) を Streamable HTTP で立てる。ラボ 2 の子プロセス用。

    python lab02_protocol/http_kb.py --port 8765      → http://127.0.0.1:8765/mcp

🔴 127.0.0.1 だけで待つ (外から入れない)。認可は付けていない。外に出すのは第 7 部の形 (トークン) にしてから。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from servers import kb  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    kb.mcp.run("streamable-http", host="127.0.0.1", port=a.port)
