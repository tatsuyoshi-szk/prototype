"""データベース（backend/cache/）の企業に、共通14項目の点数を記録する（まだ点数がない企業だけ）。
**本物のAPIを使う＝費用がかかる**（1社に Opus を1回）。

  python tools/backfill_scores.py --shard 0/2      # 企業を2つに分けた、0番目の担当
  python tools/backfill_scores.py --shard 1/2
  python tools/backfill_scores.py --limit 1        # 試しに1社だけ

軸の判定は行わない（軸は人ごとに違うため）。記録済みの企業は飛ばすので、途中で止めても、もう一度動かせる。
"""
from __future__ import annotations

import argparse
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
    ap.add_argument("--shard", default="0/1", help="i/n：n個に分けた i 番目（0始まり）")
    ap.add_argument("--limit", type=int, default=0, help="この数の企業だけ（0 = 全部）")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    i, n = (int(x) for x in args.shard.split("/"))

    todo = [e for k, e in enumerate(P.list_cached()) if k % n == i and not e.get("scores")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"担当 {args.shard}：点数がない企業 {len(todo)} 社を採点します", flush=True)
    if not todo:
        return
    client = anthropic.Anthropic(max_retries=4)
    rubric = P.load_rubric()
    done, bad = [], []

    def work(ev):
        try:
            company, _ = P.score_company(ev, [], rubric, client, P.MAIN_MODEL, "ja")
            P.save_scores(ev["name"], company["items"])
            done.append(ev["name"])
        except Exception as exc:   # noqa: BLE001  1社の失敗で止めない
            bad.append(ev["name"])
            print(f"失敗 {ev['name']}: {type(exc).__name__}: {exc}", flush=True)
        if (len(done) + len(bad)) % 10 == 0:
            print(f"  {len(done) + len(bad)}/{len(todo)}（失敗 {len(bad)}）", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    print(f"完了：記録 {len(done)} 社、失敗 {len(bad)} 社", flush=True)
    if bad:
        print("失敗した企業:", "、".join(bad), flush=True)


if __name__ == "__main__":
    main()
