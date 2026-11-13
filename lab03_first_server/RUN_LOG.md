# RUN_LOG ラボ 3

記録日 2026-10-24 / Python 3.13.14 / mcp 2.3.0 / Windows 11・キットの根で `PYTHONUTF8=1` / Claude は呼んでいない (API キー不要)

下は `python lab03_first_server/run_first_server.py ...` を 1 つずつ回した出力そのもの。

## 読み取れること

- ステップ 1: 関数名 → name、docstring → description、型ヒント → inputSchema の type、既定値のある `limit` は required から外れる。戻り値 `str` は outputSchema `{"result": string}` に包まれる
- 🔴 docstring の `Args:` の節は description に丸ごと入るだけで、inputSchema の引数の説明 (`properties.*.description`) にはならない。引数の説明は `Annotated[str, Field(description=...)]` に書く (ステップ 2)。`Field(ge=1, le=10)` は `minimum`/`maximum` になり、範囲外は SDK が呼ぶ前に断る
- 戻り値 `list[Hit]` は structured_content `{"result": [...]}` と、1 件ごとの TextContent (同じ中身の JSON) の両方で返る
- 🔴 `ToolError("…")` の文は頭に `Error executing tool <名前>: ` が付いて届く。想定外の例外 (KeyError) は `Error executing tool <名前>` だけで、中身は届かない (traceback はサーバのログにだけ)。どちらも例外ではなく `is_error=True` の結果
- 資料 (resource) の失敗は is_error の結果ではなく、クライアントで `MCPError` の例外になる (tests/test_step_servers.py)
- stdio でつないでも同じ結果 (サーバのコードは同じ、Client に渡すものだけ違う)

## 出力

