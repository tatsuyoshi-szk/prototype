"""インタビューAIの設定。必要に応じて、ここだけ書き換える。"""

# 使うモデル（Claude Opus 5.5）
MODEL = "claude-opus-5-5"

# 思考の深さ: low / medium / high / xhigh / max
EFFORT_CHAT = "medium"    # 毎ターンの質問
EFFORT_FINAL = "high"     # 会話の終了後に、軸の名前を出すとき

# 質問の回数
MAX_QUESTIONS = 5         # 目安（プロンプトに埋め込まれる）
HARD_LIMIT = 7            # 安全装置：この回数を超えたら、確認か終了に進むよう指示する

# 1回のリクエストで出力できる最大トークン数
MAX_TOKENS = 16000

# 拒否（refusal）されたとき、サーバー側で別のモデルに切り替えて続ける。不要なら False
USE_FALLBACK = True
FALLBACK_BETA = "server-side-fallback-2026-07-01"
