import { useEffect, useState } from 'react'
import { fetchRanking } from './api.js'
import { LangContext, useT } from './i18n.jsx'
import { useContext } from 'react'

const isHttp = (u) => /^https?:\/\//.test(u || '')     // http(s) のリンクだけを出す

function Link({ url, children }) {
  return isHttp(url) ? <a href={url} target="_blank" rel="noopener noreferrer">{children}</a> : null
}

function Reason({ x }) {
  const t = useT()
  return (
    <li>
      {t.detail(x.label, x.detail)}
      {x.basis && <div className="basis">{x.basis}</div>}
      {isHttp(x.url) && <div className="basis"><Link url={x.url}>{t.openSource}</Link></div>}
    </li>
  )
}

// 英語のときは、英語名を大きく、日本語名を小さく出す（英語名がなければ、日本語名だけ）
function useNames() {
  const lang = useContext(LangContext)
  return (o) => (lang === 'en' && o.name_en
    ? { main: o.name_en, sub: o.name_en === o.name ? '' : o.name, industry: o.industry_en || o.industry }
    : { main: o.name, sub: '', industry: o.industry })
}

function Card({ c }) {
  const t = useT()
  const names = useNames()(c)
  return (
    <div className="card">
      <div className="top">
        <span className={'no' + (c.rank <= 3 ? ' top3' : '')} aria-label={t.rankAria(c.rank)}>{c.rank}</span>
        <div className="who">
          <span className="nm">{names.main}</span>
          {names.sub && <span className="ind">{names.sub}</span>}
          {names.industry && <span className="ind">{names.industry}</span>}
        </div>
        <div className="pt"><span className="pt-n">{c.score}</span><span className="pt-u">/100</span></div>
      </div>
      <div className="bar" role="img" aria-label={t.barAria(c.score)}><span style={{ width: `${Math.min(100, c.score)}%` }} /></div>
      {c.low_evidence && <div className="lowev">{t.lowEvidence}</div>}
      <div className="compare">{t.knownCount(c.known_count)}</div>
      {c.strengths.length > 0 && (
        <>
          <div className="good"><span className="mark" aria-hidden="true">✓</span>{t.good} <span className="en">{t.goodEn}</span></div>
          <ul>{c.strengths.map((x, i) => <Reason key={i} x={x} />)}</ul>
        </>
      )}
      {c.concerns.length > 0 && (
        <>
          <div className="warn"><span className="mark" aria-hidden="true">!</span>{t.warn} <span className="en">{t.warnEn}</span></div>
          <ul>{c.concerns.map((x, i) => <Reason key={i} x={x} />)}</ul>
        </>
      )}
      <div className="meta">
        {t.unknownCount(c.unknown_count)}
        {(c.sources || []).filter(isHttp).map((u, i) => (
          <span key={u}>{i ? '　' : `　${t.sourcesLabel}`}<Link url={u}>[{i + 1}]</Link></span>
        ))}
      </div>
    </div>
  )
}

// 「譲れない」条件での絞り込みの結果（条件がなければ何も出さない）
function Screening({ s }) {
  const t = useT()
  const names = useNames()
  if (!s || !s.labels?.length) return null
  return (
    <div className="screening">
      <div>
        <b>{t.screenTitle}</b>{s.labels.join(t.sep)}<br />
        {t.screenResult(s.total, s.passed)}
        {s.passed === 0 && ` ${t.screenLess}`}
      </div>
      {s.excluded.length > 0 && (
        <details>
          <summary>{t.excluded(s.excluded.length)}</summary>
          <ul>
            {s.excluded.map((e) => (
              <li key={e.name}>{names(e).main}: {e.failed.map((f) => t.detail(f.label, f.reason)).join(t.sep)}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

// 調査中の表示（経過時間つき）
function Progress({ info }) {
  const t = useT()
  const m = Math.floor((info.elapsed || 0) / 60), sec = (info.elapsed || 0) % 60
  return (
    <div className="progress-box">
      <div className="wait-title">{t.waitTitle} <span className="en">{t.waitEn}</span></div>
      <div className="wait-time">{t.elapsed} <span className="num">{m}:{String(sec).padStart(2, '0')}</span></div>
      <div className="note">{t.waitNote}</div>
    </div>
  )
}

// アンケートのあと：企業の調査が終わるのを待って（定期的に確認する）、上位をカードで表示する。
export default function Result({ sid, ranking: initial }) {
  const t = useT()
  const names = useNames()
  const [ranking, setRanking] = useState(initial || null)
  const [info, setInfo] = useState({ stage: 'select', detail: '', elapsed: 0 })
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (ranking) return
    let stop = false
    let timer
    const poll = async () => {
      try {
        const d = await fetchRanking(sid)
        if (stop) return
        if (d.state === 'done') { setRanking(d.ranking); return }
        setInfo(d)
        timer = setTimeout(poll, 3000)
      } catch (e) {
        if (!stop) setError(e.message)
      }
    }
    setError('')
    poll()
    return () => { stop = true; clearTimeout(timer) }
  }, [sid, attempt])

  return (
    <>
      <div className="msg system">{t.thanks}</div>
      {!ranking && !error && <Progress info={info} />}
      {error && (
        <>
          <div className="msg error" role="alert">{error}</div>
          <button className="btn" onClick={() => setAttempt((n) => n + 1)}>{t.retry}</button>
        </>
      )}
      {ranking && (
        <div className="rank">
          <h2>{t.matchesTitle(ranking.top.length)} <span className="en">{t.matchesEn}</span></h2>
          <div className="note">{t.axesLabel}{(ranking.axes || []).join(t.sep)}</div>
          <Screening s={ranking.screening} />
          {ranking.top.map((c) => <Card key={c.id} c={c} />)}
          {ranking.others?.length > 0 && (
            <div className="others">
              {t.others}{ranking.others.map((o) => t.otherItem(o, names(o).main)).join(t.sep)}
            </div>
          )}
          <div className="note">
            {ranking.dummy
              ? t.footDummy(ranking.companies_count)
              : t.footNote(ranking.companies_count, ranking.collected_to)}
            {ranking.failed?.length ? t.failedPrefix(ranking.failed.join(t.sep)) : ''}
          </div>
        </div>
      )}
    </>
  )
}
