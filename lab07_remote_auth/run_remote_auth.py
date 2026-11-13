"""ラボ 7: 顧客台帳のサーバを HTTP で公開し、トークンで利用者と範囲を決める (講座用の小さな認可)。

    python run_remote_auth.py                                 # 場面を全部 (サーバを 1 つ立てて最後に止める)
    python run_remote_auth.py --only noauth,prm               # トークン無しの 401 と、保護リソースのメタデータ
    python run_remote_auth.py --only tokens                   # トークンを変えて 401 / 403 / 200 の表
    python run_remote_auth.py --only users --users U-01,U-02,U-05   # 同じ get_customer を利用者ごとに
    python run_remote_auth.py --only envuser,decode           # サーバの SOLAHA_USER は効かない・トークンの中身

Claude は呼ばない (API キー不要)。サーバは servers/http_crm.py を子プロセスで空いているポートに立てる。
署名の鍵 (SOLAHA_DEMO_AUTH_KEY) は実行ごとにこのプロセスで作って子プロセスに渡す。🔴 鍵は表示しない。
🔴 common/demo_auth.py は仕組みを見せる見本で、本物の OAuth 2.1 ではない (README の「本物の IdP が足すもの」)。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import unicodedata

import anyio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import llm as L  # noqa: E402
from common.demo_auth import DemoVerifier, issue  # noqa: E402
from common.host import Host  # noqa: E402
from common.identity import staff  # noqa: E402
from common.kit import out_dir, read_jsonl, write_json  # noqa: E402
from remote_parts import decode, http_crm, httpx, post, short  # noqa: E402

LAB = "lab07_remote_auth"
SECTIONS = ["noauth", "prm", "tokens", "users", "envuser", "decode"]
SERVER_USER = "U-04"           # サーバの環境変数にわざと入れる (部長)。HTTP ではトークンが優先されることを見せる
COLS = [("name", "会社名"), ("rank", "ランク"), ("credit_limit_yen", "与信枠"), ("contact.name", "担当者"),
        ("contact.phone", "電話"), ("contact.email", "メール")]


def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WFA" else 1 for ch in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(1, n - _w(s))


def _www(r) -> str:
    return r.headers.get("www-authenticate", "")


# ------------------------------------------------------------------ 1. トークン無し
async def sec_noauth(url: str, state: str, a) -> dict:
    r = post(url, None)
    print("■ 1. トークン無しで tools/list を POST")
    print(f"  HTTP {r.status_code}")
    print(f"  WWW-Authenticate: {_www(r)}")
    print(f"  本文: {r.text}")
    print("  → resource_metadata= の URL を見れば、どの認可サーバからトークンをもらえばよいかが分かる (次の場面)")
    return {"status": r.status_code, "www_authenticate": _www(r), "body": r.json()}


# ------------------------------------------------------------------ 2. 保護リソースのメタデータ (RFC 9728)
async def sec_prm(url: str, state: str, a) -> dict:
    base = url.rsplit("/", 1)[0]
    meta_url = _www(post(url, None)).split('resource_metadata="')[1].rstrip('"')
    print("■ 2. 保護リソースのメタデータ (401 の resource_metadata が指す URL)")
    out = {}
    for path in (meta_url.replace(base, ""), "/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"):
        r = httpx.get(base + path, timeout=10)
        out[path] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}
        print(f"  GET {path} → {r.status_code}")
        if r.status_code == 200:
            for k, v in r.json().items():
                print(f"      {k}: {v}")
    print("  → メタデータはリソースのパス (/mcp) を後ろに足した場所にある (SDK が置く)。認可サーバのメタデータは")
    print("    このサーバには無い (この MCP サーバはトークンを確かめる側だけ。発行者 auth.solaha.example は架空)")
    return out


# ------------------------------------------------------------------ 3. トークンを変えて当てる
async def sec_tokens(url: str, state: str, a) -> dict:
    good = issue("U-02", url, ["crm.read"])
    cases = [
        ("トークン無し", None),
        ("形が違う (ただの文字)", "hello"),
        ("署名を書き換えた", good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")),
        ("宛先が別のサーバ", issue("U-02", "http://127.0.0.1:1/mcp", ["crm.read"])),
        ("期限切れ (5 秒前)", issue("U-02", url, ["crm.read"], ttl=-5)),
        ("範囲が inventory.read", issue("U-02", url, ["inventory.read"])),
        ("知らない利用者 U-99", issue("U-99", url, ["crm.read"])),
        ("U-01 crm.read", issue("U-01", url, ["crm.read"])),
        ("U-02 crm.read", good),
    ]
    local = DemoVerifier(audience=url)      # 同じ検証のコードを手元でも回して「なぜ断られたか」を見る (サーバは理由を返さない)
    print("■ 3. トークンを変えて tools/list と get_customer C-002 を当てる")
    print("  " + _pad("場合", 24) + _pad("トークン", 16) + "HTTP  error              " + _pad("検証役の理由 ※", 26) + "get_customer")
    rows = []
    for label, tok in cases:
        r = post(url, tok)
        err = _www(r).split('error="')[1].split('"')[0] if 'error="' in _www(r) else "-"
        why = "-"
        if tok is not None:
            n = len(local.rejected)
            at = await local.verify_token(tok)
            why = local.rejected[-1] if len(local.rejected) > n else f"通る {at.subject} {' '.join(at.scopes)}"
            why = why.replace("宛先が違う (http://127.0.0.1:1/mcp)", "宛先が違う (:1/mcp)")
        call = "-"
        if r.status_code == 200:
            call = await _get_customer(url, tok)
        rows.append({"case": label, "status": r.status_code, "error": err, "reason": why, "get_customer": call,
                     "www_authenticate": _www(r)})
        print(f"  {_pad(label, 24)}{_pad(short(tok), 16)}{r.status_code}   {err:<18} {_pad(why, 26)}{call}")
    w403 = next((x["www_authenticate"] for x in rows if x["status"] == 403), "")
    print(f"  403 の WWW-Authenticate: {w403.split(', resource_metadata')[0]}")
    print("  ※ サーバと同じ検証のコード (DemoVerifier) を手元で回した結果")
    print("  → 401 は「だれか分からない」、403 は「分かったが範囲が足りない」。どちらも道具まで届かない")
    print("    サーバの 401 は理由を返さない (Authentication required だけ)。理由はサーバの中の検証役にしか無いので、")
    print("    ここでは同じ検証のコードを手元で回して見せている (攻撃する側に手がかりを渡さないのは正しい作り)")
    return {"rows": rows}


async def _get_customer(url: str, tok: str) -> str:
    async with Host(["crm"], user=None, provider=L.MockProvider(), mode="http", urls={"crm": url},
                    tokens={"crm": tok}) as h:
        txt, err = await h.call("mcp__crm__get_customer", {"customer_id": "C-002"})
    if err:
        return "✗ " + txt.split(": ", 1)[-1][:40]
    return f"✓ 隠した {len(json.loads(txt)['hidden'])} 項目"


# ------------------------------------------------------------------ 4. 同じ get_customer を利用者ごとに
async def _view(url: str, uid: str, cid: str) -> dict:
    tok = issue(uid, url, ["crm.read"])
    async with Host(["crm"], user=None, provider=L.MockProvider(), mode="http", urls={"crm": url},
                    tokens={"crm": tok}) as h:
        txt, err = await h.call("mcp__crm__get_customer", {"customer_id": cid})
    if err:
        raise RuntimeError(txt)
    return json.loads(txt)


async def sec_users(url: str, state: str, a) -> dict:
    print(f"■ 4. Host(mode=\"http\") で get_customer {a.customer} を呼ぶ。利用者はトークンだけで決まる  〇=見える －=（非表示）")
    cw = [max(_w(lab), 4) + 1 for _, lab in COLS]
    print("  " + _pad("トークンの持ち主", 22) + "".join(_pad(lab, w) for (_, lab), w in zip(COLS, cw)) + "隠した数")
    out = {}
    for uid in a.users.split(","):
        v = await _view(url, uid, a.customer)
        out[uid] = v["hidden"]
        s = staff(uid)
        who = f"{uid} {s['name'].split()[0]}({'窓口' if s['role'] == 'desk' else s['department'][:2] + s['position']})"
        marks = "".join(_pad("－" if k in v["hidden"] else "〇", w) for (k, _), w in zip(COLS, cw))
        print(f"  {_pad(who, 22)}{marks}{len(v['hidden'])}")
    print("  → Host には user を渡していない (user=None)。HTTP では「起動した人」ではなく「トークンの持ち主」が利用者")
    return out


# ------------------------------------------------------------------ 5. サーバの SOLAHA_USER は効かない
async def sec_envuser(url: str, state: str, a) -> dict:
    print(f"■ 5. サーバは環境変数 SOLAHA_USER={SERVER_USER} ({staff(SERVER_USER)['name']}・部長) で起動してある")
    v = await _view(url, "U-01", "C-002")
    print(f"  U-01 のトークンで get_customer C-002 → 隠した項目 {v['hidden']}")
    print(f"  (部長として扱われていれば、隠す項目は 0 のはず)")
    p = os.path.join(state, "audit.jsonl")
    rows = read_jsonl(p) if os.path.exists(p) else []
    last = rows[-1] if rows else {}
    print(f"  サーバの監査ログ (最後の行): user={last.get('user')} tool={last.get('tool')} customer={last.get('customer')}"
          f" / この実行で {len(rows)} 行・利用者 {sorted({r['user'] for r in rows})}")
    print("  → common/identity.py はトークンがあればトークンの subject だけを見る (環境変数・set_user は見ない)")
    return {"hidden": v["hidden"], "audit_users": sorted({r["user"] for r in rows}), "audit_n": len(rows)}


# ------------------------------------------------------------------ 6. トークンの中身
async def sec_decode(url: str, state: str, a) -> dict:
    tok = issue("U-02", url, ["crm.read"])
    ver, body, sig = tok.split(".")
    c = decode(tok)
    print("■ 6. トークンの中身 (講座の形 v1.<中身>.<署名>。JWT ではない)")
    print(f"  トークン: {short(tok)} (全 {len(tok)} 文字・画面には先頭 12 文字だけ)")
    print(f"  {ver} / 中身 {len(body)} 文字 (base64url) / 署名 {len(sig)} 文字 (HMAC-SHA256。鍵は表示しない)")
    for k in ("sub", "aud", "scope", "iss"):
        print(f"    {k:<5}: {c[k]}")
    print(f"    exp  : {c['exp']} (あと {c['exp'] - int(time.time())} 秒)")
    print("  → 中身は鍵なしで読める (秘密ではない)。書き換えると署名が合わず 401。鍵を持つのは発行者とサーバだけ")
    return {"claims": {k: c[k] for k in ("sub", "aud", "scope", "iss")}, "ttl": c["exp"] - int(time.time())}


RUN = {"noauth": sec_noauth, "prm": sec_prm, "tokens": sec_tokens, "users": sec_users, "envuser": sec_envuser,
       "decode": sec_decode}


async def amain(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="場面をカンマ区切り: " + ",".join(SECTIONS))
    ap.add_argument("--users", default="U-01,U-02", help="users で比べるトークンの持ち主 (カンマ区切り)")
    ap.add_argument("--customer", default="C-002")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    want = a.only.split(",") if a.only else SECTIONS
    bad = [w for w in want if w not in RUN]
    if bad:
        raise SystemExit(f"--only が不明です: {bad} (使える: {SECTIONS})")
    prev_key = os.environ.get("SOLAHA_DEMO_AUTH_KEY")
    os.environ["SOLAHA_DEMO_AUTH_KEY"] = secrets.token_hex(32)       # この実行だけの鍵 (表示しない)
    result = {}
    try:
        with http_crm(server_user=SERVER_USER) as (url, state):
            print(f"[サーバ] servers/http_crm.py を {url} に起動 (子プロセス・SOLAHA_USER={SERVER_USER}・鍵は表示しない)\n")
            result["url_port_changes_each_run"] = True
            for i, w in enumerate(want):
                if i:
                    print()
                result[w] = await RUN[w](url, state, a)
        print("\n[サーバ] 止めました")
    finally:
        if prev_key is None:
            os.environ.pop("SOLAHA_DEMO_AUTH_KEY", None)
        else:
            os.environ["SOLAHA_DEMO_AUTH_KEY"] = prev_key
    if a.name:
        write_json(os.path.join(out_dir(LAB), f"summary_{a.name}.json"), result)
    return result


def main(argv=None) -> dict:
    return anyio.run(amain, argv)


if __name__ == "__main__":
    from common.kit import utf8_console
    utf8_console()
    main()
