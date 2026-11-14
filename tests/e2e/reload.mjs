import { chromium } from 'playwright-core'
const sid = process.argv[2]
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 1500 } })
await page.goto(`http://127.0.0.1:5173/?sid=${sid}`)
await page.waitForSelector('.card, .screening, .msg.error', { timeout: 30000 })
await page.waitForTimeout(500)
console.log('会話の吹き出し(相談者)', (await page.$$('.msg.student')).length, '件 / 企業カード', (await page.$$('.card')).length, '枚')
console.log('絞り込みの表示:', await page.$eval('.screening', (e) => e.innerText).catch(() => '（なし）'))
await page.click('.screening summary').catch(() => {})
console.log('除外の一覧（先頭3件）:', (await page.$$eval('.screening li', (e) => e.map((x) => x.innerText))).slice(0, 3))
const rankTop = await page.$$eval('.card .nm', (e) => e.map((x) => x.innerText))
console.log('表示された企業:', rankTop.join(' / '))
await page.screenshot({ path: 'result_reload.png', fullPage: false })
// 存在しない sid
await page.goto('http://127.0.0.1:5173/?sid=AAAAAAAAAAAAAAAAAAAAAA')
await page.waitForSelector('.msg.error', { timeout: 10000 })
console.log('存在しない会話:', await page.$eval('.msg.error', (e) => e.innerText), '/ ボタン:', await page.$eval('.btn', (e) => e.innerText))
await browser.close()
