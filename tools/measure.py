"""企業探し（pipeline.run_research）の所要時間を、本物のAPIで測る。段階ごとの時間と、呼び出しごとの時間・トークンを出す。"""
import json, sys, time, threading
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
import anthropic
import server
server.check_api_key()
import pipeline as P

AXES = ["北米の人と関わる仕事", "若いうちから稼げる", "現場で働く", "起業の経験", "コンサル・金融"]
t0 = time.time()
log = []
lock = threading.Lock()

def stamp(stage, detail=""):
    with lock:
        print(f"[{time.time() - t0:6.1f}s] {stage}: {detail}", flush=True)

class Timed:
    """client を包んで、呼び出しごとの時間・使用量を記録する。"""
    def __init__(self, c): self.c = c; self.beta = _B(self); self.messages = _M(self)

class _B:
    def __init__(self, o): self.messages = _BM(o)
class _BM:
    def __init__(self, o): self.o = o
    def create(self, **kw):
        s = time.time(); r = self.o.c.beta.messages.create(**kw)
        u = r.usage
        with lock: log.append(("main", kw["model"], time.time() - s, u.input_tokens, u.output_tokens))
        return r
class _M:
    def __init__(self, o): self.o = o
    def create(self, **kw):
        s = time.time(); r = self.o.c.messages.create(**kw); u = r.usage
        with lock: log.append(("main", kw["model"], time.time() - s, u.input_tokens, u.output_tokens))
        return r
    def stream(self, **kw):
        outer = self
        class Ctx:
            def __enter__(s2): s2.s = time.time(); s2.cm = outer.o.c.messages.stream(**kw); s2.st = s2.cm.__enter__(); return s2
            def get_final_message(s2):
                r = s2.st.get_final_message(); u = r.usage
                tools = sum(1 for b in r.content if b.type in ("server_tool_use",))
                with lock: log.append(("sub", kw["model"], time.time() - s2.s, u.input_tokens, u.output_tokens, tools, r.stop_reason, getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0))
                return r
            def __exit__(s2, *a): return s2.cm.__exit__(*a)
        return Ctx()

client = Timed(anthropic.Anthropic(max_retries=4))
res = P.run_research(AXES, client, progress=stamp)
total = time.time() - t0
print(f"\n合計 {total:.0f}秒（{total/60:.1f}分）  企業 {len(res['companies'])}社  失敗 {res['failed']}")
sub = [x for x in log if x[0] == "sub"]; main = [x for x in log if x[0] == "main"]
print(f"サブ呼び出し {len(sub)}回, 最長 {max(x[2] for x in sub):.0f}秒")
si, so, sc, sw = (sum(x[3] for x in sub), sum(x[4] for x in sub), sum(x[7] for x in sub), sum(x[8] for x in sub))
print(f"サブ合計: 入力 {si:,} / 出力 {so:,} / キャッシュ読み {sc:,} / キャッシュ書き込み {sw:,}")
mi, mo = sum(x[3] for x in main), sum(x[4] for x in main)
print(f"メイン合計: 入力 {mi:,} / 出力 {mo:,}")
print(f"メイン呼び出し {len(main)}回: 平均 {sum(x[2] for x in main)/len(main):.0f}秒 / 最大 {max(x[2] for x in main):.0f}秒; 出力トークン平均 {sum(x[4] for x in main)/len(main):.0f}")
known = [sum(1 for v in c["items"].values() if not v["unconfirmed"]) for c in res["companies"]]
print("根拠あり項目の平均:", sum(known) / len(known), "/ 14")
json.dump(res, open("measure_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
