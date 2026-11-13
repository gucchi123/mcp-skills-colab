"""ラボ 2: MCP の電文を自分の手で送って、ホスト (クライアント) が実際に何を送っているかを見る。Claude は呼ばない。

    python run_protocol.py                       # stdio: 1 行 1 通の JSON を送る (server/discover → tools/list → tools/call …)
    python run_protocol.py --part legacy         # 旧来の initialize を送ると何が返るか
    python run_protocol.py --part http           # Streamable HTTP: ヘッダーとキャッシュの目安 (ttlMs・cacheScope)
    python run_protocol.py --part client         # 同じことを mcp の Client で (同じプロセス)
    python run_protocol.py --part all --show     # 全部。--show は要求を毎回全文で、返事を長めに出す

版は 2026-07-28。🔴 initialize の握手もセッション ID もない。どの要求も params._meta に版・名乗り・できることを持つ。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wire import VERSION, HttpServer, StdioWire, dumps, hide_meta, request, shorten  # noqa: E402

LAB = "lab02_protocol"
ACCEPT = "application/json, text/event-stream"
QUERY = {"query": "出張の日当", "top_k": 1}


class View:
    """画面の出し方 (--show で長め)。"""

    def __init__(self, show: bool):
        self.show = show
        self.s, self.n, self.d = (200, 4, 8) if show else (40, 2, 4)

    def req(self, r: dict, first: bool = False):
        print("  → " + dumps(r if (first or self.show) else hide_meta(r)))

    def resp(self, r: dict):
        print("  ← " + dumps(shorten(r, self.s, self.n, self.d)))


# ---------------------------------------------------------------- stdio
STDIO_STEPS = [
    ("server/discover", {}),
    ("tools/list", {}),
    ("tools/call", {"name": "search_regulations", "arguments": QUERY}),
    ("resources/templates/list", {}),
    ("resources/read", {"uri": "kb://regulations/a-01"}),
    ("prompts/list", {}),
]


def part_stdio(v: View) -> list[dict]:
    print("■ stdio: python -m servers.kb を子プロセスで起動 (利用者 U-05)。標準入出力に 1 行 1 通の JSON")
    out = []
    with StdioWire() as w:
        for i, (method, params) in enumerate(STDIO_STEPS, 1):
            r = request(i, method, params)
            v.req(r, first=i == 1)
            resp = w.send(r)
            v.resp(resp)
            out.append({"method": method, "response": resp})
    tl = out[1]["response"]["result"]
    print(f"→ {len(out)} 往復。initialize なし・セッション ID なし。"
          f"tools/list は ttlMs={tl.get('ttlMs')} cacheScope={tl.get('cacheScope')} (この間は使い回してよい、という目安)")
    return out


# ---------------------------------------------------------------- 旧来の initialize
def _initialize(rid: int, version: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "old-client", "version": "1"}}}


def _err(resp: dict) -> str:
    e = resp.get("error")
    return f"error {e['code']}: {e['message']}" if e else "result (エラーなし)"


def part_legacy(v: View) -> dict:
    print("■ 旧来の initialize を送ると (stdio。1 通り目ごとに新しい子プロセス)")
    res = {}
    print("[1] つないで最初に initialize (欲しい版 = 2026-07-28 と書いても)")
    with StdioWire() as w:
        r = _initialize(1, VERSION)
        v.req(r, first=True)
        a = w.send(r)
        v.resp(a)
        print(f"   → 返ってきた版は {a['result']['protocolVersion']} (古い版の握手として扱われる)")
        r2 = request(2, "tools/list")
        print("   続けて 2026-07-28 の封筒 (_meta) で tools/list を送ると")
        v.req(r2)
        b = w.send(r2)
        print("  ← " + _err(b))
        res["init_first"] = {"version": a["result"]["protocolVersion"], "then_modern": b.get("error")}
    print("[2] 先に 2026-07-28 の要求 (tools/list) → 後から initialize")
    with StdioWire() as w:
        r = request(1, "tools/list")
        v.req(r, first=v.show)
        a = w.send(r)
        print("  ← result (tools " + str(len(a["result"]["tools"])) + " 個)")
        r2 = _initialize(2, "2025-11-25")
        v.req(r2)
        b = w.send(r2)
        print("  ← " + _err(b) + "  data=" + dumps(b["error"].get("data")))
        res["init_after_modern"] = b.get("error")
    print("[3] 2026-07-28 の接続 (先に server/discover を 1 通送ってある) で、_meta を付け忘れた tools/list")
    with StdioWire() as w:
        w.send(request(1, "server/discover"))
        r = request(2, "tools/list", with_meta=False)
        v.req(r)
        b = w.send(r)
        print("  ← " + _err(b))
        res["no_meta"] = b.get("error")
    print("→ 1 本の接続の「時代」は最初の 1 通で決まる。2026-07-28 の接続では initialize は断られ、毎回の _meta が要る")
    return res


# ---------------------------------------------------------------- Streamable HTTP
def _headers_view(h) -> str:
    sid = h.get("mcp-session-id")
    return f"content-type={h.get('content-type')} / mcp-session-id: {sid[:8] + '…' if sid else 'なし'}"


async def part_http(v: View) -> dict:
    import httpx2 as httpx
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    res = {}
    with HttpServer() as url:
        print(f"■ Streamable HTTP: http_kb.py を子プロセスで起動 → {url.replace(url.split('/')[2], '127.0.0.1:<空きポート>')}")
        base = {"Accept": ACCEPT, "MCP-Protocol-Version": VERSION}
        async with httpx.AsyncClient(timeout=15) as hc:
            async def post(label, extra, body):
                h = {**base, **extra}
                print(f"[{label}] POST  ヘッダー: " + " / ".join(f"{k}: {x}" for k, x in h.items() if k != "Accept"))
                if v.show:
                    print("  → " + dumps(body))
                r = await hc.post(url, headers=h, json=body)
                print(f"  ← {r.status_code}  {_headers_view(r.headers)}")
                return r

            r = await post("1 tools/list", {"Mcp-Method": "tools/list"}, request(1, "tools/list"))
            tl = r.json()["result"]
            print(f"  ← tools={[t['name'] for t in tl['tools']]}  ttlMs={tl.get('ttlMs')}  cacheScope={tl.get('cacheScope')}")
            res["tools_list"] = {"status": r.status_code, "session": r.headers.get("mcp-session-id"),
                                 "ttlMs": tl.get("ttlMs"), "cacheScope": tl.get("cacheScope"),
                                 "content_type": r.headers.get("content-type")}
            body = request(2, "tools/call", {"name": "search_regulations", "arguments": QUERY})
            r = await post("2 tools/call", {"Mcp-Method": "tools/call", "Mcp-Name": "search_regulations"}, body)
            sc = r.json()["result"]["structuredContent"]["result"][0]
            print(f"  ← structuredContent: {sc['doc_id']} {sc['title']} / {sc['section']}")
            res["call"] = {"status": r.status_code, "hit": sc["doc_id"]}
            r = await post("3 名前の食い違い", {"Mcp-Method": "tools/call", "Mcp-Name": "get_regulation"}, body)
            print("  ← " + _err(r.json()) + "  (ヘッダーはボディの写し。食い違いは門前で断る)")
            res["mismatch"] = {"status": r.status_code, "error": r.json().get("error")}
            print("[4] 旧来の POST initialize (版のヘッダーなし)")
            r = await hc.post(url, headers={"Accept": ACCEPT}, json=_initialize(4, "2025-11-25"))
            print(f"  ← {r.status_code}  {_headers_view(r.headers)}  (古い方式の互換。2026-07-28 では使わない)")
            res["legacy_init"] = {"status": r.status_code, "session": bool(r.headers.get("mcp-session-id")),
                                  "content_type": r.headers.get("content-type")}

        print("■ 同じサーバに mcp の Client(url) でつなぐ (SDK が送った POST を数える)")
        sent = []

        async def hook(req):
            sent.append({"method": req.headers.get("mcp-method"), "name": req.headers.get("mcp-name"),
                         "body": json.loads(req.content or b"{}")})
        async with Client(streamable_http_client(url, http_client=httpx.AsyncClient(event_hooks={"request": [hook]}))) as c:
            print(f"  protocol={c.protocol_version} server={c.server_info.name}  ← つないだ時点の POST: "
                  + ", ".join(s["method"] for s in sent))
            if v.show:
                print("  SDK が送った 1 通目: " + dumps(shorten(sent[0]["body"], v.s, v.n)))
            n0 = len(sent)
            lt = await c.list_tools()
            print(f"  list_tools 1 回目 → POST {len(sent) - n0} 通  ttl_ms={lt.ttl_ms} cache_scope={lt.cache_scope}")
            n1 = len(sent)
            await c.list_tools()
            print(f"  list_tools 2 回目 → POST {len(sent) - n1} 通  (ttl のあいだは手元の写しを使う)")
            n2 = len(sent)
            await c.list_tools(cache_mode="bypass")
            print(f"  list_tools(cache_mode='bypass') → POST {len(sent) - n2} 通")
            n3 = len(sent)
            cr = await c.call_tool("search_regulations", QUERY)
            s = sent[-1]
            print(f"  call_tool → POST {len(sent) - n3} 通 (Mcp-Method={s['method']} Mcp-Name={s['name']})"
                  f"  is_error={cr.is_error}")
            res["client"] = {"protocol": c.protocol_version, "posts": [s["method"] for s in sent],
                             "ttl_ms": lt.ttl_ms, "cache_scope": lt.cache_scope}
    print("→ HTTP でも 1 要求 = 1 POST で完結。返事は application/json、mcp-session-id は付かない")
    return res


# ---------------------------------------------------------------- 同じプロセスの Client
def _wire_tool(t) -> dict:
    return t.model_dump(mode="json", by_alias=True, exclude_none=True)


async def part_client(v: View) -> dict:
    from mcp import Client
    from common.identity import set_user
    from servers import kb

    print("■ 同じことを Client(kb.mcp) で (同じプロセス。子プロセスもポートも無い)")
    set_user("U-05")

    def raw_tools():
        with StdioWire() as w:
            return w.send(request(1, "tools/list"))["result"]["tools"]
    raw = await anyio.to_thread.run_sync(raw_tools)       # 比べる相手: stdio で生で受け取った tools/list
    async with Client(kb.mcp) as c:
        lt = await c.list_tools()
        proto = c.protocol_version
        print(f"  protocol={proto}  ttl_ms={lt.ttl_ms}  cache_scope={lt.cache_scope}")
        for t in lt.tools:
            print(f"  道具 {t.name} ({t.title})  引数 {list(t.input_schema['properties'])}"
                  f"  read_only_hint={t.annotations.read_only_hint}")
        same = [_wire_tool(t) for t in lt.tools] == raw
        print(f"  stdio で生で受け取った tools/list と同じ中身か: {same}")
        r = await c.call_tool("search_regulations", QUERY)
        h = r.structured_content["result"][0]
        print(f"  call_tool → is_error={r.is_error}  structured_content: {h['doc_id']} {h['section']}"
              f"  (電文の structuredContent / isError が snake_case の属性になる)")
    print("→ Client は「封筒を付けて 1 通送り、返事を型に直す」係。中で起きていることは上の生の電文と同じ")
    return {"protocol": proto, "tools": [t.name for t in lt.tools], "same_as_wire": same,
            "ttl_ms": lt.ttl_ms, "cache_scope": lt.cache_scope}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="stdio", choices=["stdio", "legacy", "http", "client", "all"])
    ap.add_argument("--show", action="store_true", help="要求を毎回全文で、返事を長めに出す")
    a = ap.parse_args(argv)
    v = View(a.show)
    parts = ["stdio", "legacy", "http", "client"] if a.part == "all" else [a.part]
    out = {}
    for p in parts:
        if p == "stdio":
            out["stdio"] = await anyio.to_thread.run_sync(part_stdio, v)
        elif p == "legacy":
            out["legacy"] = await anyio.to_thread.run_sync(part_legacy, v)
        elif p == "http":
            out["http"] = await part_http(v)
        elif p == "client":
            out["client"] = await part_client(v)
    return out


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
