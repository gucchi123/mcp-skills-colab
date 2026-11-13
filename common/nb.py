"""ノートブック（Colab と手元の Jupyter の両方）で使う準備。

- API キーの探し方: Colab のシークレット → 環境変数 → （Windows）HKCU\\Environment。見つからなければ講師の記録の再生（replay）、記録も無ければ mock
- キーは画面にもファイルにも出さない。エラー文にキーらしい文字列があれば伏せ字にする
"""
from __future__ import annotations

import os
import re
import traceback
from contextlib import contextmanager

_SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")


def _find_key(in_colab: bool) -> str | None:
    if in_colab:
        try:
            from google.colab import userdata
            k = userdata.get("ANTHROPIC_API_KEY")
            if k:
                return k
        except Exception:  # シークレットが無い・ノートブックに許可していない
            pass
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    if os.environ.get("LLM_NO_KEY") == "1":  # 自己検査用: キーを持たない人の手元を再現する
        return None
    if os.name == "nt":  # Jupyter のカーネルがユーザー環境変数を引き継いでいないことがある
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                return winreg.QueryValueEx(h, "ANTHROPIC_API_KEY")[0]
        except OSError:
            return None
    return None


def choose_provider(in_colab: bool, prefer: str | None = None) -> str:
    """キーがあれば anthropic（記録があれば再生・費用 0）、無ければ講師の記録の再生（replay）、記録も無ければ mock。

    prefer に "mock" / "replay" / "anthropic" を渡すと、それを使う（キーが要る anthropic でキーが無ければ replay）。
    """
    key = _find_key(in_colab)
    has_rec = os.path.exists(os.path.join(os.getcwd(), ".cache", "llm.sqlite"))
    want = (prefer or os.environ.get("LLM_PROVIDER_PREFER") or "").lower()
    if want == "agent-sdk":                    # 講師の収録用。受講者は使わない (common/sdk_provider.py)
        os.environ["LLM_PROVIDER"] = "agent-sdk"
        print("講師の収録: Claude Code のログインで呼びます（API キーは使いません）→ provider = agent-sdk")
    elif key and want in ("", "anthropic"):
        os.environ["ANTHROPIC_API_KEY"] = key  # SDK が読む場所に置くだけ。表示しない
        os.environ["LLM_PROVIDER"] = "anthropic"
        print("API キーが見つかりました（表示しません）→ provider = anthropic")
        print("  同じ依頼の記録が .cache/llm.sqlite にあれば再生します（費用 0・すぐ終わる）")
    elif has_rec and want in ("", "anthropic", "replay"):
        os.environ["LLM_PROVIDER"] = "replay"
        print(("講師の実行記録を再生します" if key else "API キーが見つからないので、講師の実行記録を再生します")
              + " → provider = replay（費用 0）")
        print("  記録と違う依頼（入力を変えたなど）はエラーで止まります。自分で試すときはキーを登録してください。")
    else:
        os.environ["LLM_PROVIDER"] = "mock"
        print("mock で動かします（API を呼びません）。")
        print("  mock の答えは決まった筋書きです。正答率などの数字は性能の証拠になりません。")
    del key
    return os.environ["LLM_PROVIDER"]


def redact(s: str) -> str:
    return _SECRET.sub("[伏せ字]", s)


@contextmanager
def safe():
    """セルの中のエラーを短く表示する（キーらしい文字列は伏せる）。"""
    try:
        yield
    except Exception as e:  # noqa: BLE001
        msg = redact(f"{type(e).__name__}: {e}")[:300]
        print(f"⚠ エラーで止まりました: {msg}")
        tb = redact(traceback.format_exc().splitlines()[-3] if len(traceback.format_exc().splitlines()) >= 3 else "")
        if tb:
            print("  場所:", tb.strip()[:200])
