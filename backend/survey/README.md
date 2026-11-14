# survey — 重み付けアンケート

就活軸推定QAのあとに行うアンケートを作るフォルダです。
**共通項目**と、**就活軸推定QAで推定した就活軸（一言）**をインプットにして、
「1 重視していない 〜 5 重視している」の5段階で答えるチェック式アンケート（全15項目）を作ります。
回答は、企業ごとのスコアを計算するときの重みになります。

```
インプット                                アウトプット
 ├ 共通項目14個（common_items.yaml）  →  アンケートの定義（JSON）・HTMLフォーム
 └ 就活軸（QAの出力 profile.job_axis）→  回答（各項目の 1〜5）と重み（合計1）
```

## ファイル
| ファイル | 役割 |
|---|---|
| `common_items.yaml` | タイトル・説明文・5段階の文言・就活軸の項目のひな型・共通項目14個。**項目を変えるときはここだけ直す** |
| `builder.py` | 共通項目と就活軸から、アンケートの定義（dict / JSON）を作る。回答から重みを計算する |
| `form.py` | アンケートの定義からチェック式のHTMLフォームを作る。手元でフォームを開いて回答を受け取る |
| `__main__.py` | コマンドラインから使う入口 |

`pyyaml` 以外のライブラリは使いません（Claude API も呼びません）。

## 使い方
```powershell
# 就活軸推定QA → アンケートを続けて行う（ふつうはこちら）
.venv\Scripts\python -m pdca.chat -v v2 --survey

# アンケートだけ試す（ブラウザでフォームが開き、送信すると結果が runs/manual/ に保存される）
.venv\Scripts\python -m survey --axis "海外と関わる製造業の仕事"
.venv\Scripts\python -m survey --profile runs\manual\<日時>_v2.json   # QAの保存結果から就活軸を読む

# アンケートを作ってファイルに書き出すだけ（ほかの画面で使うとき）
.venv\Scripts\python -m survey --axis "海外と関わる製造業の仕事" --export out
```

Python から使う場合:
```python
from survey import build_survey, collect_answers, make_result
s = build_survey("海外と関わる製造業の仕事")   # アンケートの定義（就活軸は、文字列1つでも、名前のリストでもよい）
# s = build_survey(["ウォッカづくり", "現場で働く", "ロシア出張"])   # リストなら、軸の数だけ項目ができる（id: job_axis_1, job_axis_2, …）
answers = collect_answers(s)                   # フォームで回答を集める {項目id: 1〜5}
result = make_result(s, answers)               # {"answers": ..., "weights": ...}
```

## アンケートの定義（`build_survey` の出力）
```json
{
  "title": "会社選びで大事にしたいこと アンケート",
  "lead": "あなたに合う会社のランキングを作るための…",
  "job_axis": "海外と関わる製造業の仕事",
  "scale": [{"value": 1, "label": "重視していない"}, …, {"value": 5, "label": "重視している"}],
  "questions": [
    {"id": "job_axis", "name": "あなたの就活軸「海外と関わる製造業の仕事」に合っているか", "explain": "…", "source": "job_axis"},
    {"id": "foreign_staff_ratio", "name": "外国籍社員の割合", "explain": "…", "source": "common"},
    …
  ]
}
```

## 回答の結果（`make_result` の出力）
- `answers`：各項目の点数（1〜5）
- `weights`：点数 ÷ 全項目の点数の合計（合計が1になる）。企業スコアの重みに使う
  - 「1 重視していない」の項目にも少し重みが残る。0にしたい場合は `builder.compute_weights` を変える

## 項目を変えるとき
- 共通項目の追加・削除・説明文の変更：`common_items.yaml` の `items`
- 就活軸の項目の聞き方・位置（先頭か最後か）：`common_items.yaml` の `job_axis_item`
- 項目IDは企業データ側の列と対応させる想定なので、変えるときはランキング計算側も合わせる
