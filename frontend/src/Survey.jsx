import { useEffect, useState } from 'react'
import { getSurvey, submitSurvey } from './api.js'

// 重み付けアンケート：全項目に 1〜5 で答えると送信できる。
export default function Survey({ sid, onDone }) {
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

  if (error && !survey) return <div className="msg error">{error}</div>
  if (!survey) return <div className="msg system">アンケートを読み込み中…</div>

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
      setError(`まだ選んでいない項目が ${miss.length} 個あります。赤い行を選んでください。`)
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
        <small>{scale.map((s) => `${s.value}：${s.label}`).join(' / ')}</small>
      </p>
      <p className="must-help">
        <b>「譲れない」</b>にチェックした項目は、<b>絞り込みの条件</b>になります。その項目で<b>4点以上（根拠が確認できた企業）</b>だけが、結果に残ります。重みは、最大（{hi}点）として扱います。
        チェックが多いほど、残る企業は少なくなります。
      </p>
      <div className="sheet">
        <div className="row head">
          <div />
          {scale.map((s) => <div key={s.value}>{s.value}<br />{s.label}</div>)}
          <div>譲れない<br />Must-have</div>
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
            <label className="must" title="この項目を、絞り込みの条件にする">
              <input
                type="checkbox"
                checked={must.includes(q.id)}
                onChange={(e) => {
                  setMust((m) => (e.target.checked ? [...m, q.id] : m.filter((x) => x !== q.id)))
                  if (e.target.checked) setAnswers((a) => ({ ...a, [q.id]: hi }))      // 譲れない項目は、最大の点数にする
                }}
              />
              <span>譲れない<small>Must-have</small></span>
            </label>
          </div>
        ))}
      </div>
      {error && <div className="msg error" role="alert">{error}</div>}
      <div className="footer">
        <span className="progress">{done} / {total} 項目 回答済み　／　譲れない条件：{must.length}個</span>
        <button className="btn" type="submit" disabled={busy}>{busy ? '送信中…' : '結果を見る'}</button>
      </div>
    </form>
  )
}
