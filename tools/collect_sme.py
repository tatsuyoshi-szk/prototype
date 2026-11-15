"""中小企業を、データベース（backend/cache/）に追加する。選ぶ → Webで調べて事実と出典URLを保存 → 点数を記録 → 「中小企業」の印をつける。
**本物のAPIを使う＝費用がかかる**（1社あたり、調査 約$0.2 + 採点 約$0.04）。

  python tools/collect_sme.py --industries "製造業（金型・部品加工・食品加工）" --n 15
  python tools/collect_sme.py --industries "IT・Web制作・デザイン" --n 15 --workers 6

調べても、事実がほとんど見つからなかった企業（実在が確認できなかった企業を含む）は、保存しない（pipeline._informative）。
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import anthropic  # noqa: E402

import pipeline as P  # noqa: E402


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--industries", required=True, help="対象の業界（中小企業が多い業界）")
    ap.add_argument("--n", type=int, default=15, help="選ぶ企業の数")
    ap.add_argument("--workers", type=int, default=6, help="採点の並列数")
    args = ap.parse_args()

    client = anthropic.Anthropic(max_retries=4)
    rubric = P.load_rubric()
    known = [e["name"] for e in P.list_cached()]
    axes = [f"中小企業で働く（{args.industries}）", "若手から裁量がある", "外国人留学生を受け入れている"]
    focus = ("中小企業（従業員がおおよそ300人以下、または資本金3億円以下の、非上場の企業）だけを選ぶ。\n"
             "従業員が数百人を超える企業、上場している大手、有名な大企業、大手企業の子会社・グループ会社は、選ばない。\n"
             "従業員数が公開されている、規模の小さい（目安：従業員10〜200人）企業を優先する。\n"
             f"業界は、次のものに絞る：{args.industries}\n"
             "日本で、新卒または外国人留学生の採用実績が公開されている企業を優先する。実在が確かな企業だけを選び、名前を作らない。")
    print(f"対象：{args.industries} / 既存のデータベース {len(known)} 社 / 選ぶ企業 {args.n} 社", flush=True)

    r = P.run_research(axes, client, progress=lambda st, d="": print(f"  [{st}] {d}", flush=True),
                       avoid=known, research_only=True, n_companies=args.n, focus=focus)
    new = r["companies"][r["cached"]:]
    saved = [e for e in new if P.load_cached(e["name"])]      # 保存された企業だけ
    dropped = [e["name"] for e in new if not P.load_cached(e["name"])]
    print(f"調査：新規 {len(new)} 社のうち、保存 {len(saved)} 社、事実が少なく保存せず {len(dropped)} 社 / 調査の失敗 {len(r['failed'])} 社", flush=True)

    sizes = {"中小企業（印をつけた）": [], "大きい（印なし）": [], "規模が紹介文から分からない（印なし）": []}
    for e in saved:
        c = P.classify_sme(e.get("profile", ""))
        if c is True:
            P.save_tag(e["name"], "sme")
            sizes["中小企業（印をつけた）"].append(e["name"])
        elif c is False:
            sizes["大きい（印なし）"].append(e["name"])
        else:
            sizes["規模が紹介文から分からない（印なし）"].append(e["name"])
    print("規模の確認：" + " / ".join(f"{k} {len(v)}社" for k, v in sizes.items()), flush=True)
    bad = []

    def score(ev):
        try:
            company, _ = P.score_company(ev, [], rubric, client, P.MAIN_MODEL, "ja")
            P.save_scores(ev["name"], company["items"])
            return ev["name"]
        except Exception as exc:   # noqa: BLE001  1社の失敗で止めない
            bad.append(ev["name"])
            print(f"  採点の失敗 {ev['name']}: {type(exc).__name__}: {exc}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        done = [n for n in pool.map(score, saved) if n]
    backed = {e["name"]: sum(1 for it in e["items"].values() if it["source_url"] and not it["finding"].startswith("未確認")) for e in saved}
    print(json.dumps({"業界": args.industries, "保存": [e["name"] for e in saved], "規模": sizes, "採点して記録": len(done), "採点の失敗": bad,
                      "保存せず": dropped, "調査の失敗": r["failed"], "出典つきの項目数（社ごと）": backed}, ensure_ascii=False), flush=True)
    print(f"完了：保存 {len(saved)} 社 / 点数を記録 {len(done)} 社", flush=True)


if __name__ == "__main__":
    main()
