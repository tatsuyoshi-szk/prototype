import json, sys, threading, http.client, time, tempfile, pathlib
from types import SimpleNamespace
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "backend"))
import pipeline as P
import server as S
import ranking

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("OK  " if cond else "NG  ") + name)

def block(**d):
    return SimpleNamespace(model_dump=lambda exclude_none=True, d=d: dict(d), **d)

AXES = ["北米で働く", "若いうちに稼ぐ"]
NAMES = [(f"co{i}", f"企業{i}") for i in range(1, 22)]
calls = {"stream": 0, "structured": 0, "tools": None}

class BetaMsgs:
    @staticmethod
    def create(**kw):          # 企業の選定（構造化出力）
        calls["structured"] += 1
        comp = [{"id": i, "name": n, "industry": "業界"} for i, n in NAMES] + [{"id": "co1", "name": "重複", "industry": "x"}]
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"companies": comp}))])

class Msgs:
    seen_msgs = []
    @staticmethod
    def create(**kw):          # 採点（テキストのJSON）
        calls["structured"] += 1
        assert kw["output_config"] == {"effort": P.SCORE_EFFORT} and "format" not in kw["output_config"]
        if True:
            url_ok = "https://example.com/ok"
            cells = {i: {"score": 4, "evidence_found": True, "basis": "根拠", "source_url": url_ok} for i in P.IDS}
            cells["visa_support"] = {"score": 5, "evidence_found": True, "basis": "作ったURL", "source_url": "https://fake.example/x"}   # 許可されないURL
            cells["home_leave"] = {"score": 5, "evidence_found": False, "basis": "", "source_url": ""}
            axes = {f"a{k}": {"fit": 5, "evidence_found": True, "basis": "軸の根拠", "source_url": url_ok} for k in range(1, 3)}
            axes["a2"] = {"fit": 5, "evidence_found": True, "basis": "根拠", "source_url": ""}      # URLなし → 判断できない扱い
            text = json.dumps({"items": cells, "axes": axes})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="結果です " + text)])

    @staticmethod
    def stream(**kw): return Stream(**kw)

class Stream:
    def __init__(self, **kw):
        calls["stream"] += 1; calls["tools"] = kw["tools"]; self.kw = kw
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self):
        msgs = self.kw["messages"]
        Msgs.seen_msgs.append([m["role"] for m in msgs])
        if len(msgs) == 1 or len(msgs[1]["content"]) < 2:      # 1回目・2回目：途中で止まる（2回続けて止まる）
            return SimpleNamespace(stop_reason="pause_turn", content=[block(type="server_tool_use", id=f"x{len(msgs)}{len(msgs[-1]['content']) if len(msgs) > 1 else 0}", name="web_search", input={"query": "q"})])
        ids = [c[0] for c in NAMES if f"id: {c[0]}）" in self.kw["messages"][0]["content"]]
        comps = [{"id": cid, "name": "x", "industry": "y", "profile": "紹介", "profile_url": "https://example.com/ok",
                  "global_offices_list": ["米国"],
                  "items": {i: {"finding": "事実", "source_url": "https://example.com/ok"} for i in P.IDS[:3]},
                  "axis_facts": [{"fact": "f", "source_url": "https://example.com/ok"}, {"fact": "bad", "source_url": "javascript:alert(1)"}]}
                 for cid in ids] + [{"id": "someone_else", "items": {}}]
        text = "説明です\n```json\n" + json.dumps({"companies": comps}) + "\n```"
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text, model_dump=lambda exclude_none=True: {"type": "text", "text": text})])

client = SimpleNamespace(beta=SimpleNamespace(messages=BetaMsgs), messages=Msgs)

