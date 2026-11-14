import { useEffect, useState } from 'react'
import { fetchRanking } from './api.js'

const isHttp = (u) => /^https?:\/\//.test(u || '')     // http(s) のリンクだけを出す

function Link({ url, children }) {
  return isHttp(url) ? <a href={url} target="_blank" rel="noopener noreferrer">{children}</a> : null
}

function Reason({ x }) {
  return (
    <li>
      {x.label}（{x.detail}）
      {x.basis && <div className="basis">{x.basis}</div>}
      {isHttp(x.url) && <div className="basis"><Link url={x.url}>出典を開く</Link></div>}
    </li>
  )
}

function Card({ c }) {
  return (
    <div className="card">
      <div className="top">
        <span className={'no' + (c.rank <= 3 ? ' top3' : '')} aria-label={`${c.rank}位`}>{c.rank}</span>
        <div className="who">
          <span className="nm">{c.name}</span>
          {c.industry && <span className="ind">{c.industry}</span>}
        </div>
        <div className="pt"><span className="pt-n">{c.score}</span><span className="pt-u">/100</span></div>
      </div>
      <div className="bar" role="img" aria-label={`${c.score}点（100点満点）`}><span style={{ width: `${Math.min(100, c.score)}%` }} /></div>
      {c.strengths.length > 0 && (
        <>
          <div className="good"><span className="mark" aria-hidden="true">✓</span>合うところ <span className="en">Good fit</span></div>
          <ul>{c.strengths.map((x, i) => <Reason key={i} x={x} />)}</ul>
        </>
      )}
      {c.concerns.length > 0 && (
        <>
          <div className="warn"><span className="mark" aria-hidden="true">!</span>気になるところ <span className="en">Check</span></div>
          <ul>{c.concerns.map((x, i) => <Reason key={i} x={x} />)}</ul>
        </>
      )}
      <div className="meta">
        {c.unknown_count
          ? `共通項目のうち、根拠が見つからなかったもの：${c.unknown_count}個（基準どおり低い点で計算）`
          : '共通項目は、すべて根拠あり'}
        {(c.sources || []).filter(isHttp).map((u, i) => (
          <span key={u}>{i ? '　' : '　企業の紹介の出典：'}<Link url={u}>[{i + 1}]</Link></span>
        ))}
      </div>
    </div>
  )
}

// 「譲れない」条件での絞り込みの結果（条件がなければ何も出さない）
function Screening({ s }) {
  if (!s || !s.labels?.length) return null
  return (
    <div className="screening">
      <div>
        <b>譲れない条件：</b>{s.labels.join('、')}<br />
        {s.total}社のうち、すべて満たした企業は <b>{s.passed}社</b> です（4点以上で、根拠が確認できた企業だけを残しています）。
        {s.passed === 0 && '条件を減らすと、企業が見つかりやすくなります。'}
      </div>
      {s.excluded.length > 0 && (
        <details>
          <summary>除かれた企業（{s.excluded.length}社）と、満たさなかった条件</summary>
          <ul>
            {s.excluded.map((e) => (
              <li key={e.name}>{e.name}：{e.failed.map((f) => `${f.label}（${f.reason}）`).join('、')}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

// 調査中の表示（経過時間つき）
function Progress({ info }) {
  const m = Math.floor((info.elapsed || 0) / 60), sec = (info.elapsed || 0) % 60
  return (
    <div className="progress-box">
      <div className="wait-title">現在調査中です… <span className="en">Searching</span></div>
      <div className="wait-time">経過 <span className="num">{m}:{String(sec).padStart(2, '0')}</span></div>
      <div className="note">全部で3〜5分ほどかかります。このページを開いたままにしてください。</div>
    </div>
  )
}

// アンケートのあと：企業の調査が終わるのを待って（定期的に確認する）、上位をカードで表示する。
export default function Result({ sid, ranking: initial }) {
  const [ranking, setRanking] = useState(initial || null)
  const [info, setInfo] = useState({ stage: 'select', detail: '準備しています', elapsed: 0 })
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
      <div className="msg system">アンケートにご協力ありがとうございました。 / Thank you!</div>
      {!ranking && !error && <Progress info={info} />}
      {error && (
        <>
          <div className="msg error" role="alert">{error}</div>
          <button className="btn" onClick={() => setAttempt((n) => n + 1)}>もう一度探す</button>
        </>
      )}
      {ranking && (
        <div className="rank">
          <h2>{ranking.top.length ? `あなたに合う企業 ${ranking.top.length}社` : '条件に合う企業が見つかりませんでした'} <span className="en">Your matches</span></h2>
          <div className="note">就活軸：{(ranking.axes || []).join('、')}</div>
          <Screening s={ranking.screening} />
          {ranking.top.map((c) => <Card key={c.id} c={c} />)}
          {ranking.others?.length > 0 && (
            <div className="others">
              ほかの企業：{ranking.others.map((o) => `${o.rank}位 ${o.name}（${o.score}点）`).join('、')}
            </div>
          )}
          <div className="note">
            {ranking.dummy
              ? `これは動作確認用のダミーデータです。企業はすべて架空で、実在の企業とは関係ありません。対象は ${ranking.companies_count}社です。`
              : `あなたの就活軸に合わせてAIが選んだ${ranking.companies_count}社を、公開情報をもとにWebで調べて採点したものです。誤りや古い情報が含まれることがあります（調査日：${ranking.collected_to}）。順位は、この${ranking.companies_count}社の中でのものです。${ranking.failed?.length ? `（調べられなかった企業：${ranking.failed.join('、')}）` : ''}`}
          </div>
        </div>
      )}
    </>
  )
}
