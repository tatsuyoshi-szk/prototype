// 画面の文言（日本語・英語）。言語は、サーバーが会話の言語から判定して返す（lang: 'ja' | 'en'）。
// 最初の画面（言語が決まる前）だけは、日英の両方を出す（Chat.jsx の Welcome）。
import { createContext, useContext } from 'react'

let current = 'ja'
export const setCurrentLang = (l) => { current = l === 'en' ? 'en' : 'ja' }
export const getCurrentLang = () => current          // api.js のエラー文言用
export const LangContext = createContext('ja')

const ja = {
  brandSub: 'Job hunting guide for international students',
  stepsAria: 'ステップ / Steps',
  steps: [['話す', 'Talk'], ['答える', 'Rate'], ['探す', 'Match']],      // [大きく出す方, 小さく出す方]
  loading: '読み込み中… / Loading…',
  lost: 'この会話が見つかりません（サーバーを再起動すると、途中の会話は消えます）。',
  startNew: '新しく始める',
  thinking: '考え中…（少し時間がかかります） / Thinking…',
  placeholder: 'ここに書いてください（Enterで送る、Shift+Enterで改行）',
  send: '送る',
  messageLabel: 'メッセージ / Message',
  showConv: '会話を見る',
  showConvEn: 'Show conversation',
  doneTitle: '会話が終わりました。あなたの就活軸',
  doneTitleEn: 'Your priorities',
  next: 'アンケートに進む',
  nextEn: 'Next: Rate',
  surveyLoading: 'アンケートを読み込み中…',
  mustHelp: (hi) => (
    <>
      <b>「譲れない」</b>にチェックした項目は、<b>絞り込みの条件</b>になります。その項目で<b>4点以上（根拠が確認できた企業）</b>だけが、結果に残ります。
      重みは、最大（{hi}点）として扱います。チェックが多いほど、残る企業は少なくなります。
    </>
  ),
  mustHead: ['譲れない', 'Must-have'],
  mustTitle: 'この項目を、絞り込みの条件にする',
  missing: (n) => `まだ選んでいない項目が ${n} 個あります。赤い行を選んでください。`,
  progress: (d, t, m) => `${d} / ${t} 項目 回答済み　／　譲れない条件：${m}個`,
  submit: '結果を見る',
  submitting: '送信中…',
  thanks: 'アンケートにご協力ありがとうございました。 / Thank you!',
  waitTitle: '現在調査中です…',
  waitEn: 'Searching',
  elapsed: '経過',
  waitNote: '全部で3〜5分ほどかかります。このページを開いたままにしてください。',
  retry: 'もう一度探す',
  matchesTitle: (n) => (n ? `あなたに合う企業 ${n}社` : '条件に合う企業が見つかりませんでした'),
  matchesEn: 'Your matches',
  axesLabel: '就活軸：',
  good: '合うところ',
  goodEn: 'Good fit',
  warn: '気になるところ',
  warnEn: 'Check',
  openSource: '出典を開く',
  rankAria: (r) => `${r}位`,
  barAria: (s) => `${s}点（100点満点）`,
  unknownCount: (n) => (n ? `共通項目のうち、根拠が見つからなかったもの：${n}個（重みから外して、残りの項目で計算）` : '共通項目は、すべて根拠あり'),
  sourcesLabel: '企業の紹介の出典：',
  screenTitle: '譲れない条件：',
  screenResult: (total, passed) => (
    <>{total}社のうち、すべて満たした企業は <b>{passed}社</b> です（4点以上で、根拠が確認できたものだけを「満たす」としています）。{passed < total && ' 足りないぶんは、満たさない条件が少ない企業を、印をつけて後ろに加えています。'}</>
  ),
  screenLess: '条件を減らすと、条件をすべて満たす企業が見つかりやすくなります。',
  excluded: (n) => `条件を満たさなかった企業（${n}社）と、その条件`,
  unmetTitle: '満たさなかった「譲れない」条件',
  others: 'ほかの企業：',
  otherItem: (o, name) => `${o.rank}位 ${name}（${o.score}点）${o.unmet ? '※条件を一部満たさない' : ''}${o.low_evidence ? '※情報不足' : ''}`,
  knownCount: (n) => `点数の計算に使った項目（根拠のあるもの）：${n}個`,
  lowEvidence: '根拠のある項目が少ないため、順位は参考です（情報不足）',
  failedPrefix: (names) => `（調べられなかった企業：${names}）`,
  footNote: (n, date) => `あなたの就活軸に合わせてAIが選んだ${n}社を、公開情報をもとにWebで調べて採点したものです。誤りや古い情報が含まれることがあります（調査日：${date}）。順位は、この${n}社の中でのものです。`,
  footDummy: (n) => `これは動作確認用のダミーデータです。企業はすべて架空で、実在の企業とは関係ありません。対象は ${n}社です。`,
  detail: (label, d) => `${label}（${d}）`,
  sep: '、',
  serverUnreachable: 'サーバーにつながりません。サーバーが動いているか確認してください。',
  genericError: 'エラーが起きました。もう一度お試しください。',
}

