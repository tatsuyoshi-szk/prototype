// 使い方: node survey_me.mjs <sid> [port]   （留学生役として、アンケートに答え、結果が出るまで待つ。本物のAPIを使う）
import { chromium } from 'playwright-core'

const sid = process.argv[2], base = `http://127.0.0.1:${process.argv[3] || 8001}`
const W = { '若手から大きな仕事': 5, '研修と先輩': 4, '日中の進出支援': 4, 'いろいろな業界': 4, 'データ分析': 3, '優秀な仲間': 3,
  '外国籍社員の割合': 3, '外国籍役員': 3, '評価・等級': 5, '選考プロセスに英語': 2, '日本語のレベル': 3, '多言語': 2, 'ビザ': 4, '衣食住': 2,
  'コミュニティ': 3, '文化・宗教': 2, '長期帰国': 2, 'グローバル拠点': 4, '口コミサイト': 3, '外国人の口コミ': 3 }
const t0 = Date.now(), sec = () => Math.round((Date.now() - t0) / 1000)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 2600 } })
await page.goto(`${base}/?sid=${sid}`)
await page.waitForSelector('.panel .btn', { timeout: 15000 })
await page.click('.panel .btn')
await page.waitForSelector('.sheet .row:not(.head)')
for (const row of await page.$$('.sheet .row:not(.head)')) {
  const name = await row.$eval('.name', (e) => e.innerText)
  const k = Object.keys(W).find((k) => name.includes(k))
  console.log(W[k] ?? '??', name.slice(0, 30))
  await row.$(`label.opt input[value="${W[k] ?? 3}"]`).then((i) => i.check())
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
