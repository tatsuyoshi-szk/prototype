import { useEffect, useRef, useState } from 'react'
import { sendChat } from './api.js'

// 会話の画面。children には、会話のあとに続く画面（軸の確認、アンケート、結果）が入る。
export default function Chat({ sid, initial, locked, onSid, onFinished, children }) {
  const [messages, setMessages] = useState(() =>
    initial.length
      ? initial.map((t) => ({ role: t.role === 'student' ? 'student' : 'advisor', text: t.text }))
      : [{ role: 'system', text: 'まず、自分のこと（出身、やりたいこと、今の気持ちなど）を自由に書いてください。' }],
  )
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sidRef = useRef(sid)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages, busy, error, children])

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

  return (
    <>
      <div className="log" aria-live="polite">
        {messages.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
        {busy && <div className="msg system">考え中…（少し時間がかかります）</div>}
        {error && <div className="msg error">{error}</div>}
        {children}
        <div ref={endRef} />
      </div>
      {!locked && (
        <form className="form" onSubmit={(e) => { e.preventDefault(); submit() }}>
          <textarea
            rows={2}
            value={text}
            disabled={busy}
            autoFocus
            placeholder="ここに入力してください（Enterで送信、Shift+Enterで改行）"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="submit" disabled={busy || !text.trim()}>送信</button>
        </form>
      )}
    </>
  )
}