const en = {
  brandSub: 'Job hunting guide for international students',
  stepsAria: 'Steps / ステップ',
  steps: [['Talk', '話す'], ['Rate', '答える'], ['Match', '探す']],
  loading: 'Loading… / 読み込み中…',
  lost: 'This conversation was not found. Conversations in progress are lost when the server restarts.',
  startNew: 'Start again',
  thinking: 'Thinking… (this may take a moment)',
  placeholder: 'Write here (Enter to send, Shift+Enter for a new line)',
  send: 'Send',
  messageLabel: 'Message',
  showConv: 'Show conversation',
  showConvEn: '会話を見る',
  doneTitle: 'Our conversation is done. Your priorities',
  doneTitleEn: 'あなたの就活軸',
  next: 'Go to the survey',
  nextEn: 'アンケートへ',
  surveyLoading: 'Loading the survey…',
  mustHelp: (hi) => (
    <>
      Items you tick as <b>Must-have</b> become <b>filters</b>. Only companies that score <b>4 or higher on that item (with evidence)</b> stay in your results.
      A must-have is also weighted at the maximum ({hi}). The more you tick, the fewer companies remain.
    </>
  ),
  mustHead: ['Must-have', '譲れない'],
  mustTitle: 'Use this item as a filter',
  missing: (n) => `${n} item(s) are still not answered. Please choose an answer for the rows in red.`,
  progress: (d, t, m) => `${d} / ${t} answered　/　Must-haves: ${m}`,
  submit: 'See my results',
  submitting: 'Sending…',
  thanks: 'Thank you for answering the survey. / ご協力ありがとうございました。',
  waitTitle: 'Searching now…',
  waitEn: '調査中',
  elapsed: 'Elapsed',
  waitNote: 'This takes about 3 to 5 minutes in total. Please keep this page open.',
  retry: 'Try again',
  matchesTitle: (n) => (n ? `Your top ${n} companies` : 'No companies matched your must-haves'),
  matchesEn: 'あなたに合う企業',
  axesLabel: 'Your priorities: ',
  good: 'Good fit',
  goodEn: '合うところ',
  warn: 'Check',
  warnEn: '気になるところ',
  openSource: 'Open source',
  rankAria: (r) => `Rank ${r}`,
  barAria: (s) => `${s} out of 100`,
  unknownCount: (n) => (n ? `Common items with no evidence found: ${n} (left out of the weighting; the score uses the other items)` : 'Evidence was found for every common item'),
  sourcesLabel: 'Company overview sources: ',
  screenTitle: 'Your must-haves: ',
  screenResult: (total, passed) => (
    <>Of {total} companies, <b>{passed}</b> meet all of them (a must-have counts as met only with a score of 4 or higher and confirmed evidence).{passed < total && ' To fill the list, companies that miss the fewest must-haves are added at the end, with a note.'}</>
  ),
  screenLess: 'Try ticking fewer must-haves to see more companies.',
  excluded: (n) => `Companies that did not meet every must-have (${n}) and what they missed`,
  unmetTitle: 'Must-haves this company does not meet',
  others: 'Other companies: ',
  otherItem: (o, name) => `#${o.rank} ${name} (${o.score})${o.unmet ? ' [misses a must-have]' : ''}${o.low_evidence ? ' [little evidence]' : ''}`,
  knownCount: (n) => `Items used for the score (those with evidence): ${n}`,
  lowEvidence: 'Few items have evidence, so treat this rank as a rough guide (little evidence)',
  failedPrefix: (names) => ` (Could not research: ${names})`,
  footNote: (n, date) => `The AI chose these ${n} companies for your priorities, researched them on the web from public information, and scored them. They may contain mistakes or old information (researched: ${date}). Ranks are only among these ${n} companies.`,
  footDummy: (n) => `This is sample data for testing. All ${n} companies are fictional.`,
  detail: (label, d) => `${label} (${d})`,
  sep: ', ',
  serverUnreachable: 'Cannot reach the server. Please check that the server is running.',
  genericError: 'Something went wrong. Please try again.',
}

export const STRINGS = { ja, en }
export const useT = () => STRINGS[useContext(LangContext)] || ja