```
$ python lab03_first_server/run_first_server.py --step 1
■ step1_server.py を同じプロセスで Client(mcp) につなぐ / protocol=2026-07-28
■ tools/list (SDK が関数から作った形)
  道具 search_regulations
    description: ソラハ電機の社内規程 (13 本) から、言葉を含む規程を探して、文書番号と題名と当たった行を返す。⏎⏎Args:⏎    keyword: 探す言葉⏎    limit: 返す件数の上限⏎
    🔴 docstring の Args: は description に入っただけ。引数ごとの説明は空のまま
    引数 keyword: string  必須  (説明なし)
    引数 limit: integer  {'default': 3}  (説明なし)
    outputSchema: ['result']
■ call_tool search_regulations(keyword='出張') → is_error=False
  a-03 職務権限規程 (1 行): 承認者が出張・休暇等で不在のときは、代理者規程に定める代理者が承認を代行する。
  a-04 代理者規程 (1 行): 本規程において「不在」とは、出張、休暇、病気その他の事由により、役職者が承認を行うことができない状態をいう。
  a-05 経費精算手続き (1 行): 業務遂行のために従業員が立て替えた交通費、出張費、消耗品費、会議費などの経費を対象とします。
  structured_content: {"result": "a-03 職務権限規程 (1 行): 承認者が出張・休暇等で不在のときは、代理者規程に定める代理者が承認を代行する。…(全214字)
→ str を返すと、文字の塊が {"result": "…"} に包まれるだけ。モデルは文字を読み解くしかない

$ python lab03_first_server/run_first_server.py --step 2
■ step2_server.py を同じプロセスで Client(mcp) につなぐ / protocol=2026-07-28
■ tools/list (SDK が関数から作った形)
  道具 search_regulations (規程を探す)
    description: ソラハ電機の社内規程 (13 本) から言葉を含む規程を探し、当たった行 (題名の行は除く) の多い順に返す。
    引数 keyword: string  必須  説明「探す言葉 (例: 出張、経費、在宅勤務)」
    引数 limit: integer  {'default': 3, 'minimum': 1, 'maximum': 10}  説明「返す件数の上限」
    outputSchema: ['result']  $defs=['Hit']
    annotations: {'read_only_hint': True, 'open_world_hint': False}
  道具 get_regulation (規程の全文)
    description: 文書番号の規程の全文を返す。番号が分からなければ先に search_regulations を使う。
    引数 doc_id: string  必須  説明「文書番号 (a-01〜a-13)」
    outputSchema: ['doc_id', 'title', 'chars', 'text']
    annotations: {'read_only_hint': True, 'open_world_hint': False}
■ call_tool search_regulations(keyword='出張', limit=2) → is_error=False
  structured: a-06 出張申請手続き (15 行)  本手続きは、ソラハ電機株式会社の従業員が業務上の出張を行う際の申請、承認および報…(全80字)
  structured: a-03 職務権限規程 (1 行)  承認者が出張・休暇等で不在のときは、代理者規程に定める代理者が承認を代行する。
  content: TextContent 2 個 (同じ中身の JSON 文字。古いクライアント向け)
■ get_regulation(a-06) → 出張申請手続き / 973 字
■ get_regulation(a-99) → is_error=True  「Error executing tool get_regulation: 文書 a-99 はありません。ある文書: a-01〜a-13」
■ 資料のひな形: ['regs://{doc_id}']
  read_resource(regs://a-01) → text/markdown  # 組織規程⏎⏎## 第1章 総則⏎⏎**第1条（目的）**…(全716字)
■ 定型文: ['answer_with_citation'] → 次の質問に、社内規程だけを根拠に答えてください。⏎質問: 海外出張は何日前に申請しますか⏎search_regulati…(全149字)

$ python lab03_first_server/run_first_server.py --errors
■ 失敗したとき、クライアント (= モデル) に届くもの
[ToolError で断る (step2)] is_error=True
  届いた文: 「Error executing tool get_regulation: 文書 a-99 はありません。ある文書: a-01〜a-13」
  サーバのログ: Tool 'get_regulation' failed: 'Error executing tool get_regu
[想定外の例外 KeyError (naive)] is_error=True
  届いた文: 「Error executing tool get_regulation」
  サーバのログ: Tool 'get_regulation' raised an unexpected exception +traceback
[引数の範囲外 limit=50 (step2)] is_error=True
  届いた文: 「Error executing tool search_regulations: 1 validation error for search_regulationsArgument…(全280字)」
  サーバのログ: Tool 'search_regulations' rejected arguments: ['limit']
[無い道具の名前 (step2)] is_error=True
  届いた文: 「Unknown tool: delete_regulation」
  サーバのログ: Tool 'delete_regulation' failed: 'Unknown tool: delete_regul
→ ToolError の文は頭に「Error executing tool <名前>: 」が付いて届く (直し方を書ける)。想定外の例外は中身を隠して「Error executing tool <名前>」だけ (traceback はサーバのログにだけ)。どれも例外ではなく is_error=True の結果として返る

$ python lab03_first_server/run_first_server.py --step 2 --stdio
■ step2_server.py を子プロセスで起動して stdio でつなぐ (Claude Desktop・Claude Code と同じつなぎ方)
  protocol=2026-07-28 server=regs-step2 道具=['search_regulations', 'get_regulation']
  search_regulations(在宅勤務) → 先頭 a-11 / is_error=False
→ サーバのコードは同じ。変わるのはつなぎ方 (Client に渡すもの) だけ

$ python lab03_first_server/run_first_server.py --step 2 --json
{
 "tools": [
  {
   "name": "search_regulations",
   "title": "規程を探す",
   "description": "ソラハ電機の社内規程 (13 本) から言葉を含む規程を探し、当たった行 (題名の行は除く) の多い順に返す。",
   "inputSchema": {
    "type": "object",
    "properties": {
     "keyword": {
      "description": "探す言葉 (例: 出張、経費、在宅勤務)",
      "title": "Keyword",
      "type": "string"
     },
     "limit": {
      "default": 3,
      "description": "返す件数の上限",
      "maximum": 10,
      "minimum": 1,
      "title": "Limit",
      "type": "integer"
     }
    },
    "required": [
     "keyword"
    ],
    "title": "search_regulationsArguments"
   },
   "outputSchema": {
    "$defs": {
     "Hit": {
      "properties": {
       "doc_id": {
        "description": "文書番号 (get_regulation に渡せる)",
        "title": "Doc Id",
        "type": "string"
       },
       "title": {
        "description": "規程の題名",
        "title": "Title",
        "type": "string"
       },
       "matched": {
        "description": "言葉を含む行の数",
        "title": "Matched",
        "type": "integer"
       },
       "first_line": {
        "description": "最初に当たった行 (80 字まで)",
        "title": "First Line",
        "type": "string"
       }
      },
      "required": [
       "doc_id",
       "title",
       "matched",
       "first_line"
      ],
      "title": "Hit",
      "type": "object"
     }
    },
    "properties": {
     "result": {
      "items": {
       "$ref": "#/$defs/Hit"
      },
      "title": "Result",
      "type": "array"
     }
    },
    "required": [
     "result"
    ],
    "title": "search_regulationsOutput",
    "type": "object"
   },
   "annotations": {
    "readOnlyHint": true,
    "openWorldHint": false
   }
  },
  {
   "name": "get_regulation",
   "title": "規程の全文",
   "description": "文書番号の規程の全文を返す。番号が分からなければ先に search_regulations を使う。",
   "inputSchema": {
    "type": "object",
    "properties": {
     "doc_id": {
      "description": "文書番号 (a-01〜a-13)",
      "title": "Doc Id",
      "type": "string"
     }
    },
    "required": [
     "doc_id"
    ],
    "title": "get_regulationArguments"
   },
   "outputSchema": {
    "properties": {
     "doc_id": {
      "title": "Doc Id",
      "type": "string"
     },
     "title": {
      "title": "Title",
      "type": "string"
     },
     "chars": {
      "description": "本文の字数",
      "title": "Chars",
      "type": "integer"
     },
     "text": {
      "description": "本文 (Markdown)",
      "title": "Text",
      "type": "string"
     }
    },
    "required": [
     "doc_id",
     "title",
     "chars",
     "text"
    ],
    "title": "Regulation",
    "type": "object"
   },
   "annotations": {
    "readOnlyHint": true,
    "openWorldHint": false
   }
  }
 ]
}
```

## 試験

```
$ python -m pytest -q lab03_first_server/tests
...........                                                              [100%]
11 passed
```
