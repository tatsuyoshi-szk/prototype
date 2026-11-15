"""合う企業を探すパイプライン。ユーザーが使うたびに実行する（保存済みのデータは使わない）。

  1. メインエージェント（Opus 5.5）が、その人の就活軸に合う実在の企業を15社選ぶ（軸の名前だけを渡す。会話の内容は渡さない）
  2. サブエージェント（Sonnet 5.5）が、Web検索・Web取得で、公開情報を調べる（事実と出典URLだけを集める）。
     既定は1社に1体（15体を並列）。SUB_BATCH を 7 にすると、3体で7社ずつになる
  3. メインエージェントが、集まった事実だけをもとに、採点基準（companies/rubric.yaml）で共通14項目を採点し、
     個人の軸にどのくらい合うかも1〜5で判定する（根拠の文章と出典URLつき）

重み付けと順位づけ（ranking.rank）は、この結果を使って行う。
調査（1〜3）は、アンケートが終わってから始める。「譲れない条件」で、先に保存したデータベース（cache/）の企業を絞り込み、
15社に足りないぶんだけを、Webから集める（run_research）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import anthropic
import yaml

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"            # 調べた企業の結果の保存先（企業ごとに1ファイル）
CACHE_DAYS = 90                       # この日数を過ぎたら、調べ直す
RUBRIC_PATH = ROOT / "companies" / "rubric.yaml"

MAIN_MODEL = "claude-opus-5-5"        # 企業の選定と採点（メインエージェント）
SUB_MODEL = "claude-sonnet-5-5"       # Webでの調査（サブエージェント）
FALLBACK_BETA = "server-side-fallback-2026-07-01"
SUB_EFFORT = "medium"                 # サブエージェントの考える量（low だと、調べずに終えてしまった）
SCORE_EFFORT = "low"
N_COMPANIES = 15
SUB_BATCH = 1                        # サブエージェント1体が調べる企業の数（1 = 1社ずつ15体を並列。7にすると、3体×7社）
SEARCH_PER_COMPANY = 5                # 1社あたりの、Web検索の回数の上限（時間と費用の安全装置）
FETCH_PER_COMPANY = 6                 # 1社あたりの、ページ取得の回数の上限
FETCH_MAX_TOKENS = 8000               # 1ページの取得で、読み込む文章の上限（長いページを丸ごと読まない）
MAX_RESUMES = 8                       # 長い調査が止まる（pause_turn）たびに再開する、最大の回数
SCORE_WORKERS = 15                   # 採点は全社を同時に行う

IDS = ("foreign_staff_ratio foreign_manager_ratio evaluation_system english_selection required_japanese "
       "multilingual_docs visa_support living_support community_erg culture_religion home_leave "
       "global_offices global_review_score foreigner_reviews").split()
NO_BASIS = "公開情報から確認できなかったため、基準どおり低い点（言及なし）"
NO_BASIS_EN = "Not confirmed in public information, so scored low per the rubric (no mention found)."


class PipelineError(RuntimeError):
    """企業を探す途中で、続けられなくなったとき。画面に出してよい文言を持つ。"""


def load_rubric() -> list[dict]:
    return yaml.safe_load(RUBRIC_PATH.read_text(encoding="utf-8"))["items"]


def rubric_text(rubric: list[dict]) -> str:
    nl = chr(10)
    return nl.join(
        f"- {r['id']}（{r['qid']} {r['name']}）：" + " / ".join(f"{k}点={v}" for k, v in r["levels"].items())
        for r in rubric)


def _is_http(u) -> bool:
    return isinstance(u, str) and u.startswith(("http://", "https://"))


# ---------------------------------------------------------------- 共通：構造化出力

def structured(client, model: str, prompt: str, schema: dict, effort: str = "medium", max_tokens: int = 16000) -> dict:
    """JSONスキーマに合う出力を1回で受け取る（メインエージェント用。Webは使わない）。"""
    kwargs = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    for attempt in range(2):
        try:
            resp = client.beta.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                **kwargs)
            break
        except anthropic.BadRequestError as e:
            if attempt == 0 and "fallback" in str(e).lower():
                kwargs = {}
                continue
            raise
    if resp.stop_reason == "refusal":
        raise PipelineError("モデルが応答を拒否しました")
    if resp.stop_reason == "max_tokens":
        raise PipelineError("出力が長すぎて打ち切られました")
    return json.loads("".join(b.text for b in resp.content if b.type == "text"))


# ---------------------------------------------------------------- 1. 企業を選ぶ（メイン）

def select_companies(axes: list[str], client, model: str = MAIN_MODEL, n: int = N_COMPANIES,
                     avoid: list[str] | None = None, conditions: list[str] | None = None) -> list[dict]:
    avoid_text = ("\n\n# 選ばない企業（すでに調査済み）\n" + "、".join(avoid)) if avoid else ""
    if conditions:
        avoid_text += "\n\n# 譲れない条件（必ず満たす企業を選ぶ）\n" + chr(10).join(f"- {c}" for c in conditions)
    axes_text = chr(10).join(f"- {a}" for a in axes)
    prompt = f"""日本で就職活動をしている外国人留学生（新卒）の「就活軸」を渡します。
