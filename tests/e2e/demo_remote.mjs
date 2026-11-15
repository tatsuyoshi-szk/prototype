// 使い方: node demo_remote.mjs [画面のアドレス]   （デモの構成の確認：別の場所のバックエンドへ、会話を1往復だけ送る。本物のAPIを1回使う）
// 画面（npm run dev）は VITE_API_BASE を設定して起動しておく。
import { chromium } from 'playwright-core'

const ui = process.argv[2] || 'http://127.0.0.1:5173/'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 800 } })
const failed = []
page.on('requestfailed', (r) => failed.push(`${r.url()} ${r.failure()?.errorText}`))
page.on('console', (m) => { if (m.type() === 'error') failed.push('console: ' + m.text()) })
const apiCalls = []
page.on('response', (r) => { if (r.url().includes('/api/')) apiCalls.push(`${r.status()} ${r.url()}`) })
await page.goto(ui)
await page.waitForSelector('textarea', { timeout: 20000 })
await page.fill('textarea', 'こんにちは。インドから来た留学生です。日本のIT企業で働きたいです。')
await page.keyboard.press('Enter')
await page.waitForFunction(() => !/考え中|Thinking…/.test(document.body.innerText), null, { timeout: 120000, polling: 500 })
await page.waitForTimeout(800)
const errors = await page.$$eval('.msg.error', (e) => e.map((x) => x.innerText))
const reply = (await page.$$eval('.msg.advisor', (e) => e.map((x) => x.innerText))).at(-1) || ''
console.log('API の呼び出し:', apiCalls)
console.log('画面のエラー表示:', errors)
console.log('AI の返事:', reply.slice(0, 80))
console.log('失敗した通信・コンソールのエラー:', failed)
await browser.close()
process.exit(errors.length || !reply ? 1 : 0)
