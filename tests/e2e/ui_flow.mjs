// 新しい画面の操作の通し確認（擬似のAPI。AIは呼ばない）
import { chromium } from 'playwright-core'
import fs from 'node:fs'
const fx = JSON.parse(fs.readFileSync('fixtures.json', 'utf-8'))
const NQ = fx.survey.questions.length      // 項目数（共通14個 + 軸の数）
let ok = true
const check = (n, c) => { ok &&= !!c; console.log((c ? 'OK  ' : 'NG  ') + n) }

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 900 } })
let posted = null, ranks = 0
await page.route('**/api/**', async (route) => {
  const req = route.request(); const u = new URL(req.url())
  const json = (o, s = 200) => route.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(o) })
  if (u.pathname === '/api/chat') return json({ session_id: 'BBBBBBBBBBBBBBBBBBBBBB', kind: 'finish', message: '確認ありがとうございます。', finished: true, axes: fx.axes })
  if (u.pathname === '/api/survey' && req.method() === 'GET') return json({ survey: fx.survey })
  if (u.pathname === '/api/survey') { posted = JSON.parse(req.postData()); return json({ ok: true }) }
  if (u.pathname === '/api/rank') { ranks++; return ranks < 2 ? json({ state: 'running', stage: 'research', detail: 'x', elapsed: 5 }) : json({ state: 'done', ranking: fx.ranking }) }
  return route.continue()
})
await page.goto('http://127.0.0.1:5173/')
check('最初の画面に日英のあいさつ', (await page.locator('.hello span').count()) === 2)
check('ステップ1が現在', (await page.locator('.step.now .step-en').innerText()) === 'Talk')
check('送るボタンは、空のとき押せない', await page.locator('.form button').isDisabled())
await page.fill('textarea', 'こんにちは。ベトナムから来ました。')
check('入力すると押せる', !(await page.locator('.form button').isDisabled()))
await page.keyboard.press('Enter')
await page.waitForSelector('.panel .btn')
check('会話が終わると軸の確認', (await page.locator('.panel li').count()) === fx.axes.length)
check('ステップ2が現在', (await page.locator('.step.now .step-en').innerText()) === 'Rate')
check('入力欄が消える', (await page.locator('.form').count()) === 0)
check('URLに sid が入る', page.url().includes('sid=BBBB'))
await page.click('.panel .btn')
await page.waitForSelector('.sheet .row:not(.head)')
check('会話が折りたたまれる', (await page.locator('details.history').count()) === 1 && !(await page.locator('details.history').evaluate((e) => e.open)))
const rows = await page.$$('.sheet .row:not(.head)')
check('アンケートの項目数', rows.length === NQ)
// 未回答のまま送ると、エラーが出て、赤い行になる
await page.click('button[type=submit]')
check('未回答はエラー（role=alert）', (await page.locator('.msg.error[role=alert]').count()) === 1 && (await page.locator('.row.missing').count()) === NQ)
// 「譲れない」：チェックで5点＋固定
const r2 = page.locator('.sheet .row:not(.head)').nth(3)
await r2.locator('label.must input').check()
check('譲れない=ON で5点が選ばれる', await r2.locator('label.opt input[value="5"]').isChecked())
check('譲れない=ON で点数は固定', await r2.locator('label.opt input').evaluateAll((e) => e.every((x) => x.disabled)))
for (let i = 0; i < rows.length; i++) if (i !== 3) await page.locator('.sheet .row:not(.head)').nth(i).locator('label.opt input[value="3"]').check()
check('進み具合の表示', (await page.locator('.progress').innerText()).includes(`${NQ} / ${NQ}`))
await page.click('button[type=submit]')
await page.waitForSelector('.progress-box')
check('送信内容: 全項目の回答と must_have', posted && Object.keys(posted.answers).length === NQ && posted.must_have.length === 1 && posted.answers[posted.must_have[0]] === 5)
check('ステップ3が現在', (await page.locator('.step.now .step-en').innerText()) === 'Match')
check('調査中の表示', (await page.locator('.wait-title').innerText()).includes('調査中'))
await page.waitForSelector('.card', { timeout: 15000 })
check('結果のカード5枚', (await page.locator('.card').count()) === 5)
check('点数のバー', (await page.locator('.card .bar span').count()) === 5)
check('出典リンクは新しいタブ・noopener', (await page.locator('.card a[rel*=noopener][target=_blank]').count()) > 5)
check('結果は先頭（見出し）から見える', await page.locator('.rank h2').isVisible() && (await page.locator('.rank h2').boundingBox()).y < 400)
await page.setViewportSize({ width: 390, height: 844 })
check('スマホ幅で横はみ出しなし', !(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)))
await browser.close()
console.log(ok ? 'ALL OK' : 'FAILED')
