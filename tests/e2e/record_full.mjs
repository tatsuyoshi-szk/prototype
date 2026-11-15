// 使い方: node record_full.mjs [port]   （会話→アンケート→結果までを、画面で通して、videos/ に録画する。本物のAPIを使う＝費用がかかる）
// 留学生役の返事は、あらかじめ決めた文（相手の質問に合わせた返事ではない）。
import { chromium } from 'playwright-core'

const base = `http://127.0.0.1:${process.argv[2] || 8000}`
const answers = [
  'はじめまして。韓国から来た、情報工学科の修士2年です。日本のIT企業で、ゲームやアプリのサービスを作る仕事をしたいです。',
  'プログラマーとして、ユーザーが毎日使うアプリを作りたいです。ユーザーの反応を見ながら、すぐに改善していく開発が好きです。',
  'チームに、いろいろな国の人がいて、英語でも話せる環境がいいです。ビザのサポートがしっかりしている会社を探しています。',
  'ゲームとコミュニケーションのアプリに興味があります。日本のゲームを海外にも届けたいです。将来は、韓国と日本をつなぐ仕事もしたいです。',
  '最初は、開発の技術を深めたいです。新しい技術を使うチームで、若手でも意見を聞いてもらえる会社がいいです。',
  'ゲームの海外版を作る仕事に関わりたいです。韓国語と英語ができるので、その強みも使いたいです。',
  'はい、合っています。ほかは大丈夫です。ありがとうございます。',
  '以上です。ありがとうございます。',
  '以上です。',
]
const AXIS_W = [5, 4, 4, 4, 3, 3]
const W = { '外国籍社員の割合': 3, '外国籍役員': 2, '評価・等級': 4, '選考プロセスに英語': 4, '日本語のレベル': 3, '多言語': 3, 'ビザ': 4, '衣食住': 3,
  'コミュニティ': 3, '文化・宗教': 3, '長期帰国': 3, 'グローバル拠点': 4, '口コミサイト': 2, '外国人の口コミ': 2 }
const t0 = Date.now(), sec = () => Math.round((Date.now() - t0) / 1000)

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const ctx = await browser.newContext({ viewport: { width: 1000, height: 900 }, recordVideo: { dir: 'videos', size: { width: 1000, height: 900 } } })
const page = await ctx.newPage()
const video = page.video()
let sid = null
try {
  await page.goto(`${base}/`)
  await page.waitForSelector('textarea', { timeout: 20000 })
  await page.waitForTimeout(1500)
  for (const [i, a] of answers.entries()) {
    if (await page.$('.panel')) break
    await page.click('textarea')
    await page.keyboard.type(a, { delay: 25 })       // 打ち込む様子が見えるように、ゆっくり入力する
    await page.waitForTimeout(500)
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => !document.body.innerText.includes('考え中'), null, { timeout: 180000, polling: 1000 })
    await page.waitForTimeout(1200)
    const errs = await page.$$eval('.msg.error', (e) => e.map((x) => x.innerText))
    if (errs.length) { console.log('エラー:', errs); break }
    console.log(`[${sec()}s] ${i + 1}回目の返事あり`)
  }
  sid = new URL(page.url()).searchParams.get('sid')
  await page.waitForSelector('.panel .btn', { timeout: 20000 })
  console.log(`[${sec()}s] 会話が終わりました sid=${sid}`)
  await page.waitForTimeout(2500)
  await page.click('.panel .btn')
  await page.waitForSelector('.sheet .row:not(.head)')
  await page.waitForTimeout(1500)
  let axisNo = 0
  for (const row of await page.$$('.sheet .row:not(.head)')) {
    const name = await row.$eval('.name', (e) => e.innerText)
    await row.scrollIntoViewIfNeeded()
    let w
    if (name.includes('就活軸「')) w = AXIS_W[axisNo++] ?? 3
    else w = W[Object.keys(W).find((k) => name.includes(k))] ?? 3
    if (axisNo === 1 && name.includes('就活軸「')) {
      await row.$('label.must input').then((i) => i.check())     // 最初の軸を「譲れない」にする
    } else {
      await row.$(`label.opt input[value="${w}"]`).then((i) => i.check())
    }
    await page.waitForTimeout(250)
  }
  await page.waitForTimeout(1000)
  await page.click('button[type=submit]')
  await page.waitForSelector('.progress-box, .rank, .msg.error', { timeout: 30000 })
  console.log(`[${sec()}s] アンケート送信`)
  await page.waitForSelector('.card, .screening, .msg.error', { timeout: 12 * 60 * 1000 })
  console.log(`[${sec()}s] 結果が出ました`)
  await page.waitForTimeout(2000)
  for (let k = 0; k < 14; k++) {                      // 結果を、ゆっくりスクロールして見せる
    await page.mouse.wheel(0, 450)
    await page.waitForTimeout(1100)
  }
  await page.waitForTimeout(1500)
} finally {
  await ctx.close()                                    // 閉じると、録画ファイルが書き出される
  await browser.close()
}
console.log('録画ファイル:', await video.path())
