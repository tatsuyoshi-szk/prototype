"""共通項目と就活軸から、アンケートの定義（どんな項目を、どの段階で聞くか）を作る。

アンケートの定義はただの dict（JSONにできる）なので、
このフォルダの HTML フォーム以外の画面（Webアプリなど）でもそのまま使える。
"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent / "common_items.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_survey(job_axis: str | list[str], config: dict | None = None) -> dict:
    """アンケートの定義を作る。

    job_axis: 就活軸推定QAで推定した就活軸。例：「海外と関わる製造業の仕事」
              文字列1つでも、複数の軸の名前のリストでもよい。リストなら、軸の数だけ項目を作る。
    config:   common_items.yaml の内容（省略すると既定のファイルを読む）

    項目ID：軸が1つなら `job_axis`（従来どおり）。複数なら `job_axis_1`, `job_axis_2`, …

    戻り値の例:
      {"title": ..., "lead": ..., "job_axis": ..., "job_axes": [...],
       "scale": [{"value": 1, "label": "重視していない"}, ...],
       "questions": [{"id": "job_axis", "name": ..., "explain": ..., "source": "job_axis"},
                     {"id": "foreign_staff_ratio", ..., "source": "common"}, ...]}
    """
    raw = [job_axis] if isinstance(job_axis, str) else list(job_axis or [])
    axes = []
    for a in raw:
        a = (a or "").strip()
        if a and a not in axes:      # 空と重複は取り除く（順番は保つ）
            axes.append(a)
    if not axes:
        raise ValueError("就活軸（job_axis）が空です。就活軸推定QAの結果を渡してください。")
    config = config or load_config()

    common = [
        {"id": it["id"], "name": it["name"], "explain": it.get("explain") or "", "source": "common"}
        for it in config["items"]
    ]
    tmpl = config["job_axis_item"]
    axis_qs = [
        {
            "id": tmpl["id"] if len(axes) == 1 else f"{tmpl['id']}_{i}",
            "name": tmpl["name"].replace("{job_axis}", ax),
            "explain": (tmpl.get("explain") or "").replace("{job_axis}", ax),
            "source": "job_axis",
        }
        for i, ax in enumerate(axes, 1)
    ]
    questions = common + axis_qs if tmpl.get("position") == "last" else axis_qs + common

    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError(f"項目IDが重複しています: {ids}")

    return {
        "title": config["title"],
        "lead": config["lead"].strip(),
        "job_axis": axes[0] if len(axes) == 1 else "、".join(axes),   # 従来との互換のため残す
        "job_axes": axes,
        "scale": [{"value": int(k), "label": v} for k, v in sorted(config["scale"].items())],
        "questions": questions,
    }


def compute_weights(answers: dict) -> dict:
    """1〜5 の点数を、合計が1になる重みに変換する（点数 ÷ 点数の合計）。"""
    total = sum(answers.values())
    return {k: round(v / total, 4) for k, v in answers.items()} if total else {}


def make_result(survey: dict, answers: dict, must_have: list[str] | None = None) -> dict:
    """アンケートの回答から、ランキング計算に渡す結果をまとめる。

    must_have: 「譲れない」にチェックされた項目id。アンケートにない id は捨てる。
               企業の絞り込みに使い、さらに、重みの計算では、その項目を最大の点数（5点）として扱う。
    answers は、ユーザーが選んだ点数のまま残す。
    """
    valid = {q["id"] for q in survey["questions"]}
    must = [i for i in dict.fromkeys(must_have or []) if i in valid]
    top = survey["scale"][-1]["value"]
    effective = {k: (top if k in must else v) for k, v in answers.items()}      # 譲れない項目は、重みでは最大扱い
    return {
        "job_axis": survey["job_axis"],
        "job_axes": survey.get("job_axes", [survey["job_axis"]]),
        "questions": [{"id": q["id"], "name": q["name"], "source": q["source"]} for q in survey["questions"]],
        "answers": answers,
        "weights": compute_weights(effective),
        "must_have": must,
    }
