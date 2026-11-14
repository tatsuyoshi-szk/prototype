// 画面確認：擬似のAPI（固定データ）で、各画面のスクリーンショットを撮る。AIは呼ばない。
// 使い方: node ui_shots.mjs <出力フォルダ>   （PC幅と、スマホ幅の両方）
import { chromium } from 'playwright-core'
import fs from 'node:fs'

const outDir = process.argv[2] || 'shots'
fs.mkdirSync(outDir, { recursive: true })
const fx = JSON.parse(fs.readFileSync('fixtures.json', 'utf-8'))
const SID = 'AAAAAAAAAAAAAAAAAAAAAA'

async function setup(page, state) {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const json = (o, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(o) })
    if (u.pathname === '/api/session') {
      if (state === 'start') return json({ error: 'x' }, 404)
      return json({ finished: state !== 'midchat', axes: fx.axes, answered: state === 'result' || state === 'waiting',
                    transcript: state === 'midchat' ? fx.transcript.slice(0, 4) : fx.transcript,
                    ranking: state === 'result' ? fx.ranking : null })
    }
    if (u.pathname === '/api/survey') return json({ survey: fx.survey })
    if (u.pathname === '/api/rank') {
      return state === 'result' ? json({ state: 'done', ranking: fx.ranking })
        : json({ state: 'running', stage: 'research', detail: '調査中', elapsed: 74 })
    }
    return route.continue()
  })
}

const sizes = { pc: { width: 1000, height: 900 }, sp: { width: 390, height: 844 } }
const browser = await chromium.launch({ channel: 'msedge', headless: true })
for (const [sz, vp] of Object.entries(sizes)) {
  const shots = [
    ['1_start', 'start', null],
    ['2_midchat', 'midchat', null],
    ['3_done', 'done', null],
    ['4_survey', 'done', async (p) => { await p.click('.panel .btn'); await p.waitForSelector('.sheet .row:not(.head)') }],
    ['5_waiting', 'waiting', null],
    ['6_result', 'result', null],
  ]
  for (const [name, state, act] of shots) {
    const page = await browser.newPage({ viewport: vp })
    await setup(page, state)
    await page.goto(state === 'start' ? 'http://127.0.0.1:5173/' : `http://127.0.0.1:5173/?sid=${SID}`)
    await page.waitForTimeout(700)
    if (act) await act(page)
    await page.waitForTimeout(400)
    // 画面全体（スクロールする中身も含めて）を撮るため、高さを広げる
    const h = await page.evaluate(() => Math.max(document.querySelector('.log')?.scrollHeight || 0, 0) + 260)
    await page.setViewportSize({ width: vp.width, height: Math.min(Math.max(vp.height, h), 3800) })
    await page.waitForTimeout(300)
    await page.screenshot({ path: `${outDir}/${sz}_${name}.png` })
    // 横にはみ出していないか
    const over = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    if (over) console.log('横はみ出し:', sz, name)
    await page.close()
  }
}
await browser.close()
console.log('done')