P.CACHE_DIR = pathlib.Path(tempfile.mkdtemp())      # 本物の backend/cache を汚さない
stages = []
res = P.run_research(AXES, client, progress=lambda st, d="": stages.append(st))
check("企業は15社（重複は除かれ、多すぎる分は切る）", len(res["companies"]) == 15)
check("サブエージェントは1社に1体（15体×3回のstream=45回）", calls["stream"] == 45)
check("再開しても、assistant は1つにまとめて送る（連続させない）", all(r in (["user"], ["user", "assistant"]) for r in Msgs.seen_msgs))
check("Webツールが渡っている（search/fetch, max_uses）", [t["type"] for t in calls["tools"]] == ["web_search_20250305", "web_fetch_20250910"] and calls["tools"][0]["max_uses"] == P.SEARCH_PER_COMPANY and calls["tools"][1]["max_uses"] == P.FETCH_PER_COMPANY and calls["tools"][1]["max_content_tokens"] == P.FETCH_MAX_TOKENS)
check("採点はメインのモデルで、15回＋選定1回", calls["structured"] == 16)
check("進み具合: select→research→score", stages[0] == "select" and "research" in stages and stages[-1] == "score")
c = res["companies"][0]
check("根拠ありの項目は、点数と出典URLがつく", c["items"]["foreign_staff_ratio"]["score"] == 4 and c["items"]["foreign_staff_ratio"]["source_url"] == "https://example.com/ok" and not c["items"]["foreign_staff_ratio"]["unconfirmed"])
check("集めた事実にないURLを使った採点は、1点・根拠なし", c["items"]["visa_support"]["score"] == 1 and c["items"]["visa_support"]["unconfirmed"])
check("evidence_found=false は、1点・根拠なし", c["items"]["home_leave"]["score"] == 1 and c["items"]["home_leave"]["unconfirmed"])
f = res["fits"][c["id"]]
check("軸の判定：根拠ありは fit と出典", f[0]["fit"] == 5 and f[0]["url"] == "https://example.com/ok")
check("軸の判定：URLなしは中立3・根拠なし", f[1]["fit"] == 3 and f[1]["basis"] == "")
check("URLでない出典（javascript:）は捨てる", all(a["source_url"].startswith("http") for a in c["axis_facts"]) and len(c["axis_facts"]) == 1)

n_files = len(list(P.CACHE_DIR.glob("*.json")))
check("調べた15社が、企業ごとにファイルへ保存される", n_files == 15)
before = (calls["stream"], calls["structured"])
res2 = P.run_research(AXES, client, progress=lambda st, d="": None)
check("2回目は、調査（Web）をしない（streamが増えない）", calls["stream"] == before[0] and len(res2["companies"]) == 15)
check("2回目も、採点はやり直す（メインの呼び出しが増える）", calls["structured"] == before[1] + 16)
check("保存結果を使っても、出典URLつきの採点ができる", res2["companies"][0]["items"]["foreign_staff_ratio"]["source_url"] == "https://example.com/ok")
check("名前の表記ゆれ（株式会社・空白）でも同じ企業として探せる", P.load_cached("　企業１ ") is not None or P.load_cached("株式会社企業1") is not None)
check("期限（90日）を過ぎたら使わない", P.load_cached("企業1", today=__import__("datetime").date.today() + __import__("datetime").timedelta(days=P.CACHE_DAYS + 1)) is None)
bad = list(P.CACHE_DIR.glob("*.json"))[0]; bad.write_text("{壊れたファイル", encoding="utf-8")
check("壊れた保存ファイルは、無視して調べ直す", P.load_cached(json.loads(json.dumps("x"))) is None)
P.save_cached({"name": "空の企業", "items": {i: {"finding": "未確認", "source_url": ""} for i in P.IDS}, "axis_facts": []})
check("何も見つからなかった結果は、保存しない", P.load_cached("空の企業") is None)

# ---- 形が壊れたときのやり直し
class BadFmt:
    n = 0
    def __init__(self, **kw): self.kw = kw
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self):
        BadFmt.n += 1
        text = "これは説明だけです" if BadFmt.n < 3 else json.dumps({"companies": []})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text, model_dump=lambda exclude_none=True, t=text: {"type": "text", "text": t})])
r = P._run_subagent(SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: BadFmt(**kw))), "p")
check("形が壊れていても、最大2回、出し直させて取り出せる", r == {"companies": []} and BadFmt.n == 3)
BadFmt.n = -10
try:
    P._run_subagent(SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: BadFmt(**kw))), "p"); ok_fail = False
except P.PipelineError:
    ok_fail = True
check("3回とも壊れていたら、PipelineError", ok_fail)

# ---- ranking に流す
result = {"questions": [{"id": i, "name": i, "source": "common"} for i in P.IDS] +
          [{"id": "job_axis_1", "name": "軸1", "source": "job_axis"}, {"id": "job_axis_2", "name": "軸2", "source": "job_axis"}],
          "weights": {}, "job_axes": AXES, "must_have": ["visa_support", "job_axis_1"]}
