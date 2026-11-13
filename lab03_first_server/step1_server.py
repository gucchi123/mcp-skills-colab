"""ステップ 1: いちばん小さいサーバ。道具は 1 つ (規程を言葉で探す)。

型ヒントと docstring を書くだけで、SDK が道具の説明 (description) と引数の形 (inputSchema) を作る。
  - 関数名        → 道具の名前 (name)
  - docstring     → 説明 (description)。モデルはこれを読んで「いつ使うか」を決める
                    🔴 Args: の節も description に丸ごと入るだけで、inputSchema の引数の説明にはならない (ステップ 2 で直す)
  - 引数の型ヒント → inputSchema の type。既定値のある引数は required から外れる
  - 戻り値の型    → outputSchema (str なら {"result": string} に包まれる)

起動 (stdio): python lab03_first_server/step1_server.py
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp.server import MCPServer  # noqa: E402

from common.kit import data_path, read_text  # noqa: E402

# 規程 13 本 (a-01〜a-13) を起動時に読んでおく。{文書番号: 本文}
DOCS = {os.path.basename(p)[:-3]: read_text(p) for p in sorted(glob.glob(data_path("kb", "regulations", "*.md")))}

mcp = MCPServer("regs-step1")


@mcp.tool()
def search_regulations(keyword: str, limit: int = 3) -> str:
    """ソラハ電機の社内規程 (13 本) から、言葉を含む規程を探して、文書番号と題名と当たった行を返す。

    Args:
        keyword: 探す言葉
        limit: 返す件数の上限
    """
    hits = []
    for doc_id, text in DOCS.items():
        lines = [ln.strip() for ln in text.splitlines()[1:] if keyword in ln]
        if lines:
            title = text.splitlines()[0].lstrip("# ")
            hits.append(f"{doc_id} {title} ({len(lines)} 行): {lines[0][:60]}")
    return "\n".join(hits[:limit]) or f"「{keyword}」を含む規程はありません"


if __name__ == "__main__":
    mcp.run()          # 既定は stdio (標準入出力で 1 行 1 通の JSON)
