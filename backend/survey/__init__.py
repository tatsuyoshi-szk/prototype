"""重み付けアンケート：共通項目と就活軸（就活軸推定QAの出力）から、アンケートを作って回答を集める。

    from survey import build_survey, collect_answers, make_result
    s = build_survey("海外と関わる製造業の仕事")   # アンケートの定義を作る
    answers = collect_answers(s)                   # ブラウザのフォームで回答を集める
    result = make_result(s, answers)               # 点数と重み（ランキング計算に使う）
"""
from .builder import build_survey, compute_weights, load_config, make_result
from .form import collect_answers, parse_answers, render_html

__all__ = ["build_survey", "compute_weights", "load_config", "make_result",
           "collect_answers", "parse_answers", "render_html", "run"]


def run(job_axis: str, port: int = 0, open_browser: bool = True) -> dict:
    """アンケートを作る → フォームで回答を集める → 結果をまとめる、を一度に行う。"""
    s = build_survey(job_axis)
    return make_result(s, collect_answers(s, port=port, open_browser=open_browser))


def print_result(result: dict) -> None:
    print("\n--- アンケート結果（企業スコアの重み） ---")
    for q in result["questions"]:
        print(f"{q['id']:<24} 点数 {result['answers'].get(q['id'], '-')}  "
              f"重み {result['weights'].get(q['id'], '-')}  {q['name']}")
