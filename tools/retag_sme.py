"""データベース（backend/cache/）の「中小企業」の印を、見直す。API は使わない。
紹介文に従業員数（300人以下）か、資本金（3億円以下の非上場）が書かれている企業だけ、印を残す。
大きい企業、規模が紹介文から分からない企業は、印を外す（企業そのものは、データベースに残る）。

  python tools/retag_sme.py          # 結果を見るだけ
  python tools/retag_sme.py --apply  # 印を外す
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import pipeline as P  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
apply = "--apply" in sys.argv
keep, big, unknown = [], [], []
for e in P.list_cached():
    if "sme" not in (e.get("tags") or []):
        continue
    c = P.classify_sme(e.get("profile", ""))
    (keep if c is True else big if c is False else unknown).append(e["name"])
    if apply and c is not True:
        P.save_tag(e["name"], "sme", remove=True)
print(f"印を残す {len(keep)} 社 / 大きいので外す {len(big)} 社 / 規模が分からないので外す {len(unknown)} 社" + ("（外しました）" if apply else "（--apply で外す）"))
print("大きい:", "、".join(big))
print("規模が分からない:", "、".join(unknown))
