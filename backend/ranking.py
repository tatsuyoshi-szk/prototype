"""企業のスコア計算とランキング。

  総合点 = Σ（アンケートの重み × 0〜1の点数）× 100

- 共通項目14個：企業のデータ（companies/data/*.json）に、採点基準（companies/rubric.yaml = グローバル度_評価指標_new.csv）で
  つけた 1〜5点が入っている。それを (点数−1)÷4 で 0〜1 にする。言及・根拠が見つからなかった項目は、基準どおり低い点（多くは1点）。
- 個人軸：AI（Sonnet 5.5）が、企業の事実（紹介文・海外拠点・axis_facts。出典URLつき）を読んで、各企業×各軸を 1〜5 で判定し、
  根拠にした事実の番号を返す（1回の呼び出し。Webは使わない）。AIに送るのは、軸の名前と企業の事実だけ。会話の内容は送らない。
- 「合うところ」「気になるところ」は、AIに書かせず、計算結果（点数と重み）と、データに入っている根拠・出典URLから作る。

コマンドラインから、保存したアンケート結果で試せる：
  python ranking.py data/20261114_165830_xxxx.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent
COMPANIES_DIR = ROOT / "companies"
DATA_DIR = COMPANIES_DIR / "archive" / "data"      # 保存済みのサンプル（実在21社・2026-11-14に調査）。通常の動作では使わない

MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
TOP_N = 5
MUST_MIN = 0.75                          # 「譲れない」項目は、4点以上（0.75以上）で、根拠があることが必要
STRENGTH_MIN, CONCERN_MAX = 0.6, 0.4     # 「合うところ」は 0.6 以上、「気になるところ」は 0.4 以下の項目から選ぶ


class RankingError(RuntimeError):
    """企業データがない、AIの判定が取れない、など。"""


# ---------------------------------------------------------------- 読み込み

def load_companies(data_dir: Path = DATA_DIR) -> list[dict]:
    files = sorted(data_dir.glob("*.json")) if data_dir.exists() else []
    companies = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    if not companies:
        raise RankingError("企業データがありません。companies/data/ に企業のJSONを置いてください。")
    return companies


# ---------------------------------------------------------------- 共通項目の点数

def score_common(companies: list[dict]) -> dict[str, dict[str, dict]]:
    """{企業id: {項目id: {"score": 0〜1, "unknown": bool, "display": str, "url": str, "basis": str}}}

    データの score（1〜5）を (score−1)÷4 にする。score がない項目（データの抜け）は 0 点・unknown 扱い。
    """
    out: dict[str, dict[str, dict]] = {}
    for c in companies:
        per = {}
        for iid, it in (c.get("items") or {}).items():
            sc = it.get("score")
            ok = isinstance(sc, (int, float)) and 1 <= sc <= 5
            per[iid] = {"score": (float(sc) - 1) / 4 if ok else 0.0,
                        "unknown": bool(it.get("unconfirmed")) or not ok,
                        "display": f"{int(sc)}/5" if ok else "情報なし",
                        "url": it.get("source_url", "") or "", "basis": it.get("basis", "") or ""}
        out[c["id"]] = per
    return out


# ---------------------------------------------------------------- 個人軸の適合度（AI）

def company_facts(c: dict) -> list[dict]:
    """個人軸の判定に使う、企業の事実の一覧 [{"fact", "url"}]（番号は 1 から。0 は「根拠なし」）。"""
    facts = []
    if c.get("profile"):
        facts.append({"fact": f"紹介: {c['profile']}", "url": c.get("profile_url", "")})
    offices = c.get("global_offices_list") or []
    if offices:
        url = ((c.get("items") or {}).get("global_offices") or {}).get("source_url", "")
        facts.append({"fact": "海外拠点がある国・地域: " + "、".join(offices), "url": url})
    for f in c.get("axis_facts") or []:
        facts.append({"fact": f["fact"], "url": f.get("source_url", "")})
    return facts


def _fit_schema(ids: list[str], n_axes: int) -> dict:
    cell = {"type": "object",
            "properties": {"score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                           "fact": {"type": "integer"}},
            "required": ["score", "fact"], "additionalProperties": False}
    scores = {"type": "object",
              "properties": {f"a{i}": cell for i in range(1, n_axes + 1)},
              "required": [f"a{i}" for i in range(1, n_axes + 1)], "additionalProperties": False}
    row = {"type": "object",
           "properties": {"company_id": {"type": "string", "enum": ids}, "scores": scores},
           "required": ["company_id", "scores"], "additionalProperties": False}
    return {"type": "object", "properties": {"fits": {"type": "array", "items": row}},
            "required": ["fits"], "additionalProperties": False}


def _company_brief(c: dict) -> str:
    nl = chr(10)
    facts = nl.join(f"    F{i}: {f['fact']}" for i, f in enumerate(company_facts(c), 1))
    return f"[{c['id']}] {c['name']}｜業界: {c.get('industry', '')}{nl}{facts}"


def judge_axes(axes: list[str], companies: list[dict], client, model: str = MODEL) -> dict[str, list[dict]]:
    """{企業id: [{"fit": 1〜5, "fact": 根拠にした事実の番号（0=なし）} × 軸の数]}。判断できないときは fit=3, fact=0。"""
    nl = chr(10)
    ids = [c["id"] for c in companies]
    axes_text = nl.join(f"a{i}: {a}" for i, a in enumerate(axes, 1))
    briefs = nl.join(_company_brief(c) for c in companies)
    prompt = f"""就職活動をしている留学生の「就活軸」と、企業の事実の一覧を渡します。