この留学生に合いそうな、**実在する**日本の企業（日本法人・外資系の日本法人を含む）を {n} 社選んでください。

# 選び方
- 日本で新卒採用をしていて、外国人留学生が応募できる（応募してきた実績がある）企業。
- 就活軸のそれぞれに合う企業が、ある程度含まれるようにする。同じ業界は、多くても4社まで。大企業だけに偏らない。
- 実在が確かな企業だけを選ぶ。名前を作らない。正式な日本語の企業名で書く（例：「トヨタ自動車」）。
- id は、英小文字・数字・アンダースコアだけの短い名前（例：toyota）。{n}社の中で重複させない。
- name_en は、その企業の一般的な英語表記（例：Toyota Motor）、industry_en は、業界の英語名（例：Automotive）。

# 就活軸
{axes_text}{avoid_text}"""
    row = {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                                            "industry": {"type": "string"}, "name_en": {"type": "string"},
                                            "industry_en": {"type": "string"}},
           "required": ["id", "name", "industry", "name_en", "industry_en"], "additionalProperties": False}
    schema = {"type": "object", "properties": {"companies": {"type": "array", "items": row}},
              "required": ["companies"], "additionalProperties": False}
    data = structured(client, model, prompt, schema, effort="low", max_tokens=4000)
    out, seen_id, seen_name = [], set(), set()
    for c in data["companies"]:
        cid = re.sub(r"[^a-z0-9_]", "", (c["id"] or "").lower())
        name = (c["name"] or "").strip()
        if not cid or not name or cid in seen_id or name in seen_name:
            continue
        seen_id.add(cid); seen_name.add(name)
        out.append({"id": cid, "name": name, "industry": (c["industry"] or "").strip(),
                    "name_en": (c.get("name_en") or "").strip(), "industry_en": (c.get("industry_en") or "").strip()})
    if len(out) < 1:
        raise PipelineError("企業を選べませんでした")
    return out[:n]


# ---------------------------------------------------------------- 調べた結果の保存（企業ごとに1ファイル）
# 企業の公開情報は、ユーザーが誰でも同じなので、一度調べた企業は、期限（CACHE_DAYS）まで使い回す。
# 保存するのは、企業の公開情報（事実と出典URL）だけ。ユーザーの情報は入らない。

_cache_lock = threading.Lock()


def _norm_name(name: str) -> str:
    n = unicodedata.normalize("NFKC", name or "").lower()
    return re.sub(r"(株式会社|\(株\)|㈱|\s|・)", "", n)


def _cache_path(name: str) -> Path:
    return CACHE_DIR / (hashlib.sha1(_norm_name(name).encode("utf-8")).hexdigest()[:16] + ".json")


def load_cached(name: str, today: date | None = None) -> dict | None:
    """保存済みの調査結果を返す（なければ、期限切れ・壊れていれば None）。"""
    path = _cache_path(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved = date.fromisoformat(data["collected_at"])
        ev = data["evidence"]
        if _norm_name(data["name"]) != _norm_name(name) or not isinstance(ev.get("items"), dict):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if (today or date.today()) - saved > timedelta(days=CACHE_DAYS):
        return None
    return {**ev, "collected_at": data["collected_at"]}


def _informative(ev: dict) -> bool:
    """保存する価値があるか（ほとんど何も見つからなかった結果は、保存せず、次回また調べる）。"""
    backed = sum(1 for it in ev["items"].values() if it["source_url"] and not it["finding"].startswith("未確認"))
    return backed >= 2 or len(ev["axis_facts"]) >= 3


def save_cached(ev: dict) -> None:
    if not _informative(ev):
        return
    CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(ev["name"])
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    payload = {"name": ev["name"], "collected_at": ev.get("collected_at") or date.today().isoformat(), "evidence": ev}
    with _cache_lock:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)          # 書き込み途中のファイルを、読まれないようにする


def list_cached(today: date | None = None) -> list[dict]:
    """保存してあるデータベース（cache/）の、期限内の企業を、すべて返す（企業ごとの調査結果）。"""
    out = []
    for path in sorted(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            saved, ev = date.fromisoformat(data["collected_at"]), data["evidence"]
            if not isinstance(ev.get("items"), dict) or not ev.get("name"):
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if (today or date.today()) - saved <= timedelta(days=CACHE_DAYS):
            out.append({**ev, "collected_at": data["collected_at"], "scores": data.get("scores")})
    return out


def save_scores(name: str, items: dict) -> None:
    """採点した共通項目の点数を、データベース（その企業の保存ファイル）に記録する。保存ファイルがなければ、何もしない。
    記録するのは、点数と「根拠なし」かどうかだけ（言語に依存しない）。次回、譲れない条件での絞り込みに使う。"""
    path = _cache_path(name)
    with _cache_lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["scores"] = {"scored_at": date.today().isoformat(),
                              "items": {iid: {"score": int(it["score"]), "unconfirmed": bool(it["unconfirmed"])}
                                        for iid, it in items.items()}}
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
        except (OSError, ValueError, KeyError, TypeError):
            return


MUST_SCORE = 4          # 「譲れない」項目は、この点以上で、根拠があることが必要（ranking.MUST_MIN = 0.75 と同じ）


def meets_must(ev: dict, must_ids: list[str]) -> bool:
    """データベースの企業が、「譲れない」共通項目をすべて満たすか。
    記録した点数があれば、それで確かめる（4点以上で、根拠あり）。まだ採点していない企業は、出典つきの事実があるかだけを見る。"""
    scored = ((ev.get("scores") or {}).get("items")) or {}
    for iid in must_ids:
        if iid in scored:
            sc = scored[iid]
            if sc.get("unconfirmed") or sc.get("score", 0) < MUST_SCORE:
                return False
            continue
        it = (ev.get("items") or {}).get(iid) or {}
        if not it.get("source_url") or str(it.get("finding", "")).startswith("未確認"):
            return False
    return True


def pick_from_db(axes: list[str], pool: list[dict], n: int, conditions: list[str], client,
                 model: str = MAIN_MODEL) -> list[dict]:
    """データベースで条件に合った企業が n 社より多いとき、就活軸に合う n 社を選ぶ。"""
    if len(pool) <= n:
        return list(pool)
    nl = chr(10)
    listing = nl.join(f"{i}. {c['name']}（{c.get('industry', '')}）{(c.get('profile') or '')[:60]}" for i, c in enumerate(pool))
    cond = ("\n\n# 譲れない条件\n" + nl.join(f"- {c}" for c in conditions)) if conditions else ""
    axes_text = nl.join(f"- {a}" for a in axes)
    prompt = f"""日本で就職活動をしている外国人留学生（新卒）の「就活軸」を渡します。
