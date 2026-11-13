"""講義用のノートブックを作る (出力は空のまま保存する)。

    python notebooks/build_notebooks.py

どのノートブックも Colab と手元の Jupyter の両方でそのまま動く:
  - 0-1 のセルが実行場所を見分ける (Colab ならキットを取得して requirements を入れる。手元なら何もしない)
  - 0-2 のセルが API キーを探す (Colab のシークレット → 環境変数 → Windows のユーザー環境変数)。
    キーが無ければ講師の実行記録の再生 (replay・費用 0)、記録も無ければ mock
  - ラボの入口は async (MCP の Client が async のため)。セルでは `await amain([...])` で呼ぶ (Jupyter・Colab はセルの直下で await できる)
🔴 型は「見出しの md → コード」の繰り返し。ラボの担当は BOOKS を book_<番号>.py に足し、ここで読み込む。
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DISCLAIMER = "この教材に登場する会社・人物・製品・数値・文書はすべて架空のものです。実在の企業・団体・個人とは関係ありません。"
REPO_URL = "https://github.com/gucchi123/mcp-skills-colab.git"

SETUP = '''# 0-1. 実行場所を見分けて、キットのフォルダに移る (Colab のときだけ取得とインストールをする)
import os, sys, subprocess
REPO_URL = "{repo}"
try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
if IN_COLAB:
    KIT = "/content/mcp-skills-kit"
    if not os.path.exists(KIT):
        subprocess.run(["git", "clone", "-q", REPO_URL, KIT], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", f"{KIT}/requirements.txt"], check=True)
else:  # 手元: notebooks/ から開いた前提。キットの根 (common/ がある所) を探す
    KIT = os.path.abspath(".." if os.path.exists("../common/host.py") else ".")
os.chdir(KIT)
sys.path.insert(0, KIT)
print("実行場所:", "Colab" if IN_COLAB else "手元の Jupyter", "/ キットの根:", os.path.basename(KIT))'''.replace("{repo}", REPO_URL)

PROVIDER = '''# 0-2. Claude の呼び先を決める (キーは表示しない) と、ラボのモジュールを読めるようにする
from common.nb import choose_provider, safe
from common.kit import use_labs, utf8_console
PROVIDER = choose_provider(IN_COLAB)
use_labs(); utf8_console()'''

NO_LLM = '''# 0-2. このノートブックは Claude を呼びません (API キー不要)。ラボのモジュールを読めるようにする
from common.nb import safe
from common.kit import use_labs, utf8_console
use_labs(); utf8_console()'''


def nb(title, intro, cells, llm=True):
    lines = ["- 上から順に実行します。0 のセルは準備です (Colab でも手元の Jupyter でも同じ)。"]
    if llm:
        lines.append("- API キーが無ければ、講師の実行記録を再生します (費用 0)。記録も無ければ mock で最後まで流れます (mock の数字は性能の証拠になりません)。")
    else:
        lines.append("- このノートブックは Claude を呼びません。API キーが無くても全部動きます。")
    lines.append("- 🔴 データはすべて架空の会社・文書です。")
    out = [("md", f"# {title}\n\n> **{DISCLAIMER}**\n\n{intro}\n\n" + "\n".join(lines)),
           ("md", "## 0. 準備"), ("code", SETUP), ("code", PROVIDER if llm else NO_LLM)]
    return out + cells


def cell(kind, src):
    c = {"cell_type": "markdown" if kind == "md" else "code", "metadata": {}, "source": src.strip("\n").splitlines(True)}
    if kind == "code":
        c.update(execution_count=None, outputs=[])
    return c


def save(name, cells):
    cs = [cell(k, s) for k, s in cells]
    for i, c in enumerate(cs):
        c["id"] = f"c{i:02d}"   # nbformat 4.5 はセルに id が要る (決まった値にして差分を小さく)
    doc = {"cells": cs, "nbformat": 4, "nbformat_minor": 5,
           "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                        "language_info": {"name": "python"}, "colab": {"provenance": []}}}
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote", name, len(cells), "cells")


M, C = "md", "code"


def all_books() -> dict:
    """book_*.py の BOOKS を集める (ラボごとに担当が分かれても、ここは書き換えずに済む)。"""
    books = {}
    for f in sorted(os.listdir(HERE)):
        if f.startswith("book_") and f.endswith(".py"):
            books.update(importlib.import_module(f[:-3]).BOOKS)
    return books


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    for name, cells in all_books().items():
        if name.startswith(only):
            save(name, cells)
