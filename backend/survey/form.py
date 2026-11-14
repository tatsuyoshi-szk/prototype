"""アンケートの定義から、チェック式のHTMLフォームを作り、回答を受け取る。"""
from __future__ import annotations

import html
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;
  background:#f5f6f8;color:#1f2328;line-height:1.6}
main{max-width:880px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.4rem;margin:0 0 8px}
.lead{margin:0 0 20px;color:#444}
.error{background:#fdecec;border:1px solid #f2b8b8;color:#8a1c1c;padding:10px 14px;border-radius:8px;margin-bottom:16px}
.sheet{background:#fff;border:1px solid #dde1e6;border-radius:10px;overflow:hidden}
.row{display:grid;grid-template-columns:1fr repeat(5,64px);align-items:center;border-top:1px solid #eef0f3}
.row:first-child{border-top:none}
.head{position:sticky;top:0;background:#f0f3f7;font-size:.75rem;color:#555;text-align:center;z-index:1}
.head div{padding:8px 4px;line-height:1.3}
.item{padding:12px 16px}
.num{color:#8a8f98;font-size:.8rem;margin-right:6px}
.name{font-weight:600}
.explain{display:block;font-size:.8rem;color:#6b7078;margin-top:2px}
.row.missing{background:#fff6f6}
label.opt{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;
  min-height:56px;cursor:pointer}
label.opt:hover{background:#f2f6ff}
label.opt input{width:20px;height:20px;margin:0;accent-color:#2f6fe4;cursor:pointer}
label.opt span{display:none;font-size:.7rem;color:#555;text-align:center;line-height:1.2}
label.opt small{display:block;font-size:.62rem;color:#8a8f98}
.footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:20px}
.progress{color:#555;font-size:.9rem}
button{background:#2f6fe4;color:#fff;border:none;border-radius:8px;padding:12px 28px;font-size:1rem;cursor:pointer}
button:hover{background:#2459bd}
@media (max-width:640px){
  .head{display:none}
  .row{grid-template-columns:repeat(5,1fr)}
  .item{grid-column:1/-1;padding:12px 12px 4px}
  label.opt{min-height:52px;justify-content:flex-start;padding:8px 0 6px}
  label.opt small{white-space:nowrap}
  label.opt span{display:block}
}
"""

PROGRESS_JS = """
const form=document.querySelector('form'),out=document.getElementById('progress'),n=%d;
function update(){const done=new Set([...form.querySelectorAll('input:checked')].map(e=>e.name)).size;
  out.textContent=done+' / '+n+' 項目 回答済み';
  form.querySelectorAll('.row.missing').forEach(r=>{if(r.querySelector('input:checked'))r.classList.remove('missing')});}
form.addEventListener('change',update);update();
"""

THANKS_HTML = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>送信しました</title>
<style>body{font-family:system-ui,"Hiragino Sans",sans-serif;background:#f5f6f8;display:grid;place-items:center;
height:100vh;margin:0}div{background:#fff;padding:32px 40px;border-radius:12px;border:1px solid #dde1e6;text-align:center}</style>
</head><body><div><h2>ありがとうございました</h2><p>回答を受け取りました。結果は会社のランキングに反映されます。<br>
このページは閉じてかまいません。</p></div></body></html>"""


def render_html(survey: dict, answers: dict | None = None, missing: list[str] | None = None,
                action: str = "/submit") -> str:
    """アンケートの定義から、チェック式フォームのHTMLを作る。"""
    answers, missing = answers or {}, missing or []
    esc = html.escape
    scale = survey["scale"]
    lo, hi = scale[0]["value"], scale[-1]["value"]

    head = '<div class="row head"><div></div>' + "".join(
        f"<div>{s['value']}<br>{esc(s['label'])}</div>" for s in scale) + "</div>"
    rows = []
    for i, q in enumerate(survey["questions"], 1):
        opts = []
        for s in scale:
            v = s["value"]
            checked = " checked" if str(answers.get(q["id"])) == str(v) else ""
            # スマホ表示では見出し行が消えるので、両端の意味だけ数字の下に出す
            edge = f"<small>{esc(s['label'])}</small>" if v in (lo, hi) else ""
            opts.append(f'<label class="opt" title="{esc(s["label"])}">'
                        f'<input type="radio" name="{esc(q["id"])}" value="{v}" required{checked}>'
                        f'<span>{v}{edge}</span></label>')
        explain = f'<span class="explain">{esc(q["explain"])}</span>' if q.get("explain") else ""
        cls = "row missing" if q["id"] in missing else "row"
        rows.append(f'<div class="{cls}"><div class="item"><span class="num">{i}</span>'
                    f'<span class="name">{esc(q["name"])}</span>{explain}</div>{"".join(opts)}</div>')

    lead = "<br>".join(esc(line) for line in survey["lead"].splitlines())
    scale_text = " / ".join(f"{s['value']}：{esc(s['label'])}" for s in scale)
    error = (f'<div class="error">まだ選んでいない項目が {len(missing)} 個あります。赤い行を選んでください。</div>'
             if missing else "")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(survey['title'])}</title><style>{CSS}</style></head>
<body><main>
<h1>{esc(survey['title'])}</h1>
<p class="lead">{lead}<br><small>{scale_text}</small></p>
{error}
<form method="post" action="{esc(action)}">
<div class="sheet">{head}{''.join(rows)}</div>
<div class="footer"><span class="progress" id="progress"></span><button type="submit">送信する</button></div>
</form>
</main><script>{PROGRESS_JS % len(survey['questions'])}</script></body></html>"""


def parse_answers(form: dict, survey: dict) -> tuple[dict, list[str]]:
    """フォームの値（parse_qs の結果）から {項目id: 点数} を作る。戻り値は (回答, 未回答の項目id)。"""
    valid = {str(s["value"]) for s in survey["scale"]}
    answers, missing = {}, []
    for q in survey["questions"]:
        v = (form.get(q["id"]) or [""])[0]
        if v in valid:
            answers[q["id"]] = int(v)
        else:
            missing.append(q["id"])
    return answers, missing


def collect_answers(survey: dict, port: int = 0, open_browser: bool = True) -> dict:
    """手元で小さなWebサーバーを起動してフォームを開き、送信されるまで待って {項目id: 点数} を返す。"""
    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: str, status: int = 200):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(THANKS_HTML if done.is_set() else render_html(survey))
            else:
                self._send("not found", 404)

        def do_POST(self):
            if self.path != "/submit":
                return self._send("not found", 404)
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
            answers, missing = parse_answers(form, survey)
            if missing:
                return self._send(render_html(survey, answers, missing))
            result.update(answers)
            self._send(THANKS_HTML)
            done.set()

        def log_message(self, *args):  # アクセスログは表示しない
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\nアンケートを開きます: {url}\n（ブラウザが開かないときは、このURLを開いてください。送信されるまで待ちます）")
    if open_browser:
        webbrowser.open(url)
    try:
        done.wait()
    finally:
        server.shutdown()
        server.server_close()
    return result
