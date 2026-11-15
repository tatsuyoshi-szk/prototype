"""公開（デモ）モードの確認：招待コードも利用回数の上限もなく、別の Host・別の場所の画面（CORS）から使える。AIは呼ばない。"""
import http.client, json, sys, threading
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import server as S

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("OK  " if cond else "NG  ") + name)

class Fake:
    def __init__(self): self.history, self.questions, self.finished, self.axes = [], 0, False, None
    lang = "ja"
    def send(self, m):
        self.history.append({"role": "user", "content": m})
        self.history.append({"role": "assistant", "content": [{"type": "text", "text": json.dumps({"message": "どうぞ", "kind": "question"})}]})
        return SimpleNamespace(kind="question", message="どうぞ", finished=False, axes=None)
    def transcript(self): return []

def start(access):
    srv = S.make_server("127.0.0.1", 0, session_factory=Fake, access=access)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

def req(srv, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
    h = dict(headers or {})
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
    r = c.getresponse(); data = r.read()
    try: j = json.loads(data)
    except ValueError: j = None
    return r.status, j, {k.lower(): v for k, v in r.getheaders()}

# ---- 既定（公開モードでない）：これまでどおり、このPCからだけ
srv0 = start(None)
st, _, h = req(srv0, "GET", "/api/session?sid=" + "a" * 22, headers={"Host": "demo.example.com"})
check("既定：別の Host は403", st == 403 and "access-control-allow-origin" not in h)
st, _, _ = req(srv0, "POST", "/api/chat", {"message": "こんにちは"}, {"Host": f"127.0.0.1:{srv0.server_address[1]}"})
check("既定：このPCの Host は使える", st == 200)

# ---- 公開モード（招待コードなし・上限なし）
srv = start(S.Access(True, extra_origins=["https://demo-ui.example.com"]))
DEMO = {"Host": "abc-def.trycloudflare.com"}
LOCAL_UI = {"Origin": "http://localhost:5199"}
st, j, h = req(srv, "POST", "/api/chat", {"message": "こんにちは"}, {**DEMO, **LOCAL_UI})
sid = (j or {}).get("session_id")
check("公開モード：コードなしで、別の Host から使える（別の場所の画面にも、応答が読める）",
      st == 200 and sid and h.get("access-control-allow-origin") == "http://localhost:5199")
st, j, _ = req(srv, "GET", f"/api/session?sid={sid}", headers={**DEMO, **LOCAL_UI})
check("続きの会話の取得も、コードなしで通る", st == 200 and j is not None)
st, _, h = req(srv, "OPTIONS", "/api/chat", headers={**DEMO, **LOCAL_UI, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
check("確認の問い合わせ（OPTIONS）が通る", st == 204 and h.get("access-control-allow-origin") == "http://localhost:5199"
      and "content-type" in h.get("access-control-allow-headers", "").lower())
st, _, _ = req(srv, "POST", "/api/chat", {"message": "x"}, {**DEMO, "Origin": "https://evil.example.com"})
check("知らない場所の画面（Origin）は403", st == 403)
st, _, h = req(srv, "OPTIONS", "/api/chat", headers={**DEMO, "Origin": "https://demo-ui.example.com"})
check("ALLOWED_ORIGINS に書いた場所は許可", st == 204 and h.get("access-control-allow-origin") == "https://demo-ui.example.com")
st, _, _ = req(srv, "GET", "/", headers=DEMO)
check("画面のファイルも、取れる", st not in (401, 403))

# ---- 利用回数の上限は、ない
codes = [req(srv, "POST", "/api/chat", {"message": f"{i}"}, {**DEMO, "CF-Connecting-IP": "203.0.113.9"})[0] for i in range(60)]
check("同じ接続元から、60会話を始めても、すべて通る（上限なし）", all(c == 200 for c in codes))

print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
