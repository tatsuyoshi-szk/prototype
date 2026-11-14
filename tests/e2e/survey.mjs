// 使い方: node survey.mjs <sid>
import { chromium } from 'playwright-core'

const sid = process.argv[2]
const MUST = (process.env.MUST || '').split(',').filter(Boolean)
const t0 = Date.now()
const sec = () => Math.round((Date.now() - t0) / 1000)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 2600 } })
await page.goto(`http://127.0.0.1:5173/?sid=${sid}`)
await page.waitForSelector('.panel .btn', { timeout: 15000 })
console.log('パネルの見出し:', await page.$eval('.panel h2', (e) => e.innerText), '| ボタン:', await page.$eval('.panel .btn', (e) => e.innerText))
console.log('軸の確認パネル:', (await page.$$eval('.panel li', (e) => e.map((x) => x.innerText))).join(' / '))
await page.screenshot({ path: 'survey0_done.png' })
await page.click('.panel .btn')
await page.waitForSelector('.sheet .row:not(.head)', { timeout: 15000 })

// 項目名に応じて点数を決める（それ以外は 3）
const score = (name) => {
  if (name.includes('起業')) return 5
  if (name.includes('新サービス')) return 5
  if (name.includes('若手')) return 4
  if (name.includes('ベトナム')) return 4
  if (name.includes('評価・等級')) return 4
  if (name.includes('選考プロセスに英語')) return 4
  if (name.includes('日本語')) return 4
  if (name.includes('長期帰国')) return 4
  if (name.includes('ビザ')) return 4
  if (name.includes('多言語')) return 4
  const n = name.toLowerCase()
  if (n.includes('startup') || n.includes('new service')) return 5
  if (n.includes('early responsibility') || n.includes('vietnam')) return 4
  if (n.includes('japanese level') || n.includes('english available') || n.includes('long leave') || n.includes('visa')) return 4
  if (n.includes('evaluated') || n.includes('other languages')) return 4
  return 3
}
const rows = await page.$$('.sheet .row:not(.head)')
console.log('項目数:', rows.length)

// 「譲れない」の動作確認：ビザの行にチェック → 5点が選ばれて固定される → チェックを外して、4点に選び直す
for (const row of rows) {
  const name = await row.$eval('.name', (e) => e.innerText)
  if (!MUST.length && name.includes('ビザ')) {
    await row.$('label.must input').then((i) => i.check())
    const state = await row.$$eval('label.opt input', (els) => els.map((e) => ({ v: e.value, checked: e.checked, disabled: e.disabled })))
    console.log('譲れない=ON のビザ行:', JSON.stringify(state.filter((s) => s.checked || s.v === '3').slice(0, 3)), '全部disabled:', state.every((s) => s.disabled), '5点が選択:', state.find((s) => s.v === '5').checked)
    await row.$('label.must input').then((i) => i.uncheck())
  }
}
for (const row of rows) {
  const name = await row.$eval('.name', (e) => e.innerText)
  if (MUST.some((k) => name.includes(k))) { await row.$('label.must input').then((i) => i.check()); continue }
  await row.$(`label.opt input[value="${score(name)}"]`).then((i) => i.check())
}
await page.screenshot({ path: 'survey1_filled.png', fullPage: true })
console.log('進み具合の表示:', await page.$eval('.progress', (e) => e.innerText))
await page.click('button[type=submit]')
await page.waitForSelector('.progress-box, .rank, .msg.error', { timeout: 30000 })
await page.screenshot({ path: 'survey2_waiting.png' })
console.log(`[${sec()}s] 送信 → 待ち画面:`, await page.$eval('.progress-box', (e) => e.innerText).catch(() => '（もう結果）'))

// 結果が出るまで待つ（最大 12 分）
await page.waitForSelector('.card, .screening, .msg.error', { timeout: 12 * 60 * 1000 })
console.log(`[${sec()}s] 結果画面`)
await page.waitForTimeout(500)
await page.screenshot({ path: 'result.png', fullPage: false })
console.log(await page.$eval('.rank', (e) => e.innerText).catch(async () => (await page.$$eval('.msg.error', (x) => x.map((y) => y.innerText))).join('\n')))

// 読み込み直し：同じアドレスで開き直して、会話・結果が復元されるか
await page.goto(`http://127.0.0.1:5173/?sid=${sid}`)
await page.waitForSelector('.card, .screening, .msg.error', { timeout: 30000 })
await page.waitForTimeout(500)
await page.screenshot({ path: 'result_reload.png' })
console.log('読み込み直し後: 会話の吹き出し', (await page.$$('.msg.student')).length, '件 / 企業カード', (await page.$$('.card')).length, '枚 / 絞り込みの表示', !!(await page.$('.screening')))
console.log('絞り込み:', await page.$eval('.screening', (e) => e.innerText).catch(() => '（なし）'))
await browser.close()