下の企業の一覧（番号つき）から、この留学生に合いそうな企業を {n} 社選び、番号を返してください。
就活軸のそれぞれに合う企業が含まれるようにする。同じ業界は、多くても4社まで。一覧にない番号は返さない。

# 就活軸
{axes_text}{cond}

# 企業の一覧
{listing}"""
    schema = {"type": "object", "properties": {"picks": {"type": "array", "items": {"type": "integer"}}},
              "required": ["picks"], "additionalProperties": False}
    data = structured(client, model, prompt, schema, effort="low", max_tokens=2000)
    seen, out = set(), []
    for i in data["picks"]:
        if isinstance(i, int) and 0 <= i < len(pool) and i not in seen:
            seen.add(i)
            out.append(pool[i])
    for i, c in enumerate(pool):          # 足りないぶんは、一覧の順で補う
        if len(out) >= n:
            break
        if i not in seen:
            out.append(c)
    return out[:n]


# ---------------------------------------------------------------- 2. Webで調べる（サブエージェント）

def _research_prompt(batch: list[dict], axes: list[str], rubric: list[dict]) -> str:
    nl = chr(10)
    companies = nl.join(f"{i}. {c['name']}（id: {c['id']}）" for i, c in enumerate(batch, 1))
    axes_text = nl.join(f"- {a}" for a in axes)
    item_ids = ", ".join(IDS)
    n = len(batch)
    search_cap, fetch_cap = SEARCH_PER_COMPANY * n, FETCH_PER_COMPANY * n
    return f"""あなたは企業の公開情報を集める調査担当です。点数はつけません（点数は別の担当がつけます）。