answers = {q["id"]: 3 for q in result["questions"]}
result["answers"] = answers; result["weights"] = {k: round(1 / len(answers), 4) for k in answers}
rk = ranking.rank(AXES, result, companies=res["companies"], fits=res["fits"])
check("譲れない条件(ビザ=根拠なし)で、全社除外", rk["top"] == [] and rk["screening"]["passed"] == 0 and len(rk["screening"]["excluded"]) == 15)
result["must_have"] = ["job_axis_1", "foreign_staff_ratio"]
rk = ranking.rank(AXES, result, companies=res["companies"], fits=res["fits"])
check("譲れない条件(根拠あり4点)で、15社が残る", rk["screening"]["passed"] == 15 and len(rk["top"]) == 5)
check("理由にURL", any(x["url"].startswith("https://example.com") for x in rk["top"][0]["strengths"]))

# ---- サーバー：会話が終わると調査が始まり、アンケート後に結果が出る
class Stub:
    def __init__(self): self.finished = False; self.axes = []; self.n = 0; self.log = []
    def send(self, m):
        self.n += 1; fin = self.n >= 1
        if fin: self.finished = True; self.axes = AXES
        self.log += [{"role": "student", "text": m}, {"role": "advisor", "text": "q"}]
        return SimpleNamespace(kind="finish", message="q", finished=True, axes=AXES)
    def transcript(self): return self.log

gate = threading.Event(); started = []
def researcher(axes, progress, **kw):
    started.append(axes); progress("research", "調査中"); gate.wait(5)
    return res

srv = S.make_server("127.0.0.1", 0, session_factory=Stub, researcher=researcher)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
S.DATA_DIR = pathlib.Path(tempfile.mkdtemp())

def req(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request(method, path, json.dumps(body).encode() if body is not None else None,
              {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())

st, d = req("POST", "/api/chat", {"session_id": None, "message": "こんにちは"}); sid = d["session_id"]
time.sleep(0.3)
check("会話が終わった時点で調査が始まる（アンケート前）", len(started) == 1 and started[0] == AXES)
sv = req("GET", f"/api/survey?sid={sid}")[1]["survey"]
check("アンケート前の /api/rank は 400", req("POST", "/api/rank", {"session_id": sid})[0] == 400)
good = {q["id"]: 3 for q in sv["questions"]}
req("POST", "/api/survey", {"session_id": sid, "answers": good, "must_have": ["job_axis_1"]})
st, d = req("POST", "/api/rank", {"session_id": sid})
check("調査中は state=running と進み具合", st == 200 and d["state"] == "running" and d["stage"] == "research")
check("調査は二重に始まらない", len(started) == 1)
gate.set(); time.sleep(0.3)
st, d = req("POST", "/api/rank", {"session_id": sid})
check("調査後は state=done とランキング", st == 200 and d["state"] == "done" and d["ranking"]["companies_count"] == 15)
check("保存JSONに ranking と research", {"ranking", "research"} <= set(json.loads(next(S.DATA_DIR.glob("*.json")).read_text(encoding="utf-8"))))
check("2回目はキャッシュ", req("POST", "/api/rank", {"session_id": sid})[1]["ranking"] == d["ranking"])

# ---- 調査の失敗 → 画面向けの文言 → やり直し
n = {"c": 0}
def flaky(axes, progress, **kw):
    n["c"] += 1
    if n["c"] == 1: raise RuntimeError("boom")
    return res
srv2 = S.make_server("127.0.0.1", 0, session_factory=Stub, researcher=flaky)
port = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()
st, d = req("POST", "/api/chat", {"session_id": None, "message": "x"}); sid = d["session_id"]
sv = req("GET", f"/api/survey?sid={sid}")[1]["survey"]
req("POST", "/api/survey", {"session_id": sid, "answers": {q["id"]: 3 for q in sv["questions"]}})
time.sleep(0.3)
st, d = req("POST", "/api/rank", {"session_id": sid})
check("失敗は500＋やさしい文言（内部の文言は出ない）", st == 500 and d["state"] == "error" and "boom" not in d["error"])
st, d = req("POST", "/api/rank", {"session_id": sid}); time.sleep(0.3)
st, d = req("POST", "/api/rank", {"session_id": sid})
check("もう一度呼ぶと、調査をやり直して成功", st == 200 and d["state"] == "done" and n["c"] == 2)
print("ALL OK" if ok else "FAILED")
