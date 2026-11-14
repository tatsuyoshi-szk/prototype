// ヘッダー：サービス名と、いまのステップ（日本語＋English）。留学生が「いまどこか」を、すぐ分かるようにする。
const STEPS = [
  { ja: '話す', en: 'Talk' },
  { ja: '答える', en: 'Rate' },
  { ja: '探す', en: 'Match' },
]

export default function Header({ step }) {
  return (
    <header className="site-header">
      <div className="brand">
        <span className="brand-ja">就活相談</span>
        <span className="brand-en">Job hunting guide for international students</span>
      </div>
      <ol className="steps" aria-label="ステップ / Steps">
        {STEPS.map((s, i) => {
          const n = i + 1
          const state = n < step ? 'done' : n === step ? 'now' : 'next'
          return (
            <li key={s.en} className={`step ${state}`} aria-current={n === step ? 'step' : undefined}>
              <span className="step-no">{n < step ? '✓' : n}</span>
              <span className="step-label">
                <span className="step-ja">{s.ja}</span>
                <span className="step-en">{s.en}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </header>
  )
}
