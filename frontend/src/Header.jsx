import { useT } from './i18n.jsx'

// ヘッダー：サービス名と、いまのステップ（日本語＋English）。留学生が「いまどこか」を、すぐ分かるようにする。
export default function Header({ step }) {
  const t = useT()
  return (
    <header className="site-header">
      <div className="brand">
        <span className="brand-ja">就活相談</span>
        <span className="brand-en">{t.brandSub}</span>
      </div>
      <ol className="steps" aria-label={t.stepsAria}>
        {t.steps.map(([main, sub], i) => {
          const n = i + 1
          const state = n < step ? 'done' : n === step ? 'now' : 'next'
          return (
            <li key={sub} className={`step ${state}`} aria-current={n === step ? 'step' : undefined}>
              <span className="step-no">{n < step ? '✓' : n}</span>
              <span className="step-label">
                <span className="step-ja">{main}</span>
                <span className="step-en">{sub}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </header>
  )
}
