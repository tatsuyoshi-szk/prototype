"""会話の保存・復元（サーバーを作り直しても、同じ sid で続きが開ける）。AIは呼ばない。"""
import json, sys, tempfile, threading, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import server as S

class Fake:
    def __init__(self): self.history, self.questions, self.finished, self.axes = [], 0, False, None
    def send(self, m):
        self.history.append({"role": "user", "content": m})
        self.history.append({"role": "assistant", "content": [{"type": "text", "text": json.dumps({"message": "どうぞ", "kind": "question"})}]})
        from types import SimpleNamespace
        return SimpleNamespace(kind="question", message="どうぞ", finished=False, axes=None)
    lang = "ja"
    def transcript(self): return [{"role": "student", "text": self.history[0]["content"]}, {"role": "advisor", "text": "どうぞ"}]
    def to_dict(self): return {"history": self.history, "questions": 0, "finished": False, "axes": None}
    @classmethod
    def from_dict(cls, d):
        s = cls(); s.history = d["history"]; return s

def run(d):
    srv = S.make_server("127.0.0.1", 0, session_factory=Fake, persist_dir=Path(d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"

ok = True
def check(n, c):
    global ok; ok &= bool(c); print("OK " if c else "NG ", n)

with tempfile.TemporaryDirectory() as d:
    srv, base = run(d)
    req = urllib.request.Request(base + "/api/chat", json.dumps({"message": "こんにちは"}).encode(), {"Content-Type": "application/json"})
    sid = json.load(urllib.request.urlopen(req))["session_id"]
    srv.shutdown(); srv.server_close()
    srv2, base2 = run(d)                       # 再起動したつもり
    got = json.load(urllib.request.urlopen(f"{base2}/api/session?sid={sid}"))
    check("再起動しても、会話の履歴が残る", got["transcript"][0]["text"] == "こんにちは" and len(got["transcript"]) == 2)
    try: urllib.request.urlopen(f"{base2}/api/session?sid=" + "x" * 22); code = 200
    except urllib.error.HTTPError as e: code = e.code
    check("知らない sid は404", code == 404)
    srv2.shutdown(); srv2.server_close()
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
