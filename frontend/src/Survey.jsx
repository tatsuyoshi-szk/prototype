import { useEffect, useState } from 'react'
import { getSurvey, submitSurvey } from './api.js'
import { useT } from './i18n.jsx'

// 重み付けアンケート：全項目に 1〜5 で答えると送信できる。項目名・説明・段階の言葉は、サーバーが会話の言語で返す。
export default function Survey({ sid, onDone }) {
  const t = useT()
  const [survey, setSurvey] = useState(null)
  const [answers, setAnswers] = useState({})
  const [missing, setMissing] = useState([])
  const [must, setMust] = useState([])      // 「譲れない」にチェックした項目のid
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getSurvey(sid)
      .then((d) => setSurvey(d.survey))
      .catch((e) => (e.data?.answered ? onDone() : setError(e.message)))
  }, [sid])

  if (error && !survey) return <div className="msg error" role="alert">{error}</div>
  if (!survey) return <div className="msg system">{t.surveyLoading}</div>

  const total = survey.questions.length
  const done = survey.questions.filter((q) => answers[q.id]).length
  const scale = survey.scale
  const lo = scale[0].value
  const hi = scale[scale.length - 1].value

  async function submit(e) {
    e.preventDefault()
    const miss = survey.questions.filter((q) => !answers[q.id]).map((q) => q.id)
    setMissing(miss)
    if (miss.length) {
      setError(t.missing(miss.length))
      return
    }
    setError('')
    setBusy(true)
    try {
      await submitSurvey(sid, answers, must)
      onDone()
    } catch (err) {
      if (err.data?.answered) return onDone()
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="survey" onSubmit={submit}>
      <h2>{survey.title}</h2>
      <p className="lead">
        {survey.lead.split('\n').map((l, i) => <span key={i}>{l}<br /></span>)}
        <small>{scale.map((s) => `${s.value}: ${s.label}`).join(' / ')}</small>
      </p>
      <p className="must-help">{t.mustHelp(hi)}</p>
      <div className="sheet">
        <div className="row head">
          <div />
          {scale.map((s) => <div key={s.value}>{s.value}<br />{s.label}</div>)}
          <div>{t.mustHead[0]}<br />{t.mustHead[1]}</div>
        </div>
        {survey.questions.map((q, i) => (
          <div key={q.id} className={'row' + (missing.includes(q.id) && !answers[q.id] ? ' missing' : '')}>
            <div className="item">
              <span className="num">{i + 1}</span>
              <span className="name">{q.name}</span>
              {q.explain && <span className="explain">{q.explain}</span>}
            </div>
            {scale.map((s) => (
              <label key={s.value} className="opt" title={s.label}>
                <input
                  type="radio"
                  name={q.id}
                  value={s.value}
                  checked={answers[q.id] === s.value}
                  disabled={must.includes(q.id)}
                  onChange={() => setAnswers((a) => ({ ...a, [q.id]: s.value }))}
                />
                <span>{s.value}{(s.value === lo || s.value === hi) && <small>{s.label}</small>}</span>
              </label>
            ))}
            <label className="must" title={t.mustTitle}>
              <input
                type="checkbox"
                checked={must.includes(q.id)}
                onChange={(e) => {
                  setMust((m) => (e.target.checked ? [...m, q.id] : m.filter((x) => x !== q.id)))
                  if (e.target.checked) setAnswers((a) => ({ ...a, [q.id]: hi }))      // 譲れない項目は、最大の点数にする
                }}
              />
              <span>{t.mustHead[0]}<small>{t.mustHead[1]}</small></span>
            </label>
          </div>
        ))}
      </div>
      {error && <div className="msg error" role="alert">{error}</div>}
      <div className="footer">
        <span className="progress">{t.progress(done, total, must.length)}</span>
        <button className="btn" type="submit" disabled={busy}>{busy ? t.submitting : t.submit}</button>
      </div>
    </form>
  )
}
