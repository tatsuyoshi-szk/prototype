import { useEffect, useRef, useState } from 'react'
import { sendChat } from './api.js'

// 最初の画面：多言語のあいさつ。次にすることは、「自分のことを書く」の1つだけ。
function Welcome() {
  return (
    <section className="welcome" aria-label="はじめに / Welcome">
      <p className="hello" aria-label="こんにちは。Hello. Xin chào. 你好. 안녕하세요.">
        <span lang="ja">こんにちは</span>
        <span lang="en">Hello</span>
        <span lang="vi">Xin chào</span>
        <span lang="zh">你好</span>
        <span lang="ko">안녕하세요</span>
      </p>
      <h1>あなたに合う会社を、一緒に探しましょう。</h1>
      <p className="lead">
        <span>まず、あなたのことを、下の入力欄に書いてください。</span>
        <span>やさしい日本語で大丈夫です。</span>
      </p>
      <ul className="hints">
        <li>どこから来ましたか</li>
        <li>日本で、どんな仕事がしたいですか</li>
        <li>いまの気持ち（不安、楽しみ）</li>
      </ul>
    </section>
  )
}

// 会話の画面。children には、会話のあとに続く画面（軸の確認、アンケート、結果）が入る。
export default function Chat({ sid, initial, locked, fold, onSid, onFinished, children }) {
  const [messages, setMessages] = useState(() =>
    initial.map((t) => ({ role: t.role === 'student' ? 'student' : 'advisor', text: t.text })),
  )
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sidRef = useRef(sid)
  const endRef = useRef(null)
  const afterRef = useRef(null)      // 会話のあとに続く画面（軸の確認・アンケート・結果）の先頭

  useEffect(() => {
    // アンケート・結果は、先頭から見せる（会話の末尾までスクロールしない）。会話中は、最新の発言まで
    const target = fold ? afterRef.current : endRef.current
    target?.scrollIntoView({ block: fold ? 'start' : 'end' })
  }, [messages, busy, error, children, fold])

  async function submit() {
    const t = text.trim()
    if (!t || busy || locked) return
    setError('')
    setBusy(true)
    setMessages((m) => [...m, { role: 'student', text: t }])
    setText('')
    try {
      const data = await sendChat(sidRef.current, t)
      sidRef.current = data.session_id
      onSid(data.session_id)
      setMessages((m) => [...m, { role: 'advisor', text: data.message }])
      if (data.finished) onFinished(data.axes || [])
    } catch (e) {
      // 失敗：送った文章を入力欄に戻して、もう一度送れるようにする
      if (e.data?.session_id) sidRef.current = e.data.session_id
      setMessages((m) => m.slice(0, -1))
      setText(t)
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function onKeyDown(e) {
    // 日本語入力の変換中の Enter は送信しない
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault()
      submit()
    }
  }

  const turns = messages.map((m, i) =>
    m.role === 'advisor' ? (
      <div key={i} className="turn advisor">
        <span className="avatar" aria-hidden="true">AI</span>
        <div className="msg advisor">{m.text}</div>
      </div>
    ) : (
      <div key={i} className="turn student">
        <div className="msg student">{m.text}</div>
      </div>
    ),
  )

  return (
    <>
      <div className="log" aria-live="polite">
        {messages.length === 0 && !busy && <Welcome />}
        {fold ? (
          // アンケート・結果のときは、会話を折りたたんで、結果を上に出す
          <details className="history">
            <summary>会話を見る <span className="en">Show conversation</span>（{messages.length}）</summary>
            <div className="history-body">{turns}</div>
          </details>
        ) : turns}
        {busy && <div className="msg system">考え中…（少し時間がかかります） / Thinking…</div>}
        {error && <div className="msg error" role="alert">{error}</div>}
        <div className="after" ref={afterRef}>{children}</div>
        <div ref={endRef} />
      </div>
      {!locked && (
        <form className="form" onSubmit={(e) => { e.preventDefault(); submit() }}>
          <textarea
            rows={2}
            value={text}
            disabled={busy}
            autoFocus
            aria-label="メッセージ / Message"
            placeholder="ここに書いてください（Enterで送る、Shift+Enterで改行）"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="submit" disabled={busy || !text.trim()}>送る</button>
        </form>
      )}
    </>
  )
}
