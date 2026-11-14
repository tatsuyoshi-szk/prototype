"""保存（backend/cache）を増やすためのループ。視点（就活軸）を変えて企業を選び、調査して保存する（採点はしない）。
調査済みの企業は、選ばせない。各回の時間・新しく保存した数・失敗を記録する。"""
import json, sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
import anthropic
import server
server.check_api_key()
import pipeline as P

VIEWS = [
    ["大手メーカー（自動車・電機・機械）で海外駐在", "技術力を磨ける", "安定して長く働ける"],
    ["総合商社・専門商社で海外ビジネス", "若いうちから稼げる", "世界中で働ける"],
    ["外資系・日系のコンサルティング・戦略ファーム", "短期間で成長できる", "論理的思考を鍛えられる"],
    ["IT・Webサービス・SaaSで開発やプロダクトに関わる", "英語が使える環境", "新しい技術に挑戦できる"],
    ["銀行・証券・保険・投資銀行などの金融", "専門性が身につく", "グローバルな案件に関われる"],
    ["食品・化粧品・消費財・小売のブランド企業", "アジア展開に関われる", "商品づくりに携われる"],
    ["インフラ・エネルギー・重工・建設・物流", "社会に大きなスケールで貢献できる", "海外プロジェクトに関われる"],
    ["製薬・ヘルスケア・化学・素材メーカー", "研究開発や専門知識を活かせる", "グローバルに事業をしている"],
    ["ゲーム・エンタメ・メディア・広告・旅行・ホテル", "好きなことを仕事にできる", "訪日外国人・海外ファンと関われる"],
    ["スタートアップ・ベンチャー・外資IT・日系グローバル中堅", "若手でも裁量が大きい", "英語や多国籍のチームで働ける"],
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else len(VIEWS)
client = anthropic.Anthropic(max_retries=4)
rows = []
t_all = time.time()
for i, axes in enumerate(VIEWS[:N], 1):
    cached_names = []
    for f in P.CACHE_DIR.glob("*.json"):
        try: cached_names.append(json.loads(f.read_text(encoding="utf-8"))["name"])
        except Exception: pass
    t0 = time.time()
    try:
        r = P.run_research(axes, client, progress=lambda st, d="": None, avoid=cached_names, research_only=True)
        row = {"回": i, "視点": axes[0], "秒": round(time.time() - t0), "選ばれた": len(r["companies"]) + len(r["failed"]),
               "既存を再利用": r["cached"], "新規に保存": r["new"], "失敗": r["failed"],
               "新規の企業": [c["name"] for c in r["companies"][r["cached"]:]]}
    except Exception as e:
        row = {"回": i, "視点": axes[0], "秒": round(time.time() - t0), "エラー": f"{type(e).__name__}: {e}"[:300]}
    n_saved = len(list(P.CACHE_DIR.glob("*.json")))
    row["保存の累計"] = n_saved
    rows.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
print(f"\n合計 {time.time() - t_all:.0f}秒 / 保存した企業 {len(list(P.CACHE_DIR.glob('*.json')))}社 / エラーの回 {sum(1 for r in rows if 'エラー' in r)} / 失敗した企業 {sum(len(r.get('失敗', [])) for r in rows)}")
