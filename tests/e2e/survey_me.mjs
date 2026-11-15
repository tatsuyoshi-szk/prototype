// 使い方: node survey_me.mjs <sid> [port]   （留学生役として、アンケートに答え、結果が出るまで待つ。本物のAPIを使う）
// 環境変数 MUST に、「譲れない」にする項目名の一部をカンマ区切りで書く（例：MUST=工場のDX,文化・宗教）
import { chromium } from 'playwright-core'

const sid = process.argv[2], base = `http://127.0.0.1:${process.argv[3] || 8000}`
const MUST = (process.env.MUST || '').split(',').filter(Boolean)
const AXIS_W = [5, 4, 4, 4, 3, 3]          // 就活軸の重み（上から順）
const W = { '外国籍社員の割合': 3, '外国籍役員': 2, '評価・等級': 4, '選考プロセスに英語': 3, '日本語のレベル': 3, '多言語': 3, 'ビザ': 3, '衣食住': 3,
  'コミュニティ': 2, '文化・宗教': 5, '長期帰国': 3, 'グローバル拠点': 3, '口コミサイト': 2, '外国人の口コミ': 2 }
const t0 = Date.now(), sec = () => Math.round((Date.now() - t0) / 1000)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 2600 } })
await page.goto(`${base}/?sid=${sid}`)
await page.waitForSelector('.panel .btn', { timeout: 15000 })
await page.click('.panel .btn')
await page.waitForSelector('.sheet .row:not(.head)')
let axisNo = 0
for (const row of await page.$$('.sheet .row:not(.head)')) {
  const name = await row.$eval('.name', (e) => e.innerText)
  let w
  if (name.includes('就活軸「')) w = AXIS_W[axisNo++] ?? 3
  else w = W[Object.keys(W).find((k) => name.includes(k))] ?? 3
  if (MUST.some((k) => name.includes(k))) {
    await row.$('label.must input').then((i) => i.check())
    console.log('譲れない', name.slice(0, 30))
  } else {
    await row.$(`label.opt input[value="${w}"]`).then((i) => i.check())
    console.log(w, name.slice(0, 30))
  }
}
await page.click('button[type=submit]')
await page.waitForSelector('.progress-box, .rank, .msg.error', { timeout: 30000 })
console.log(`[${sec()}s] 送信`)
await page.waitForSelector('.card, .screening, .msg.error', { timeout: 12 * 60 * 1000 })
console.log(`[${sec()}s] 結果`)
await page.waitForTimeout(500)
await page.screenshot({ path: 'me_result.png', fullPage: true })
console.log(await page.$eval('.rank', (e) => e.innerText).catch(async () => (await page.$$eval('.msg.error', (x) => x.map((y) => y.innerText))).join('\n')))
await browser.close()
