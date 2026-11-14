"""コマンドラインから使う。

  python -m survey --axis "海外と関わる製造業の仕事"            # フォームを開いて回答を集める
  python -m survey --profile runs/manual/xxx_v2.json             # 就活軸推定QAの保存結果から
  python -m survey --axis "..." --export out/                    # アンケートを作ってファイルに書き出すだけ
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from . import build_survey, collect_answers, make_result, print_result, render_html

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="共通項目と就活軸から重み付けアンケートを作る")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--axis", help="就活軸（一言）を直接指定する")
    src.add_argument("--profile", help="就活軸推定QA（pdca.chat）が保存したJSON。profile.job_axis を使う")
    ap.add_argument("--export", metavar="DIR", help="回答は集めず、survey.json と survey.html を書き出す")
    ap.add_argument("--port", type=int, default=0, help="フォームのポート番号（省略で空いている番号）")
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = ap.parse_args()

    if args.profile:
        with open(args.profile, encoding="utf-8") as f:
            job_axis = json.load(f)["profile"]["job_axis"]
    else:
        job_axis = args.axis

    s = build_survey(job_axis)

    if args.export:
        out = Path(args.export)
        out.mkdir(parents=True, exist_ok=True)
        (out / "survey.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "survey.html").write_text(render_html(s), encoding="utf-8")
        print(f"書き出しました: {out / 'survey.json'} / {out / 'survey.html'}")
        return

    result = make_result(s, collect_answers(s, port=args.port, open_browser=not args.no_browser))
    print_result(result)
    out = ROOT / "runs" / "manual"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d_%H%M%S}_survey.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n保存: {path}")


if __name__ == "__main__":
    main()
