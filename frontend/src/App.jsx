import { useEffect, useState } from 'react'
import { getSession } from './api.js'
import Chat from './Chat.jsx'
import Header from './Header.jsx'
import Survey from './Survey.jsx'
import Result from './Result.jsx'
import { LangContext, STRINGS, setCurrentLang } from './i18n.jsx'

// 画面の流れ：chat（会話）→ done（軸の確認）→ survey（アンケート）→ result（合う企業）
// ?sid= があれば、サーバーから会話を復元して、続きの画面から始める。
// 画面の言語（lang）は、サーバーが会話の言語から判定して返す。
function setSidInUrl(sid) {
  history.replaceState(null, '', sid ? `/?sid=${encodeURIComponent(sid)}` : '/')
}

const FRESH = { phase: 'chat', sid: null, transcript: [], axes: [], lang: 'ja' }

export default function App() {
  const [state, setState] = useState({ phase: 'loading', sid: null, transcript: [], axes: [], lang: 'ja' })
  const lang = state.lang === 'en' ? 'en' : 'ja'
  setCurrentLang(lang)                      // api.js のエラー文言用
  const t = STRINGS[lang]

  useEffect(() => {
    const sid = new URLSearchParams(location.search).get('sid')
    if (!sid) {
      setState(FRESH)
      return
    }
    getSession(sid)
      .then((d) => {
        const phase = !d.finished ? 'chat' : d.answered ? 'result' : 'done'
        setState({ phase, sid, transcript: d.transcript || [], axes: d.axes || [], ranking: d.ranking, lang: d.lang || 'ja' })
      })
      .catch(() => setState({ ...FRESH, phase: 'lost' }))
  }, [])

  const go = (patch) => setState((s) => ({ ...s, ...patch }))
  // key を変えないよう、sid は state にだけ反映する（URL は書き換えるが、Chat は作り直さない）
  const onSid = (sid) => { setSidInUrl(sid); go({ sid }) }

  let body
  if (state.phase === 'loading') {
    body = (
      <>
        <Header step={1} />
        <div className="log"><div className="msg system">{t.loading}</div></div>
      </>
    )
  } else if (state.phase === 'lost') {
    body = (
      <>
        <Header step={1} />
        <div className="log">
          <div className="msg error" role="alert">{t.lost}</div>
          <button className="btn" onClick={() => { setSidInUrl(null); setState(FRESH) }}>{t.startNew}</button>
        </div>
      </>
    )
  } else {
    body = (
      <>
        <Header step={state.phase === 'chat' ? 1 : state.phase === 'result' ? 3 : 2} />
        <Chat
          sid={state.sid}
          initial={state.transcript}
          locked={state.phase !== 'chat'}
          fold={state.phase === 'survey' || state.phase === 'result'}
          onSid={onSid}
          onLang={(l) => go({ lang: l })}
          onFinished={(axes) => go({ phase: 'done', axes })}
        >
          {state.phase === 'done' && (
            <div className="panel">
              <h2>{t.doneTitle} <span className="en">{t.doneTitleEn}</span></h2>
              <ul>{state.axes.map((a) => <li key={a}>{a}</li>)}</ul>
              <button className="btn" onClick={() => go({ phase: 'survey' })}>{t.next} <span className="en">{t.nextEn}</span></button>
            </div>
          )}
          {state.phase === 'survey' && <Survey sid={state.sid} onDone={() => go({ phase: 'result' })} />}
          {state.phase === 'result' && <Result sid={state.sid} ranking={state.ranking} />}
        </Chat>
      </>
    )
  }

  return (
    <LangContext.Provider value={lang}>
      <div id="app" lang={lang}>{body}</div>
    </LangContext.Provider>
  )
}
