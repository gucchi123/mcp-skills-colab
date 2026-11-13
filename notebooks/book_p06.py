from build_notebooks import C, M, nb

BOOKS = {}

BOOKS["p06_saas_writes.ipynb"] = nb("P06 SaaS を操作する ― 書き込みを安全に", "発注 (inventory) と経費の申請 (expense) の書き込みの道具を、確認・二重登録の防止・本人だけ・金額の承認の 4 つの守りで動かします。確認 1 往復の素の線と、Tasks の有無も確かめます。", [
    (M, "## 1. モデルに見せる引数の形\nPython の関数には `confirm` がありますが、モデルに見せる inputSchema には出ません。人に聞いて埋める引数だからです。"),
    (C, '''from run_saas_writes import amain as writes
with safe():
    r = await writes(["--only", "schema"])'''),
    (M, "## 2. 確認の文と、承認・断る\n登録の前にサーバが出す確認の文を見て、承認・断る・閉じた・承認だが ok=false の 4 通りで答えます。"),
    (C, '''with safe():
    r = await writes(["--only", "confirm"])'''),
    (M, "## 3. 同じ request_id の 2 回目と、本人だけ\n再試行で同じ依頼が 2 回届いても二重に登録しません。経費は本人の名前でしか申請できません。"),
    (C, '''with safe():
    r = await writes(["--only", "idem,self"])'''),
    (M, "## 4. 購買の依頼 10 件を正解と照合\n10 万円を超える発注は「承認待ち」で登録します。O-08 は依頼文で承認を飛ばすよう頼んでいますが、決めるのはサーバです。"),
    (C, '''with safe():
    r = await writes(["--only", "gold", "--all"])'''),
    (M, "## 5. 確認 1 往復の素の線\nSDK の Client とサーバの間に、行を書き写す中継をはさみます。`input_required` が返り、`inputResponses` を付けて送り直す流れがそのまま見えます。"),
    (C, '''with safe():
    r = await writes(["--only", "wire"])'''),
    (M, "## 6. Tasks (長い処理) は使えるか\nmcp 2.3.0 の型・クラスを調べ、サーバに `tasks/get` を送って確かめます。"),
    (C, '''with safe():
    r = await writes(["--only", "tasks"])'''),
    (M, "## 7. ホストで発注係を動かす (mock)\n🔴 モデルは mock (筋書きどおりの偽物) です。承認役が断る → 承認する → 同じ依頼をもう一度、の 3 回で、確認がどう出るかを見ます。"),
    (C, '''with safe():
    r = await writes(["--only", "host"])'''),
])
