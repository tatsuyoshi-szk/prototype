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


const browser = await chromium.launch({ channel: 'msedge', headless: true })
for (const [sz, vp] of Object.entries({ pc: { width: 1000, height: 900 }, sp: { width: 390, height: 844 } })) {
  for (const [name, state, act] of [['result', 'result', null], ['survey', 'done', async (p) => { await p.click('.panel .btn'); await p.waitForSelector('.sheet .row:not(.head)') }], ['waiting', 'waiting', null]]) {
    const page = await browser.newPage({ viewport: vp })
    await setup(page, state)
    await page.goto(`http://127.0.0.1:5173/?sid=${SID}`)
    await page.waitForTimeout(800)
    if (act) await act(page)
    await page.waitForTimeout(600)
    await page.screenshot({ path: `${outDir}/view_${sz}_${name}.png` })
    await page.close()
  }
}
await browser.close()