あなたの仕事は、「事実と出典URL」を集めることだけです。

# 担当企業（{len(batch)}社）
{companies}

# 調べる内容
日本で新卒就職する外国人留学生にとっての、その企業の「グローバル度・外国人の働きやすさ」です。
次の14項目の採点基準があります。各項目について、この基準で点数をつけられるだけの「事実」を集めます（点数そのものは書かない）。
{rubric_text(rubric)}

さらに、**就活軸の判定に使う事実（axis_facts）**を集めます。就活軸は次のとおりです。
{axes_text}
各軸に合うか合わないかの判断材料になる事実（具体的な数字・制度名・拠点・事業内容など）を、1社あたり6〜10個。
この結果は、別の就活軸の人にも使い回すので、軸に直接関係する事実に加えて、一般的な判断材料（初任給・年収、海外拠点と赴任、新規事業・社内起業の制度、若手の裁量・昇進、事業の中心、研修・成長支援、働き方）も含める。

# 調べ方（時間が限られているので、この手順で、**並列に**進める）
- 複数の検索・取得は、**1回のターンで同時に（並列に）呼び出す**。企業ごとに1つずつ順番に調べない。
- 手順：
  1. 担当の企業の検索を、同時に行う（企業ごとに、2〜3種類の検索語）（例：「<企業名> 新卒採用 外国人留学生 英語 日本語」「<企業名> 統合報告書 外国籍 管理職 比率 海外拠点」など）。
  2. 検索結果の中から、公式の採用ページ・サステナビリティ（ダイバーシティ）ページ・IR資料のURLを選び、同時に取得する（1社あたり、2〜3ページまで）。
  3. まだ「未確認」の重要な項目（外国籍の割合、外国籍の管理職、海外拠点、英語での選考、日本語要件、ビザ支援）があれば、それを埋める検索・取得を、もう1〜2回、同時に行う。
  4. JSONを書いて終える。全体で、検索は{search_cap}回まで、ページ取得は{fetch_cap}回まで。3〜4ラウンドで終えること。
- 優先する出典：企業の採用サイト、統合報告書・サステナビリティレポート・IR資料、公式のプレスリリース、有価証券報告書。
- 口コミサイト（Glassdoor・Indeed・OpenWork など）は、ログインが必要で開けないので、見に行かない（global_review_score と foreigner_reviews は「未確認」にする）。

# 守ること
- 記憶や推測で書かない。検索・取得で見つけた内容だけを書く。見つからなければ、その項目の finding は「未確認」にする。数字を勝手に丸めたり、作ったりしない。
- 事実ごとに、その内容が書かれていたページのURL（出典）を付ける。URLを推測で作らない。
- ページの本文を取得して読んだ内容は、そのまま書く。検索結果に表示された文章（抜粋）だけが根拠のときは、finding の末尾に「（検索結果の抜粋）」と書き、そのページのURLを付ける。
- 事実の文章は、出典に書いてある内容を、短く（1〜2文）まとめる。年度や調査時点、範囲（国内だけ・連結など）も書く。
- 見つからない項目を、探し続けない。「未確認」でよい。

