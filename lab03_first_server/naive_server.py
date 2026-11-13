"""比べるための「素朴な書き方」: 無い番号を想定せず、DOCS[doc_id] でそのまま引く (KeyError が起きる)。

ステップ 2 の get_regulation (ToolError で断る) と、クライアントに届くものを比べる。
  - ToolError       → is_error=True、書いた文がモデルに届く
  - 想定外の例外    → is_error=True、文は「Error executing tool get_regulation」だけ。中身 (KeyError の値) は届かない。
                      詳しいことはサーバのログ (標準エラー) にだけ出る
🔴 この書き方を手本にしない。
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp.server import MCPServer  # noqa: E402

from common.kit import data_path, read_text  # noqa: E402

DOCS = {os.path.basename(p)[:-3]: read_text(p) for p in sorted(glob.glob(data_path("kb", "regulations", "*.md")))}

mcp = MCPServer("regs-naive")


@mcp.tool()
def get_regulation(doc_id: str) -> str:
    """文書番号の規程の全文を返す。"""
    return DOCS[doc_id]            # 無い番号なら KeyError


if __name__ == "__main__":
    mcp.run()