各企業が、各就活軸に、どのくらい合うかを、1〜5で判定してください。

# 判定のルール
- score: 5=とても合う、4=合う、3=どちらとも言えない／判断できる事実がない、2=あまり合わない、1=合わない。
- 根拠は、下の「企業の事実」（F1, F2…）に書かれていることだけにする。企業についての、書かれていない知識で、点数を上げ下げしない。
  判断に使える事実がなければ、score は 3、fact は 0 にする。
- fact: 判断の根拠にした事実の番号（F3 なら 3）。いちばん決め手になった事実を1つだけ。根拠がないとき（score が 3 のとき）は 0。
- 就活軸の名前の意味を、よく考える（例：「北米支社への転勤」は、北米に拠点があること、北米への赴任の機会があることが必要）。
- 企業の数と、軸の数をすべて埋める。

# 就活軸
{axes_text}

# 企業の事実
{briefs}"""
    kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    for attempt in range(2):
        try:
            resp = client.beta.messages.create(
                model=model, max_tokens=16000,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": _fit_schema(ids, len(axes))}},
                **kwargs)
            break
        except anthropic.BadRequestError as e:
            if attempt == 0 and "fallback" in str(e).lower():
                kwargs = {}
                continue
            raise
    if resp.stop_reason == "refusal":
        raise RankingError("モデルが応答を拒否しました")
    if resp.stop_reason == "max_tokens":
        raise RankingError("判定の出力が長すぎて打ち切られました")
    data = json.loads("".join(b.text for b in resp.content if b.type == "text"))
    n_facts = {c["id"]: len(company_facts(c)) for c in companies}
    fits = {cid: [{"fit": 3, "fact": 0} for _ in axes] for cid in ids}      # 抜けた分は中立
    for row in data["fits"]:
        cid = row["company_id"]
        if cid not in fits:
            continue
        for i in range(1, len(axes) + 1):
            cell = row["scores"].get(f"a{i}") or {}
            fit = int(cell.get("score", 3))
            fact = int(cell.get("fact", 0))
            if not 1 <= fact <= n_facts[cid]:      # 存在しない番号は「根拠なし」にする
                fact = 0
            fits[cid][i - 1] = {"fit": fit, "fact": fact}
    return fits


# ---------------------------------------------------------------- ランキング

def rank(axes: list[str], result: dict, top_n: int = TOP_N, client=None, model: str = MODEL,
         companies: list[dict] | None = None, fits: dict | None = None, lang: str = "ja") -> dict:
    """アンケートの結果から、企業のランキングを作る。

    axes:   個人軸の名前の一覧
    result: survey.make_result() の戻り値（questions / answers / weights / job_axes）
    """
    companies = companies if companies is not None else load_companies()
    client = client or anthropic.Anthropic(max_retries=4)

    questions = result["questions"]
    weights = result["weights"]
    axis_qids = [q["id"] for q in questions if q["source"] == "job_axis"]
    job_axes = result.get("job_axes") or axes
    if len(axis_qids) != len(job_axes):
        raise RankingError("個人軸の数と、アンケートの項目の数が合いません")

    common = score_common(companies)
    en = lang == "en"
    quote = (lambda a: f"“{a}”") if en else (lambda a: f"「{a}」")      # 軸の名前を囲む記号
    must = [m for m in (result.get("must_have") or [])]
    qname = {q["id"]: q["name"] for q in questions}
    must_labels = [(quote(job_axes[axis_qids.index(m)]) if m in axis_qids else qname.get(m, m)) for m in must if m in qname]
    if fits is None:      # 軸の判定が渡されていなければ、保存済みの事実から、AIに判定させる
        fits = judge_axes(job_axes, companies, client, model)

    rows = []
    for c in companies:
        facts = company_facts(c)
        contribs, total = [], 0.0
        for q in questions:
            w = float(weights.get(q["id"], 0.0))
            if q["source"] == "job_axis":
                i = axis_qids.index(q["id"])
                cell = fits[c["id"]][i]
                fit = cell["fit"]
                if "basis" in cell:      # パイプラインの判定：根拠の文章と出典URLが、判定に付いている
                    basis, url = cell["basis"], cell.get("url", "")
                    fact = {"fact": basis, "url": url} if basis and url else None
                else:                    # 事実の番号で返される判定
                    fact = facts[cell["fact"] - 1] if cell["fact"] else None
                    basis, url = (fact["fact"], fact["url"]) if fact else ("", "")
                if fact is None:
                    basis, url = ("No fact was found to judge this, so the neutral score of 3 is used." if en
                                  else "判断できる事実が見つからなかったため、中立の3点"), ""
                s, unknown, display = (fit - 1) / 4, fact is None, f"{fit}/5"
                label = quote(job_axes[i])
            else:
                info = common[c["id"]].get(q["id"])
                if info is None:      # 企業のデータにない項目は、計算に入れない
                    continue
                s, unknown, display, url, basis = (info["score"], info["unknown"], info["display"],
                                                   info["url"], info["basis"])
                label = q["name"]
            total += w * s
            contribs.append({"qid": q["id"], "label": label, "weight": w, "score": s, "unknown": unknown, "display": display,
                             "url": url, "basis": basis, "is_axis": q["source"] == "job_axis"})

        # 「合うところ」「気になるところ」は、根拠のある項目から選ぶ
        # 譲れない条件：満たさない項目の一覧（根拠がない項目も「満たさない」）
        by_qid = {x["qid"]: x for x in contribs}
        failed = []
        for qid in must:
            x = by_qid.get(qid)
            if x is None:
                continue
            if x["unknown"]:
                failed.append({"label": x["label"], "reason": "No evidence found" if en else "根拠が見つからず、確認できない"})
            elif x["score"] < MUST_MIN:
                failed.append({"label": x["label"], "reason": f"{x['display']}; needs 4 or higher" if en else f"{x['display']}で、4点以上が必要"})

        known = [x for x in contribs if not x["unknown"]]
        strengths = sorted((x for x in known if x["score"] >= STRENGTH_MIN),
                           key=lambda x: x["weight"] * x["score"], reverse=True)[:3]
        concerns = sorted((x for x in known if x["score"] <= CONCERN_MAX),
                          key=lambda x: x["weight"] * (1 - x["score"]), reverse=True)[:2]
        fmt = lambda x: {"label": x["label"], "detail": x["display"], "basis": x["basis"], "url": x["url"]}
        rows.append({
            "id": c["id"], "name": c["name"], "industry": c.get("industry", ""),
            "name_en": c.get("name_en", ""), "industry_en": c.get("industry_en", ""),
            "score": round(total * 100, 1),
            "strengths": [fmt(x) for x in strengths], "concerns": [fmt(x) for x in concerns],
            "unknown_count": sum(1 for x in contribs if x["unknown"] and not x["is_axis"]),
            "sources": [u for u in [c.get("profile_url", "")] + list(c.get("sources") or []) if u][:3],
            "profile": c.get("profile", ""), "failed": failed,
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    excluded = [{"name": r["name"], "name_en": r["name_en"], "failed": r["failed"]} for r in rows if r["failed"]]
    rows = [r for r in rows if not r["failed"]]          # 譲れない条件を、すべて満たした企業だけを順位づけする
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    dates = sorted(c["collected_at"] for c in companies if c.get("collected_at") and not c.get("dummy"))
    return {
        "dummy": all(c.get("dummy") for c in companies),     # ダミーデータだけで計算したか
        "top": rows[:top_n],
        "others": [{"rank": r["rank"], "name": r["name"], "name_en": r["name_en"], "score": r["score"]} for r in rows[top_n:]],
        "companies_count": len(companies),
        "axes": job_axes, "lang": lang,
        "screening": {"labels": must_labels, "total": len(companies),
                      "passed": len(rows), "excluded": excluded},
        "collected_from": dates[0] if dates else "", "collected_to": dates[-1] if dates else "",
    }


def format_text(ranking: dict) -> str:
    nl = chr(10)
    when = "ダミーデータ" if ranking.get("dummy") else f"データ取得日: {ranking['collected_from']}〜{ranking['collected_to']}"
    lines = [f"対象 {ranking['companies_count']}社 / 就活軸: {'、'.join(ranking['axes'])} / {when}", ""]
    for r in ranking["top"]:
        lines.append(f"{r['rank']}位  {r['name']}  {r['score']}点  （{r['industry']}）  根拠なし {r['unknown_count']}項目")
        lines += [f"    ○ {x['label']}（{x['detail']}）" for x in r["strengths"]]
        lines += [f"    △ {x['label']}（{x['detail']}）" for x in r["concerns"]]
    if ranking["others"]:
        lines += ["", "ほか: " + "、".join(f"{o['rank']}位 {o['name']}（{o['score']}）" for o in ranking["others"])]
    return nl.join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        raise SystemExit("使い方: python ranking.py data/<保存したアンケート結果>.json")
    sys.path.insert(0, str(ROOT))
    from server import check_api_key
    check_api_key()
    saved = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(format_text(rank(saved["axes"], saved["survey"])))