# 出力
最後のメッセージには、次の形のJSONだけを書く（前後に説明を書かない）。担当の全社を入れる。
{{"companies": [
  {{"id": "担当企業のid", "name": "企業名", "industry": "業界",
    "profile": "事業内容、海外展開、外国人の働きやすさの特徴を、200字以内で（出典に基づく）",
    "profile_url": "https://...",
    "global_offices_list": ["開いたページで確認できた、海外拠点のある国・地域（なければ空の配列）"],
    "items": {{"項目id": {{"finding": "事実を短く。なければ「未確認」", "source_url": "https://...（なければ空文字）"}}}},
    "axis_facts": [{{"fact": "具体的な事実", "source_url": "https://..."}}]
  }}
]}}
items には、次の14個の項目idをすべて入れる：{item_ids}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _run_subagent(client, prompt: str, model: str = SUB_MODEL, n_companies: int = 1) -> dict:
    """サブエージェントを1体動かし、最後のJSONを返す。Webツールの長い処理が止まる（pause_turn）たびに再開する。"""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCH_PER_COMPANY * n_companies},
             {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": FETCH_PER_COMPANY * n_companies,
              "max_content_tokens": FETCH_MAX_TOKENS}]
    user = {"role": "user", "content": prompt}
    carried: list[dict] = []          # これまでの assistant の出力。再開のときは、1つの assistant メッセージにまとめて送り直す
    for _ in range(MAX_RESUMES + 3):
        messages = [user] + ([{"role": "assistant", "content": carried}] if carried else [])
        with client.messages.stream(model=model, max_tokens=32000, tools=tools, messages=messages,
                                    output_config={"effort": SUB_EFFORT}) as stream:
            resp = stream.get_final_message()
        content = [b.model_dump(exclude_none=True) for b in resp.content]
        if resp.stop_reason == "pause_turn":          # 続きを、そのまま送り直す（「続けて」とは書かない）
            carried = carried + content
            continue
        if resp.stop_reason == "refusal":
            raise PipelineError("調査担当が応答を拒否しました")
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return _extract_json(text)
        except ValueError:                            # JSONになっていない（途中で切れた、など）：出し直させる（最大2回）
            if resp.stop_reason == "max_tokens" and not text:
                raise PipelineError("調査結果の形が正しくありませんでした")
            carried = carried + content
            for _ in range(2):
                messages = [user, {"role": "assistant", "content": carried},
                            {"role": "user", "content": "JSONだけを、もう一度、最後のメッセージに書いてください（説明は書かない）。"
                             "「companies」の配列に、担当の全社を入れ、各社の items には14個の項目idをすべて入れること。"}]
                with client.messages.stream(model=model, max_tokens=32000, tools=tools, messages=messages,
                                            output_config={"effort": SUB_EFFORT}) as stream:
                    resp = stream.get_final_message()
                content = [b.model_dump(exclude_none=True) for b in resp.content]
                try:
                    return _extract_json("".join(b.text for b in resp.content if b.type == "text"))
                except ValueError:
                    carried = carried + content
            raise PipelineError("調査結果の形が正しくありませんでした")
    raise PipelineError("調査が終わりませんでした")


def _clean_evidence(raw: dict, batch: list[dict]) -> list[dict]:
    """サブエージェントの出力を整える（担当外の企業・URLでないものを捨て、足りない項目は「未確認」で埋める）。"""
    wanted = {c["id"]: c for c in batch}
    out = []
    for c in raw.get("companies", []):
        cid = c.get("id")
        if cid not in wanted:
            continue
        items = {}
        for iid in IDS:
            it = (c.get("items") or {}).get(iid) or {}
            url = it.get("source_url", "")
            items[iid] = {"finding": str(it.get("finding") or "未確認"), "source_url": url if _is_http(url) else ""}
        out.append({
            "id": cid, "name": wanted[cid]["name"], "industry": c.get("industry") or wanted[cid]["industry"],
            "name_en": wanted[cid].get("name_en", ""), "industry_en": wanted[cid].get("industry_en", ""),
            "collected_at": date.today().isoformat(),
            "profile": str(c.get("profile") or ""),
            "profile_url": c.get("profile_url") if _is_http(c.get("profile_url")) else "",
            "global_offices_list": [str(x) for x in (c.get("global_offices_list") or [])][:60],
            "items": items,
            "axis_facts": [{"fact": str(a["fact"]), "source_url": a.get("source_url", "")}
                           for a in (c.get("axis_facts") or [])
                           if isinstance(a, dict) and a.get("fact") and _is_http(a.get("source_url"))][:14],
        })
    return out


# ---------------------------------------------------------------- 3. 採点する（メイン）

SCORE_FORMAT = """# 出力
次の形のJSONだけを書く（前後に説明を書かない）。items には14個の項目idすべて、axes には a1 から軸の数ぶんすべてを入れる。
{"items": {"項目id": {"score": 1〜5の整数, "evidence_found": true か false, "basis": "根拠の文章（なければ空文字）", "source_url": "出典URL（なければ空文字）"}},
 "axes":  {"a1": {"fit": 1〜5の整数, "evidence_found": true か false, "basis": "根拠の文章（なければ空文字）", "source_url": "出典URL（なければ空文字）"}}}"""


def _text_json(client, model: str, prompt: str, effort: str, max_tokens: int = 12000) -> dict:
    """JSONを文章で出させて、読み取る（形が壊れていたら、1回だけやり直す）。スキーマは使わない（大きいと拒否されるため）。"""
    for attempt in range(2):
        resp = client.messages.create(model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}],
                                      output_config={"effort": effort})
        if resp.stop_reason == "refusal":
            raise PipelineError("モデルが応答を拒否しました")
        try:
            return _extract_json("".join(b.text for b in resp.content if b.type == "text"))
        except ValueError:
            if attempt == 1:
                raise PipelineError("採点の形が正しくありませんでした")


