import { useEffect, useState } from 'react'
import { getSession } from './api.js'
import Chat from './Chat.jsx'
import Header from './Header.jsx'
import Survey from './Survey.jsx'
import Result from './Result.jsx'

// 画面の流れ：chat（会話）→ done（軸の確認）→ survey（アンケート）→ result（合う企業）
// ?sid= があれば、サーバーから会話を復元して、続きの画面から始める。
function setSidInUrl(sid) {
  history.replaceState(null, '', sid ? `/?sid=${encodeURIComponent(sid)}` : '/')
}

const FRESH = { phase: 'chat', sid: null, transcript: [], axes: [] }

export default function App() {
  const [state, setState] = useState({ phase: 'loading', sid: null, transcript: [], axes: [] })

  useEffect(() => {
    const sid = new URLSearchParams(location.search).get('sid')
    if (!sid) {
      setState(FRESH)
      return
    }
    getSession(sid)
      .then((d) => {
        const phase = !d.finished ? 'chat' : d.answered ? 'result' : 'done'
        setState({ phase, sid, transcript: d.transcript || [], axes: d.axes || [], ranking: d.ranking })
      })
      .catch(() => setState({ phase: 'lost', sid: null, transcript: [], axes: [] }))
  }, [])

  const go = (patch) => setState((s) => ({ ...s, ...patch }))
  // key を変えないよう、sid は state にだけ反映する（URL は書き換えるが、Chat は作り直さない）
  const onSid = (sid) => { setSidInUrl(sid); go({ sid }) }

  if (state.phase === 'loading') {
    return <div id="app"><Header step={1} /><div className="log"><div className="msg system">読み込み中… / Loading…</div></div></div>
  }
  if (state.phase === 'lost') {
    return (
      <div id="app">
        <Header step={1} />
        <div className="log">
          <div className="msg error" role="alert">この会話が見つかりません（サーバーを再起動すると、途中の会話は消えます）。</div>
          <button className="btn" onClick={() => { setSidInUrl(null); setState(FRESH) }}>新しく始める</button>
        </div>
      </div>
    )
  }

  return (
    <div id="app">
      <Header step={state.phase === 'chat' ? 1 : state.phase === 'result' ? 3 : 2} />
      <Chat
        sid={state.sid}
        initial={state.transcript}
        locked={state.phase !== 'chat'}
        fold={state.phase === 'survey' || state.phase === 'result'}
        onSid={onSid}
        onFinished={(axes) => go({ phase: 'done', axes })}
      >
        {state.phase === 'done' && (
          <div className="panel">
            <h2>会話が終わりました。あなたの就活軸 <span className="en">Your priorities</span></h2>
            <ul>{state.axes.map((a) => <li key={a}>{a}</li>)}</ul>
            <button className="btn" onClick={() => go({ phase: 'survey' })}>アンケートに進む <span className="en">Next: Rate</span></button>
          </div>
        )}
        {state.phase === 'survey' && (
          <Survey sid={state.sid} onDone={() => go({ phase: 'result' })} />
        )}
        {state.phase === 'result' && <Result sid={state.sid} ranking={state.ranking} />}
      </Chat>
    </div>
  )
}
