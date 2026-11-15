"""就活相談チャットボットのバックエンド（JSON API だけ。画面は frontend/ の React）。

  python server.py                  # http://127.0.0.1:8000/ （frontend をビルド済みなら、画面も同じアドレスで出る）
  python server.py --port 8080

API:
  POST /api/chat            会話を1往復進める
  GET  /api/session?sid=    会話の履歴・軸・回答済みか・ランキング
  GET  /api/survey?sid=     アンケートの定義（会話が終わったあと）
  POST /api/survey          アンケートの回答（と「譲れない」項目）を保存する
  POST /api/rank            合う企業のランキング。調査（Web）が終わるまでは state=running を返す。
                            調査は、会話が終わった時点で裏で始まる（pipeline.py）

APIキーは、.env に `ANTHROPIC_API_KEY=sk-ant-...` と書いて置く（.env.example を参照）。
標準ライブラリだけで動く（追加の依存は anthropic と pyyaml）。このPC（127.0.0.1）からだけ接続できる。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from interviewer import InterviewError, InterviewSession  # noqa: E402
from interviewer.session import detect_lang  # noqa: E402
from survey import build_survey, make_result  # noqa: E402

DATA_DIR = ROOT / "data"          # 回答の保存先（個人情報を含む）
FRONTEND_DIST = ROOT.parent / "frontend" / "dist"      # ビルド済みの画面（あれば、このサーバーが配る）
DEV_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}   # frontend の開発サーバー（npm run dev）
MAX_BODY = 32 * 1024              # リクエスト本文の上限（バイト）
MAX_MESSAGE = 2000                # 相談者のメッセージの上限（文字）
SID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

MSG_AUTH = "APIキーが正しくありません。prottype フォルダの .env を確認してください。"
MSG_BUSY = "AIが混み合っています。少し待ってから、もう一度送ってください。"
MSG_FAIL = "AIとの通信でエラーが起きました。もう一度送ってください。"
MSG_REFUSED = "この内容には、AIが答えられませんでした。言い方を変えて、もう一度送ってください。"
MSG_RANK = "企業のランキングを作れませんでした。少し待ってから、ページを読み込み直してください（もう一度、計算します）。"
MSG_RANK_BUSY = "AIが混み合っています。少し待ってから、ページを読み込み直してください（もう一度、計算します）。"

# 英語の画面向けの文言（日本語の文言が、先頭から一致したら、対応する英語にする）
MSG_EN = {
    MSG_AUTH: "The API key is not valid. Check the .env file in the prottype folder.",
    MSG_BUSY: "The AI is busy. Please wait a moment and send again.",
    MSG_FAIL: "An error occurred while talking to the AI. Please send again.",
    MSG_REFUSED: "The AI could not answer this. Please rephrase and send again.",
    MSG_RANK: "Could not build the company ranking. Please wait a moment and reload the page (it will be calculated again).",
    MSG_RANK_BUSY: "The AI is busy. Please wait a moment and reload the page (it will be calculated again).",
    "先にアンケートに答えてください。": "Please answer the survey first.",
    "会話が見つかりません。ページを読み込み直してください。": "Conversation not found. Please reload the page.",
}


def tr(text: str, lang: str) -> str:
    """画面に出す文言を、画面の言語にする。"""
    if lang != "en":
        return text
    for ja, en in MSG_EN.items():
        if text.startswith(ja):
            return en
    return text


def lang_of(entry: dict) -> str:
    return getattr(entry["session"], "lang", "ja")


# ---------------------------------------------------------------- .env とAPIキー

def load_env(path: Path) -> set[str]:
    """`KEY=VALUE` の行を読み込み、環境変数にセットする（すでにある環境変数より .env を優先）。読んだキー名を返す。"""
    loaded: set[str] = set()
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value:
            os.environ[key] = value
            loaded.add(key)
    return loaded


def check_api_key() -> None:
    loaded = load_env(ROOT / ".env") | load_env(ROOT.parent / ".env")   # backend/.env か、その1つ上の .env
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("APIキーが見つかりません。\n"
              f"  {ROOT.parent / '.env'} を作り、次の1行を書いてください:\n"
              "  ANTHROPIC_API_KEY=sk-ant-...\n"
              "  （.env.example をコピーしてもかまいません）")
        sys.exit(1)
    source = ".env" if "ANTHROPIC_API_KEY" in loaded else "環境変数"
    print(f"APIキー: {source} から読み込みました（末尾 {key[-4:]}）")   # キーの全体は表示しない


# ---------------------------------------------------------------- セッション

class Store:
    """会話（セッション）を持つ。persist_dir があれば、変わるたびにファイルへ保存し、サーバーを再起動しても復元する。"""

    def __init__(self, factory, persist_dir: Path | None = None):
        self.factory = factory
        self.persist_dir = persist_dir
        self._items: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _new_entry(self, session, sid: str) -> dict:
        return {"sid": sid, "session": session, "lock": threading.Lock(), "saved": False,
                "result": None, "ranking": None, "path": None,
                "research": {"state": "idle", "stage": "", "detail": "", "data": None, "error": "", "t0": 0.0}}

    def create(self) -> tuple[str, dict]:
        sid = secrets.token_urlsafe(16)
        entry = self._new_entry(self.factory(), sid)
        with self._lock:
            self._items[sid] = entry
        return sid, entry

    def get(self, sid: str | None) -> dict | None:
        if not sid or not SID_RE.match(sid):
            return None
        with self._lock:
            entry = self._items.get(sid)
            if entry is None:
                entry = self._load(sid)
                if entry is not None:
                    self._items[sid] = entry
            return entry

    # --- ファイルへの保存・復元（調査の途中経過は保存しない。調べ直しは cache があるので速い）
    def save(self, entry: dict) -> None:
        session = entry["session"]
        if self.persist_dir is None or not hasattr(session, "to_dict"):
            return
        r = entry["research"]
        payload = {"session": session.to_dict(), "saved": entry["saved"], "result": entry["result"],
                   "ranking": entry["ranking"], "path": str(entry["path"]) if entry["path"] else None,
                   "research_data": r["data"] if r["state"] == "done" else None}
        try:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            path = self.persist_dir / f"{entry['sid']}.json"
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError):
            traceback.print_exc()      # 保存に失敗しても、会話は続ける

    def _load(self, sid: str) -> dict | None:
        restore = getattr(self.factory, "from_dict", None)
        if self.persist_dir is None or restore is None:
            return None
        path = self.persist_dir / f"{sid}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry = self._new_entry(restore(payload["session"]), sid)
            entry.update(saved=bool(payload["saved"]), result=payload["result"], ranking=payload["ranking"],
                         path=Path(payload["path"]) if payload.get("path") else None)
            if payload.get("research_data"):
                entry["research"].update(state="done", data=payload["research_data"])
            return entry
        except (OSError, ValueError, KeyError, TypeError):
            return None


def add_ranking(path: Path | None, ranking: dict, research: dict | None = None) -> None:
    """保存済みの回答のJSONに、ランキングと、調べて採点した企業のデータを追記する。"""
    if path is None or not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ranking"] = ranking
    if research is not None:
        payload["research"] = research
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_researcher(axes: list[str], progress, lang: str = "ja", must: list[dict] | None = None) -> dict:
    """企業を選び、サブエージェント（Web）で調べ、採点する。ユーザーが使うたびに行う。"""
    from pipeline import PipelineError, run_research   # 使うときに読み込む（テストでは差し替える）
    try:
        return run_research(axes, progress=progress, lang=lang, must=must)
    except PipelineError as exc:
        raise RankingFailed(str(exc)) from exc


def default_ranker(axes: list[str], result: dict, research: dict, lang: str = "ja") -> dict:
    """アンケートの重みと「譲れない条件」で、調査・採点の結果を順位づけする。"""
    from ranking import rank
    ranking = rank(axes, result, companies=research["companies"], fits=research["fits"], lang=lang)
    ranking["failed"] = research.get("failed", [])
    return ranking


class RankingFailed(RuntimeError):
    """企業データがない、など。画面に出してよい文言を持つ。"""


def save_result(sid: str, entry: dict, result: dict) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    session = entry["session"]
    path = DATA_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{sid[:8]}.json"
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "axes": session.axes,
        "transcript": session.transcript(),
        "survey": result,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def friendly_error(exc: Exception) -> tuple[int, str]:
    """例外を、画面に出す文言とHTTPステータスにする。詳細はコンソールにだけ出す。"""
    if isinstance(exc, RankingFailed):
        return 500, f"{MSG_RANK}（{exc}）"
    if isinstance(exc, InterviewError):
        return 502, MSG_REFUSED if "拒否" in str(exc) else MSG_FAIL
    name = type(exc).__name__
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return 502, MSG_AUTH
    if name in ("RateLimitError", "InternalServerError", "APIConnectionError", "APITimeoutError"):
        return 503, MSG_BUSY
    return 500, MSG_FAIL


# ---------------------------------------------------------------- HTTP

def make_handler(store: Store, ranker, researcher):
    def start_research(entry: dict) -> None:
        """調査を裏のスレッドで始める（すでに動いている・終わっているときは何もしない）。"""
        r = entry["research"]
        if r["state"] in ("running", "done"):
            return
        r.update(state="running", stage="select", detail="準備しています", error="", t0=time.time())
        axes = list(entry["session"].axes)
        lang = lang_of(entry)
        result = entry["result"] or {}
        qs = result.get("questions") or []
        axis_qids = [q["id"] for q in qs if q["source"] == "job_axis"]
        job_axes = result.get("job_axes") or axes
        names = {q["id"]: q["name"] for q in qs}
        must = [{"qid": m, "axis": axis_qids.index(m) if m in axis_qids else None,
                 "label": job_axes[axis_qids.index(m)] if m in axis_qids and axis_qids.index(m) < len(job_axes) else names.get(m, m)}
                for m in (result.get("must_have") or [])]      # 譲れない条件（企業の絞り込みに使う）

        def progress(stage: str, detail: str = ""):
            r["stage"], r["detail"] = stage, detail

        def work():
            try:
                r["data"] = researcher(axes, progress, lang=lang, must=must)
                r["state"] = "done"
                store.save(entry)
            except Exception as exc:   # noqa: BLE001  詳細はコンソールへ
                traceback.print_exc()
                _, text = friendly_error(exc)
                r.update(state="error", error=tr({MSG_FAIL: MSG_RANK, MSG_BUSY: MSG_RANK_BUSY}.get(text, text), lang))

        threading.Thread(target=work, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "prottype"

        # --- 共通
        def _send(self, body: str | bytes, status: int = 200, ctype: str = "text/html; charset=utf-8", headers=None):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj: dict, status: int = 200):
            self._send(json.dumps(obj, ensure_ascii=False), status, "application/json; charset=utf-8")

        def _redirect(self, where: str):
            self._send("", 302, headers={"Location": where})

        def _local_only(self) -> bool:
            """別のサイトから、このサーバー（＝APIの料金）を使われないよう、Host と Origin を確かめる。"""
            port = self.server.server_address[1]
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                self._send("forbidden", 403, "text/plain; charset=utf-8")
                return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{host}" and origin not in DEV_ORIGINS:
                self._send("forbidden", 403, "text/plain; charset=utf-8")
                return False
            return True

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self.close_connection = True   # 大きすぎる本文は読まずに拒否する（接続が切れて見えることがある）
                self._send("payload too large", 413, "text/plain; charset=utf-8", headers={"Connection": "close"})
                return None
            return self.rfile.read(length)

        def log_message(self, fmt, *args):   # アクセスログは出さない
            pass

        # --- GET
        def do_GET(self):
            if not self._local_only():
                return
            url = urlparse(self.path)
            if url.path == "/api/survey":
                sid = (parse_qs(url.query).get("sid") or [""])[0]
                entry = store.get(sid)
                if entry is None:
                    return self._json({"error": "会話が見つかりません"}, 404)
                if not entry["session"].finished:
                    return self._json({"error": "会話がまだ終わっていません"}, 400)
                if entry["saved"]:
                    return self._json({"error": "すでに回答済みです", "answered": True}, 409)
                return self._json({"survey": build_survey(entry["session"].axes, lang=lang_of(entry))})
            if url.path == "/api/session":
                sid = (parse_qs(url.query).get("sid") or [""])[0]
                entry = store.get(sid)
                if entry is None:
                    return self._json({"error": "会話が見つかりません"}, 404)
                session = entry["session"]
                return self._json({"lang": lang_of(entry), "finished": session.finished, "axes": session.axes,
                                   "answered": entry["saved"], "transcript": session.transcript(),
                                   "ranking": entry["ranking"]})
            if url.path.startswith("/api/"):
                return self._send("not found", 404, "text/plain; charset=utf-8")
            self._static(url.path)

        def _static(self, path: str):
            """ビルド済みの画面（frontend/dist）を配る。ファイルがなければ index.html（画面側で行き先を決める）。"""
            if not FRONTEND_DIST.exists():
                return self._send("画面がビルドされていません。frontend フォルダで `npm run build` するか、"
                                  "`npm run dev`（http://127.0.0.1:5173/）を使ってください。", 404,
                                  "text/plain; charset=utf-8")
            root = FRONTEND_DIST.resolve()
            target = (root / path.lstrip("/")).resolve()
            if root not in target.parents or not target.is_file():    # フォルダの外は見せない
                target = root / "index.html"
            ctype = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
                     ".html": "text/html", ".json": "application/json"}.get(target.suffix, "application/octet-stream")
            self._send(target.read_bytes(), 200, ctype + "; charset=utf-8")

        # --- POST
        def do_POST(self):
            # 本文は、どのエラーを返す場合でも、先に読み切る（読まずに閉じると、ブラウザにエラー内容が届かないことがある）
            raw = self._read_body()
            if raw is None:
                return
            if not self._local_only():
                return
            url = urlparse(self.path)
            if url.path == "/api/chat":
                return self._chat(raw)
            if url.path == "/api/survey":
                return self._submit(raw)
            if url.path == "/api/rank":
                return self._rank(raw)
            self._send("not found", 404, "text/plain; charset=utf-8")

        def _chat(self, raw: bytes):
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json({"error": "Content-Type が正しくありません"}, 415)
            try:
                body = json.loads(raw.decode("utf-8"))
                message = body["message"].strip()
                sid = body.get("session_id")
            except (ValueError, KeyError, AttributeError, TypeError):
                return self._json({"error": "リクエストの形が正しくありません"}, 400)
            if not message:
                return self._json({"error": "メッセージが空です"}, 400)
            if len(message) > MAX_MESSAGE:
                return self._json({"error": f"メッセージが長すぎます（{MAX_MESSAGE}文字まで）"}, 400)

            if sid is None:
                sid, entry = store.create()
            else:
                entry = store.get(sid)
                if entry is None:
                    return self._json({"error": "会話が見つかりません。ページを読み込み直してください。"}, 404)
            with entry["lock"]:
                session = entry["session"]
                if session.finished:
                    return self._json({"error": "この会話は終了しています。"}, 400)
                try:
                    turn = session.send(message)
                except Exception as exc:   # noqa: BLE001  詳細はコンソールへ、画面にはやさしい文言だけ
                    traceback.print_exc()
                    status, text = friendly_error(exc)
                    return self._json({"error": tr(text, detect_lang(message)), "session_id": sid}, status)
                store.save(entry)
            self._json({"session_id": sid, "kind": turn.kind, "message": turn.message, "lang": lang_of(entry),
                        "finished": turn.finished, "axes": turn.axes})

        def _submit(self, raw: bytes):
            try:
                body = json.loads(raw.decode("utf-8"))
                sid, given = body.get("session_id"), body["answers"]
                must = body.get("must_have") or []
                if not isinstance(given, dict) or not isinstance(must, list) or not all(isinstance(m, str) for m in must):
                    raise TypeError
            except (ValueError, KeyError, AttributeError, TypeError):
                return self._json({"error": "リクエストの形が正しくありません"}, 400)
            entry = store.get(sid)
            if entry is None:
                return self._json({"error": "会話が見つかりません。ページを読み込み直してください。"}, 404)
            with entry["lock"]:
                if not entry["session"].finished:
                    return self._json({"error": "会話がまだ終わっていません"}, 400)
                if entry["saved"]:
                    return self._json({"error": "すでに回答済みです", "answered": True}, 409)
                survey = build_survey(entry["session"].axes, lang=lang_of(entry))
                valid = {s["value"] for s in survey["scale"]}
                answers, missing = {}, []
                for q in survey["questions"]:
                    v = given.get(q["id"])
                    if isinstance(v, int) and not isinstance(v, bool) and v in valid:
                        answers[q["id"]] = v
                    else:
                        missing.append(q["id"])
                if missing:
                    return self._json({"error": f"まだ選んでいない項目が {len(missing)} 個あります。", "missing": missing}, 400)
                result = make_result(survey, answers, must)
                path = save_result(sid, entry, result)
                entry.update(saved=True, result=result, path=path)
                start_research(entry)      # 譲れない条件が決まったので、ここから企業を集める
                store.save(entry)
            print(f"回答を保存しました: {path}")
            self._json({"ok": True})

        def _rank(self, raw: bytes):
            """ランキングの取得（何度呼んでもよい）。調査が終わるまでは state=running と進み具合を返す。"""
            try:
                sid = json.loads(raw.decode("utf-8")).get("session_id")
            except (ValueError, AttributeError):
                return self._json({"error": "リクエストの形が正しくありません"}, 400)
            entry = store.get(sid)
            if entry is None:
                return self._json({"error": "会話が見つかりません。ページを読み込み直してください。"}, 404)
            with entry["lock"]:
                if not entry["saved"]:
                    return self._json({"error": tr("先にアンケートに答えてください。", lang_of(entry))}, 400)
                if entry["ranking"] is not None:        # 計算は1回だけ。2回目以降は、保存した結果を返す
                    return self._json({"state": "done", "ranking": entry["ranking"]})
                r = entry["research"]
                if r["state"] == "error":
                    msg = r["error"]      # 調査のスレッドで、すでに画面の言語にしてある
                    r["state"] = "idle"                 # 次に呼ばれたら、調査をやり直す
                    return self._json({"state": "error", "error": msg}, 500)
                if r["state"] == "idle":                # 復元したときなど、まだ始まっていなければ、ここで始める
                    start_research(entry)
                if r["state"] == "running":
                    return self._json({"state": "running", "stage": r["stage"], "detail": r["detail"],
                                       "elapsed": int(time.time() - r["t0"])})
                try:                                    # 調査が終わっている：重みと譲れない条件で順位づけする
                    entry["ranking"] = ranker(entry["session"].axes, entry["result"], r["data"], lang=lang_of(entry))
                except Exception as exc:   # noqa: BLE001
                    traceback.print_exc()
                    status, text = friendly_error(exc)
                    text = tr({MSG_FAIL: MSG_RANK, MSG_BUSY: MSG_RANK_BUSY}.get(text, text), lang_of(entry))
                    return self._json({"state": "error", "error": text}, status)
                add_ranking(entry["path"], entry["ranking"], r["data"])
                store.save(entry)
            self._json({"state": "done", "ranking": entry["ranking"]})

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 8000, session_factory=InterviewSession,
                ranker=default_ranker, researcher=default_researcher, persist_dir: Path | None = None) -> ThreadingHTTPServer:
    store = Store(session_factory, persist_dir)
    server = ThreadingHTTPServer((host, port), make_handler(store, ranker, researcher))
    server.daemon_threads = True
    server.store = store
    return server


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="就活相談チャットボット（ローカル）")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    check_api_key()
    server = make_server("127.0.0.1", args.port, persist_dir=DATA_DIR / "sessions")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"APIサーバーを起動しました: {url}\n（画面は frontend で `npm run dev` → http://127.0.0.1:5173/ 。"
          "止めるときは Ctrl+C。会話は data/sessions/ に保存され、再起動しても続きから開けます）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