def _cell(data: dict, section: str, key: str, score_name: str) -> dict:
    """採点結果の1項目分を、型を確かめて取り出す（壊れていたら「根拠なし」にする）。"""
    c = ((data.get(section) or {}).get(key)) or {}
    try:
        score = int(c.get(score_name))
    except (TypeError, ValueError):
        score = 0
    ok = bool(c.get("evidence_found")) and 1 <= score <= 5
    return {"score": score if ok else 0, "ok": ok, "basis": str(c.get("basis") or "").strip(),
            "url": str(c.get("source_url") or "").strip()}


def _allowed_urls(ev: dict) -> set[str]:
    urls = {ev.get("profile_url", "")} | {it["source_url"] for it in ev["items"].values()}
    urls |= {a["source_url"] for a in ev["axis_facts"]}
    return {u for u in urls if u}


def score_company(ev: dict, axes: list[str], rubric: list[dict], client, model: str = MAIN_MODEL,
                  lang: str = "ja") -> tuple[dict, list[dict]]:
    """1社分を採点する。戻り値は (企業のデータ, 軸の判定 [{fit, fact, basis, url}])。"""
    nl = chr(10)
    lines = []
    for iid in IDS:
        it = ev["items"][iid]
        lines.append(f"- {iid}: {it['finding']}（出典: {it['source_url'] or 'なし'}）")
    facts = nl.join(f"- {a['fact']}（出典: {a['source_url']}）" for a in ev["axis_facts"]) or "- （なし）"
    offices = "、".join(ev["global_offices_list"]) or "（確認できた国名の一覧なし）"
    axes_text = nl.join(f"a{i}: {a}" for i, a in enumerate(axes, 1))
    lang_note = ("\n- 言語：basis は、**英語**で書く（短く、やさしい英語。日本語の事実は、英語に訳してまとめる）。数字と出典URLは、そのまま。末尾の注記も英語にする（「（検索結果の抜粋）」は「(search result excerpt)」、「二次情報」は「(secondary info)」）。"
                 if lang == "en" else "")
    prompt = f"""あなたは、企業のグローバル度を採点する担当です。調査担当が集めた「事実と出典URL」だけをもとに、採点してください。

# 採点基準（共通14項目。1〜5点）
{rubric_text(rubric)}

# 採点のルール
- 根拠にしてよいのは、下の「集まった事実」に書かれていることだけ。企業についての、書かれていない知識で点数をつけない。
- 根拠があるとき：evidence_found を true にし、score を基準に当てはめて決める。basis に根拠（事実の短い要約。範囲が国内だけなら、そのことも）を書き、
  source_url に、その事実の出典URLを、下に書かれたURLから**そのまま**写す。出典のない事実は、根拠にしない。
- 根拠がないとき（「未確認」、出典URLがない、など）：evidence_found を false にし、score は基準の「言及なし・確認できない」に当たる点（多くは1点）、basis と source_url は空文字にする。
- 一部しか確認できなかったとき（例：海外拠点の国が一部しか分からない）は、確認できた範囲で基準に当てはめる。basis に、その範囲を書く。
- 古い情報：根拠が2021年より前の情報だけのときは、基準に当てはめた点から1点下げる（最低1点）。basis に、その年を書く（例：「2015年の情報」）。
  年が書かれていない情報は、そのまま使ってよい。{lang_note}
- 「（検索結果の抜粋）」と書かれた事実は、出典URLがあれば根拠にしてよい。ただし basis の末尾に「（検索結果の抜粋）」と書く。出典URLのない事実、「参考値」とだけ書かれた事実は、根拠にしない。

# 就活軸の判定
各就活軸に、この企業がどのくらい合うかを、fit（1=合わない〜5=とても合う）で判定する。
根拠にするのは、「就活軸の判定に使う事実」「会社の紹介」「海外拠点」「共通項目の事実」に書かれたことだけ。
根拠があるとき：evidence_found を true にし、決め手になった事実を basis に短く書き、その出典URLを source_url に写す。
判断できる事実がないとき：fit は 3、evidence_found は false、basis と source_url は空文字。
{axes_text}

# 集まった事実
企業: {ev['name']}（{ev['industry']}）
会社の紹介: {ev['profile'] or '（なし）'}（出典: {ev['profile_url'] or 'なし'}）
海外拠点がある国・地域: {offices}

共通項目の事実:
{nl.join(lines)}

就活軸の判定に使う事実:
{facts}"""
    data = _text_json(client, model, prompt + chr(10) * 2 + SCORE_FORMAT, SCORE_EFFORT)
    allowed = _allowed_urls(ev)

    items = {}
    for iid in IDS:
        cell, src = _cell(data, "items", iid, "score"), ev["items"][iid]
        if cell["ok"] and cell["url"] in allowed and cell["basis"]:
            items[iid] = {"score": cell["score"], "basis": cell["basis"], "source_url": cell["url"],
                          "unconfirmed": False, "finding": src["finding"]}
        else:        # 根拠（出典つきの事実）がないものは、1点・根拠なし
            items[iid] = {"score": 1, "basis": NO_BASIS_EN if lang == "en" else NO_BASIS, "source_url": "",
                          "unconfirmed": True, "finding": src["finding"]}
    fits = []
    for i in range(1, len(axes) + 1):
        cell = _cell(data, "axes", f"a{i}", "fit")
        ok = cell["ok"] and cell["url"] in allowed and bool(cell["basis"])
        fits.append({"fit": cell["score"] if ok else 3, "fact": 0,
                     "basis": cell["basis"] if ok else "", "url": cell["url"] if ok else ""})
    company = {**{k: ev[k] for k in ("id", "name", "industry", "profile", "profile_url", "global_offices_list", "axis_facts")},
               "name_en": ev.get("name_en", ""), "industry_en": ev.get("industry_en", ""),
               "collected_at": ev.get("collected_at") or date.today().isoformat(), "dummy": False, "items": items,
               "sources": [u for u in [ev["profile_url"]] if u]}
    return company, fits


