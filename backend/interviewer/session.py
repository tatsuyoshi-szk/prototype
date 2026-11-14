"""就活相談のインタビューAI。1人の相談者との会話（1セッション）を扱う。

使い方（最小）:
    from interviewer import InterviewSession

    session = InterviewSession()
    turn = session.send("ロシア人です。ロシアに関係する仕事がしたいです")   # 相談者の最初のメッセージ
    print(turn.message)                                                   # 相談者に表示する文章
    while not turn.finished:
        turn = session.send(input("> "))
        print(turn.message)
    print(turn.axes)                                                      # 例: ["ウォッカづくり", "現場で働く", ...]

会話の途中で状態を保存したいとき（Webサーバーなど）:
    data = session.to_dict()                    # JSONにできる dict
    session = InterviewSession.from_dict(data)  # 次のリクエストで復元
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

from . import config

_DIR = Path(__file__).resolve().parent

# 毎ターンの出力形式
TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["question", "confirm", "finish"]},
        "message": {"type": "string"},
        "internal_note": {"type": "string"},
    },
    "required": ["kind", "message", "internal_note"],
    "additionalProperties": False,
}

# 会話の終了後に出す、個人軸（名前だけ）の出力形式
AXES_SCHEMA = {
    "type": "object",
    "properties": {"axes": {"type": "array", "items": {"type": "string"}}},
    "required": ["axes"],
    "additionalProperties": False,
}

FINAL_REQUEST = (
    "【システムからの依頼】会話は終了しました。これは相談者への返事ではありません。"
    "これまでの会話だけをもとに、システムプロンプトの「最終出力（axes）」のルールに従って、"
    "個人軸の名前だけをJSONで出力してください。"
    "軸の名前は、相談者が会話で使っていた言語（日本語または英語）で書いてください。"
)

_JA_CHARS = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def detect_lang(text: str) -> str:
    """文章の言語を、"ja" か "en" で返す。日本語の文字があれば ja、英字だけで3文字以上あれば en、それ以外は ja。"""
    if _JA_CHARS.search(text or ""):
        return "ja"
    return "en" if len(re.findall(r"[A-Za-z]", text or "")) >= 3 else "ja"

LIMIT_NOTICE = (
    "\n\n【システム】質問の回数が上限に達しました。次は、質問をせず、見つけた軸を要約して確認する（kind を confirm にする）か、"
    "確認が済んでいれば会話を終える（kind を finish にする）ようにしてください。"
)


class InterviewError(RuntimeError):
    """拒否（refusal）や、出力の打ち切りなど、続行できないとき。"""


@dataclass
class Turn:
    kind: str                       # "question" / "confirm" / "finish"
    message: str                    # 相談者に表示する文章
    finished: bool                  # 会話が終わったか
    axes: list[str] | None = None   # finished のときだけ入る。軸の名前の一覧（重要な順）
    note: str = ""                  # 内部メモ。相談者には見せない（デバッグ・ログ用）


def load_common_items() -> str:
    """共通項目の一覧（プロンプトに差し込む文字列）。

    正は、アンケート側の survey/common_items.yaml（`items` の name と explain）。
    それが無いときだけ、interviewer/common_items.md（1行に1項目。「#」で始まる行と空行は無視）を読む。
    """
    empty = "（共通項目はまだ登録されていません）"
    yaml_path = _DIR.parent / "survey" / "common_items.yaml"
    if yaml_path.exists():
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        lines = []
        for it in data.get("items") or []:
            name, explain = (it.get("name") or "").strip(), (it.get("explain") or "").strip()
            if name:
                lines.append(f"{name}：{explain}" if explain else name)
        if lines:
            return "\n".join(lines)
    path = _DIR / "common_items.md"
    if not path.exists():
        return empty
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return "\n".join(lines) if lines else empty


def load_system_prompt() -> str:
    text = (_DIR / "prompt.md").read_text(encoding="utf-8")
    return (text.replace("{{max_questions}}", str(config.MAX_QUESTIONS))
                .replace("{{common_items}}", load_common_items()))


class InterviewSession:
    def __init__(self, client: anthropic.Anthropic | None = None, *, system_prompt: str | None = None):
        # ANTHROPIC_API_KEY などの認証情報は、環境変数から読み込まれる
        self.client = client or anthropic.Anthropic(max_retries=4)
        self.system_prompt = system_prompt or load_system_prompt()
        self.history: list[dict] = []
        self.questions = 0
        self.finished = False
        self.axes: list[str] | None = None

    # ------------------------------------------------------------ 公開メソッド

    def send(self, user_message: str) -> Turn:
        """相談者のメッセージを受け取り、アドバイザーの返事を返す。最初のメッセージも、これで送る。"""
        if self.finished:
            raise InterviewError("この会話はもう終了しています。新しい InterviewSession を作ってください。")
        text = user_message.strip()
        if not text:
            raise ValueError("メッセージが空です")
        if self.questions >= config.HARD_LIMIT:
            text += LIMIT_NOTICE
        # 途中で失敗したときは、このターンの分を取り消す（同じメッセージを再送しても、二重に入らない）
        keep_len, keep_questions = len(self.history), self.questions
        try:
            self.history.append({"role": "user", "content": text})
            data, content = self._call(self.history, TURN_SCHEMA, config.EFFORT_CHAT)
            self.history.append({"role": "assistant", "content": content})
            if data["kind"] == "question":
                self.questions += 1

            if data["kind"] == "finish":
                axes = self._final_axes()
                self.axes, self.finished = axes, True
                return Turn(data["kind"], data["message"], True, axes, data["internal_note"])
            return Turn(data["kind"], data["message"], False, None, data["internal_note"])
        except BaseException:
            del self.history[keep_len:]
            self.questions = keep_questions
            raise

    @property
    def lang(self) -> str:
        """会話の言語（相談者の、いちばん新しいメッセージの言語）。画面の言語に使う。"""
        for m in reversed(self.history):
            if m["role"] == "user" and isinstance(m["content"], str):
                return detect_lang(m["content"].replace(LIMIT_NOTICE, ""))
        return "ja"

    def transcript(self) -> list[dict]:
        """会話を [{"role": "student" | "advisor", "text": ...}] で返す。保存・表示用。
        内部メモと、システムが足した注意文は含めない。"""
        out = []
        for m in self.history:
            if m["role"] == "user":
                text = m["content"] if isinstance(m["content"], str) else ""
                out.append({"role": "student", "text": text.replace(LIMIT_NOTICE, "").strip()})
            else:
                body = "".join(b.get("text", "") for b in m["content"] if b.get("type") == "text")
                try:
                    data = json.loads(body)
                    out.append({"role": "advisor", "text": data["message"], "kind": data["kind"]})
                except (ValueError, KeyError):
                    out.append({"role": "advisor", "text": body})
        return out

    def to_dict(self) -> dict:
        """会話の状態を、JSONにできる dict にする。"""
        return {"history": self.history, "questions": self.questions,
                "finished": self.finished, "axes": self.axes}

    @classmethod
    def from_dict(cls, data: dict, client: anthropic.Anthropic | None = None) -> "InterviewSession":
        s = cls(client)
        s.history = data["history"]
        s.questions = data["questions"]
        s.finished = data["finished"]
        s.axes = data["axes"]
        return s

    # ------------------------------------------------------------ 内部

    def _final_axes(self) -> list[str]:
        data, _ = self._call(self.history + [{"role": "user", "content": FINAL_REQUEST}],
                             AXES_SCHEMA, config.EFFORT_FINAL)
        # 念のため、空文字と重複を取り除く（順番は保つ）
        seen, axes = set(), []
        for a in data["axes"]:
            a = a.strip()
            if a and a not in seen:
                seen.add(a)
                axes.append(a)
        return axes

    def _call(self, messages: list[dict], schema: dict, effort: str) -> tuple[dict, list[dict]]:
        kwargs = {}
        if config.USE_FALLBACK:
            kwargs = {"betas": [config.FALLBACK_BETA], "fallbacks": "default"}
        resp = self.client.beta.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=self.system_prompt,
            messages=messages,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            **kwargs,
        )
        if resp.stop_reason == "refusal":
            raise InterviewError(f"モデルが応答を拒否しました: {resp.stop_details}")
        if resp.stop_reason == "max_tokens":
            raise InterviewError("出力が長すぎて打ち切られました。config.MAX_TOKENS を増やしてください。")
        text = "".join(b.text for b in resp.content if b.type == "text")
        # 思考ブロックも含めて、そのまま次のリクエストに渡せるよう、プレーンな dict にして保存する
        content = [b.model_dump(exclude_none=True) for b in resp.content]
        return json.loads(text), content
