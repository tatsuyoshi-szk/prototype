import json, sys, threading, http.client, time, tempfile, pathlib
from types import SimpleNamespace
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "backend"))
import pipeline as P, ranking, server as S
from interviewer.session import InterviewSession, detect_lang, LIMIT_NOTICE

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("OK  " if cond else "NG  ") + name)

# ---- 言語の判定
check("detect_lang: 英語/日本語/混在/短い", (detect_lang("Hi, I am from Vietnam"), detect_lang("こんにちは"), detect_lang("I want 起業"), detect_lang("OK")) == ("en", "ja", "ja", "ja"))
s = InterviewSession.__new__(InterviewSession); s.history = []
check("lang: 履歴がないときは ja", s.lang == "ja")
s.history = [{"role": "user", "content": "Hello, I study business."}, {"role": "assistant", "content": []}]
check("lang: 英語のメッセージなら en", s.lang == "en")
s.history.append({"role": "user", "content": "I want to start a company." + LIMIT_NOTICE})
check("lang: システムの日本語の注意文が付いても、en のまま", s.lang == "en")
s.history.append({"role": "user", "content": "日本語に変えます"})
check("lang: 途中で日本語に変えたら ja", s.lang == "ja")
check("prompt.md に言語の規則がある", "英語で書いたときは、英語で返事する" in (pathlib.Path(__file__).resolve().parents[2].joinpath("backend", "interviewer", "prompt.md").read_text(encoding="utf-8")))

# ---- 採点の指示（英語）
prompts = []
class M:
    @staticmethod
    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        cells = {i: {"score": 4, "evidence_found": False, "basis": "", "source_url": ""} for i in P.IDS}
        cells["visa_support"] = {"score": 4, "evidence_found": True, "basis": "Visa support for families.", "source_url": "https://example.com/ok"}
        axes = {"a1": {"fit": 5, "evidence_found": True, "basis": "New business unit.", "source_url": "https://example.com/ok"}}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps({"items": cells, "axes": axes}))])
client = SimpleNamespace(messages=M)
ev = {"id": "x", "name": "テスト商事", "industry": "商社", "name_en": "Test Trading", "industry_en": "Trading", "profile": "p", "profile_url": "https://example.com/ok",
      "global_offices_list": [], "axis_facts": [], "items": {i: {"finding": "未確認", "source_url": ""} for i in P.IDS}}
ev["items"]["visa_support"] = {"finding": "ビザ支援あり", "source_url": "https://example.com/ok"}
rubric = P.load_rubric()
co_en, fits_en = P.score_company(ev, ["New services"], rubric, client, lang="en")
co_ja, _ = P.score_company(ev, ["新サービス"], rubric, client, lang="ja")
check("英語のとき、採点の指示に『英語で書く』が入る（日本語のときは入らない）", "**英語**で書く" in prompts[0] and "**英語**で書く" not in prompts[1])
check("根拠なしの文言が英語になる", co_en["items"]["foreign_staff_ratio"]["basis"] == P.NO_BASIS_EN and co_ja["items"]["foreign_staff_ratio"]["basis"] == P.NO_BASIS)
check("英語の根拠と出典URLは残る", co_en["items"]["visa_support"]["basis"] == "Visa support for families." and co_en["items"]["visa_support"]["source_url"] == "https://example.com/ok")
check("企業の英語名が引き継がれる", co_en["name_en"] == "Test Trading" and co_en["industry_en"] == "Trading")

# ---- 順位づけ（英語）
sv = __import__("survey").build_survey(["New services"], lang="en")
result = __import__("survey").make_result(sv, {q["id"]: 3 for q in sv["questions"]}, ["visa_support", "foreign_staff_ratio", "job_axis"])
rk = ranking.rank(["New services"], result, companies=[co_en], fits={"x": fits_en}, lang="en")
sc = rk["screening"]
check("絞り込みの表示が英語（軸は“ ”で囲む）", "“New services”" in sc["labels"] and sc["labels"][1] == "Share of foreign-national employees")
check("除外の理由が英語", sc["excluded"] and sc["excluded"][0]["failed"][0]["reason"] == "No evidence found")
check("ランキングに言語と英語名がある", rk["lang"] == "en" and rk["screening"]["total"] == 1)
result["must_have"] = []
rk2 = ranking.rank(["New services"], result, companies=[co_en], fits={"x": fits_en}, lang="en")
check("カードに英語名・業界の英語名", rk2["top"][0]["name_en"] == "Test Trading" and rk2["top"][0]["industry_en"] == "Trading")
rk3 = ranking.rank(["新サービス"], __import__("survey").make_result(__import__("survey").build_survey(["新サービス"]), {q["id"]: 3 for q in __import__("survey").build_survey(["新サービス"])["questions"]}, ["foreign_staff_ratio"]), companies=[co_ja], fits={"x": [{"fit": 3, "fact": 0, "basis": "", "url": ""}]})
check("日本語のときは、これまでどおり（「…で、4点以上が必要」・「根拠が見つからず」）", rk3["screening"]["excluded"][0]["failed"][0]["reason"] == "根拠が見つからず、確認できない")

# ---- サーバー：英語の会話
class Stub:
    def __init__(self): self.finished = False; self.axes = []; self.n = 0; self.log = []; self.lang = "ja"
    def send(self, m):
        self.n += 1; self.lang = "en" if m.isascii() else "ja"
        self.finished = True; self.axes = ["New services"]
        self.log += [{"role": "student", "text": m}, {"role": "advisor", "text": "ok"}]
        return SimpleNamespace(kind="finish", message="ok", finished=True, axes=self.axes)
    def transcript(self): return self.log
got = {}
def researcher(axes, progress, lang="ja", **kw):
    got["lang"] = lang
    return {"companies": [co_en], "fits": {"x": fits_en}, "failed": []}
srv = S.make_server("127.0.0.1", 0, session_factory=Stub, researcher=researcher)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
S.DATA_DIR = pathlib.Path(tempfile.mkdtemp())
def req(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request(method, path, json.dumps(body).encode() if body is not None else None, {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
st, d = req("POST", "/api/chat", {"session_id": None, "message": "Hello, I am from Vietnam."}); sid = d["session_id"]
check("チャットの返事に lang=en", d["lang"] == "en")
check("/api/session に lang", req("GET", f"/api/session?sid={sid}")[1]["lang"] == "en")
sv2 = req("GET", f"/api/survey?sid={sid}")[1]["survey"]
check("アンケートが英語", sv2["lang"] == "en" and sv2["scale"][4]["label"] == "Important" and sv2["questions"][1]["name"] == "Share of foreign-national employees")
st, d = req("POST", "/api/rank", {"session_id": sid})
check("アンケート前の /api/rank のエラーが英語", st == 400 and d["error"] == "Please answer the survey first.")
req("POST", "/api/survey", {"session_id": sid, "answers": {q["id"]: 3 for q in sv2["questions"]}, "must_have": []})
time.sleep(0.3)
check("調査に lang=en が渡る", got.get("lang") == "en")
st, d = req("POST", "/api/rank", {"session_id": sid})
check("結果に lang=en と英語名", st == 200 and d["ranking"]["lang"] == "en" and d["ranking"]["top"][0]["name_en"] == "Test Trading")
check("tr: 英語・日本語", S.tr(S.MSG_FAIL, "en").startswith("An error occurred") and S.tr(S.MSG_FAIL, "ja") == S.MSG_FAIL and S.tr(S.MSG_RANK + "（x）", "en").startswith("Could not build"))
print("ALL OK" if ok else "FAILED")