# ---------------------------------------------------------------- 全体

def run_research(axes: list[str], client=None, progress=None, *, main_model: str = MAIN_MODEL,
                 sub_model: str = SUB_MODEL, n_companies: int = N_COMPANIES, avoid: list[str] | None = None,
                 research_only: bool = False, lang: str = "ja", must: list[dict] | None = None) -> dict:
    """企業を集め、採点する。戻り値は {"companies": [...], "fits": {企業id: [...]}, "failed": [...]}。

    must: 「譲れない」項目 [{"qid": 項目id, "label": 表示名}]。
    集め方：① データベース（cache/）の企業を、譲れない共通項目の事実があるものに絞り、n社を選ぶ
            ② 足りないぶんは、Webから集める（メインが企業を選び、サブエージェントが調べる）。最大2回
    research_only のときは、データベースを使わず、Webで調べて保存するだけ（保存を増やすとき）。
    """
    client = client or anthropic.Anthropic(max_retries=4)
    progress = progress or (lambda stage, detail="": None)
    rubric = load_rubric()
    must = must or []
    must_common = [m["qid"] for m in must if m["qid"] in IDS]
    conditions = [m["label"] for m in must]
    failed: list[str] = []

    def research_web(chosen: list[dict]) -> tuple[list[dict], int]:
        """選んだ企業を、Webで調べる（保存があれば、それを使う）。戻り値は（調査結果, 保存を使った数）。"""
        cached, todo = [], []
        for c in chosen:
            hit = load_cached(c["name"])
            if hit:
                cached.append({**hit, "id": c["id"], "name_en": c.get("name_en") or hit.get("name_en", ""),
                               "industry_en": c.get("industry_en") or hit.get("industry_en", "")})
            else:
                todo.append(c)
        batches = [todo[i:i + SUB_BATCH] for i in range(0, len(todo), SUB_BATCH)]
        done_agents = []

        def research(batch):
            try:
                for attempt in range(2):                   # 形が壊れて失敗したときは、1回だけ、その企業を調べ直す
                    try:
                        raw = _run_subagent(client, _research_prompt(batch, axes, rubric), sub_model, len(batch))
                        break
                    except PipelineError:
                        if attempt == 1:
                            raise
                found = _clean_evidence(raw, batch)
                for ev in found:
                    save_cached(ev)
                return found
            except (PipelineError, anthropic.APIError, ValueError) as exc:
                print(f"調査担当の失敗: {type(exc).__name__}: {exc}")
                failed.extend(c["name"] for c in batch)
                return []
            finally:
                done_agents.append(1)
                progress("research", f"{len(done_agents)}/{len(batches)} 件の調査が終わりました")

        if batches:
            progress("research", f"{len(todo)}社をWebで調べています")
            with ThreadPoolExecutor(max_workers=len(batches)) as pool:
                return cached + [e for part in pool.map(research, batches) for e in part], len(cached)
        return cached, len(cached)

    if research_only:      # 調査と保存だけ（採点しない）。保存を増やすときに使う
        progress("select", "あなたの就活軸に合う企業を選んでいます")
        evidence, n_cached = research_web(select_companies(axes, client, main_model, n_companies, avoid))
        if not evidence:
            raise PipelineError("企業の情報を集められませんでした")
        return {"companies": evidence, "fits": {}, "failed": failed, "cached": n_cached, "new": len(evidence) - n_cached}

    # 譲れない条件で、採点した結果を確かめる（共通項目は4点以上・根拠あり、個人軸は判定4以上・根拠あり）
    def unmet_count(company: dict, fits: list[dict]) -> int:
        """満たさない「譲れない」項目の数（0 なら、すべて満たす）。"""
        n = 0
        for m in must:
            if m["qid"] in IDS:
                it = company["items"].get(m["qid"]) or {}
                if it.get("unconfirmed", True) or it.get("score", 0) < MUST_SCORE:
                    n += 1
            elif m.get("axis") is not None and m["axis"] < len(fits):
                f = fits[m["axis"]]
                if not (f.get("basis") and f.get("url")) or f["fit"] < MUST_SCORE:
                    n += 1
        return n

    done_scores = []

    def score(ev):
        try:
            company, fits = score_company(ev, axes, rubric, client, main_model, lang)
            save_scores(ev["name"], company["items"])          # 点数をデータベースに記録する
            return company, fits
        except (PipelineError, anthropic.APIError, ValueError, KeyError) as exc:
            print(f"採点の失敗（{ev['name']}）: {type(exc).__name__}: {exc}")
            failed.append(ev["name"])
            return None
        finally:
            done_scores.append(1)
            progress("score", f"集めた情報を採点しています（{len(done_scores)}社）")

    results: list[tuple[dict, list[dict]]] = []      # 譲れない条件を満たした企業（採点済み）
    rejected: list[tuple[dict, list[dict]]] = []     # 採点したが、条件を満たさなかった企業
    seen_ids: set[str] = set()

    def take(evs: list[dict]) -> None:
        """採点して、譲れない条件を満たす企業だけを、集めた企業に加える。"""
        for e in evs:          # id が重ならないようにする（軸の判定を、id で持つため）
            base, k = e["id"], 2
            while e["id"] in seen_ids:
                e["id"], k = f"{base}{k}", k + 1
            seen_ids.add(e["id"])
        with ThreadPoolExecutor(max_workers=SCORE_WORKERS) as pool:
            scored = [x for x in pool.map(score, evs) if x]
        for company, fits in scored:
            (results if unmet_count(company, fits) == 0 else rejected).append((company, fits))

    # ① データベースから、譲れない条件に合う企業を集める（記録した点数で絞り、選んで、採点して、もう一度確かめる）
    progress("select", "保存したデータベースから、条件に合う企業を探しています")
    db_all = list_cached()
    pool_db = [e for e in db_all if meets_must(e, must_common)]
    for _ in range(3):
        need = n_companies - len(results)
        if need <= 0 or not pool_db:
            break
        picks = pick_from_db(axes, pool_db, need, conditions, client, main_model)
        taken = {e["name"] for e in picks}
        pool_db = [e for e in pool_db if e["name"] not in taken]
        take(picks)

    # ② 足りないぶんは、Webから集める（調べて、採点して、譲れない条件を満たす企業だけを入れる）。最大2回
    tried = [e["name"] for e in db_all]
    for _ in range(2):
        need = n_companies - len(results)
        if need <= 0:
            break
        progress("select", f"データベースに{len(results)}社だけだったので、残り{need}社をWebから探します")
        chosen = select_companies(axes, client, main_model, need, avoid=tried, conditions=conditions)
        tried += [c["name"] for c in chosen]
        found, _ = research_web(chosen)
        take(found)

    need = n_companies - len(results)
    if need > 0 and rejected:
        # 条件をすべて満たす企業が足りないときは、満たさない項目が少ない企業から、足りないぶんを加える
        # （順位づけで、「満たさなかった条件」の印がつき、条件をすべて満たす企業の後ろに並ぶ）
        rejected.sort(key=lambda cf: unmet_count(*cf))
        results += rejected[:need]
    if not results:
        raise PipelineError("企業の情報を集められませんでした")
    return {"companies": [c for c, _ in results], "fits": {c["id"]: f for c, f in results}, "failed": failed}
