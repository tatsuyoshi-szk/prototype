// バックエンド（JSON API）を呼ぶ。失敗したときは、画面に出してよい文言を持った Error を投げる。
import { STRINGS, getCurrentLang } from './i18n.jsx'

async function call(path, options) {
  const t = STRINGS[getCurrentLang()]
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error(t.serverUnreachable)
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.error || t.genericError)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

const post = (path, body) =>
  call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const getSession = (sid) => call('/api/session?sid=' + encodeURIComponent(sid))
export const sendChat = (sessionId, message) => post('/api/chat', { session_id: sessionId, message })
export const getSurvey = (sid) => call('/api/survey?sid=' + encodeURIComponent(sid))
export const submitSurvey = (sessionId, answers, mustHave) =>
  post('/api/survey', { session_id: sessionId, answers, must_have: mustHave })
export const fetchRanking = (sessionId) => post('/api/rank', { session_id: sessionId })
