# ラボ 10 MCP×Skills を組み合わせる ― Claude Agent SDK と Claude API

> データはすべて架空 (ソラハ電機)。

ラボ 9 では Skill の読み込みと道具の繋ぎ込みを自分で書きました。ここでは出来合いの仕組みに任せます。

| 形 | Skill はどこで動く | MCP サーバはどこにつなぐ | 向いている場面 |
|---|---|---|---|
| Claude Agent SDK (`run_agent.py`) | 手元 (作業フォルダの `.claude/skills/`) | 手元の stdio のサーバをそのまま | 社内の PC・サーバで動かす業務の自動化 |
| Claude API の Skills (`run_api.py`) | Anthropic 側のコード実行の箱 | MCP コネクタはインターネットに出た HTTPS だけ。手元の数字は自分のホストで取って渡す | 自分のアプリに組み込む |

```
python run_agent.py --probe                          # つないで中身を見るだけ (モデルを呼ばない・費用 0)
python run_agent.py --task report --run --name opus  # 月次レポート (要 API キー)
python run_agent.py --task report --run --model claude-sonnet-5-5 --name sonnet
python run_agent.py --task order --run --name order  # 書き込みの道具は can_use_tool が止める
python run_api.py --dry                              # Claude API に送る request の形 (費用 0)
python run_api.py --run --name opus                  # Skill を API に上げて作らせる (要 API キー)
```

- 利用者 (SOLAHA_USER) はサーバを起動するときに渡す。書き込みの道具は allowed_tools に入れず、can_use_tool で記録して断る
- `--run` はキー (ANTHROPIC_API_KEY) が見つからなければモデルを呼ばずに止まる。Claude のプラン (Pro・Max など) で Claude Code に
  ログインしているなら、`--auth login` でキーを渡さずにログインで呼べる (費用の欄は API に換算した目安)
- シェルとファイルの許可: 通すのは「作業フォルダの中で Skill のスクリプトを動かす」(`check_shell`: パスを解決して判定) と
  「作業フォルダの中のファイルの編集」(`check_file_edit`) だけ。ほかは理由を添えて断る。Agent SDK の呼び出しは記録の再生が効かないので、講師の実行は `out/agent_<名前>.json` に残し、`--show-saved <名前>` で表示する
- 答え合わせ: Skill のスクリプトが作る 1〜3 節の数字の行が、出来上がったレポートに一字一句あるか (手で書き写した・丸めた数字を拾う)
- 試験: `python -m pytest -q lab10_mcp_x_skills/tests` (モデルを呼ばない)
