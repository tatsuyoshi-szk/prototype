"""画面確認用の固定データ fixtures.json を作る（APIは呼ばない）。
backend/data/ にある、ランキングつきの保存データのうち、いちばん新しいものから作る。先に、画面で1回、最後まで通しておく。"""
import glob, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from survey import build_survey

files = sorted(glob.glob(str(ROOT / "backend" / "data" / "*.json")), key=os.path.getmtime, reverse=True)
for f in files:
    d = json.load(open(f, encoding="utf-8"))
    if d.get("ranking") and d.get("axes"):
        break
else:
    raise SystemExit("ランキングつきの保存データがありません。先に、画面で1回、最後まで通してください。")
out = {"axes": d["axes"], "transcript": d["transcript"], "survey": build_survey(d["axes"]), "ranking": d["ranking"]}
json.dump(out, open(Path(__file__).parent / "fixtures.json", "w", encoding="utf-8"), ensure_ascii=False)
print("fixtures.json を作りました:", d["axes"])
