// 使い方: node chat.mjs   （会話を、終わるまで1つの画面で進める。sid と、軸を出力する）
import { chromium } from 'playwright-core'

const answers = [
  'はじめまして。私はベトナムから来た留学生で、日本の大学の経営学部の4年生です。将来は日本で働きたいですが、いつか自分でも事業を始めたいと思っています。まだ具体的な会社は決まっていません。',
  'ベトナムと日本をつなぐ、ITやEコマースの事業をやってみたいです。両方の国の事情が分かるので、そこに強みがあると思っています。',
  '新しいサービスを自分で作って、お客さんに届けるところまで、早い段階から任せてもらえる経験がしたいです。大きい会社より、若手でも裁量がある環境がいいです。',
  'ベトナムとは関わり続けたいです。仕事で、ベトナムのチームと一緒に働いたり、出張で行けたりしたら嬉しいです。ただ、ずっと海外にいたいわけではなく、日本が拠点で大丈夫です。',
  '分野にはこだわりません。ITでも商社でも、新しいことに挑戦できて、成長できる会社なら大丈夫です。お給料も大事なので、成果を出したらちゃんと評価される会社がいいです。',
  '家族が大切なので、年に1回は長めにベトナムへ帰れると安心です。あと、日本語はまだ完璧ではないので、周りが英語でも話せる環境だと助かります。',
  'はい、合っています。あと、成果を出したら、給料や評価にちゃんと反映されることも大事です。それ以外は大丈夫です。',
  '以上です。ありがとうございます。',
  '以上です。',
]
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 900 } })
await page.goto('http://127.0.0.1:5173/')
await page.waitForSelector('textarea')
for (const [i, a] of answers.entries()) {
  if (await page.$('.panel')) break
  await page.fill('textarea', a)
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => !document.body.innerText.includes('考え中'), null, { timeout: 180000, polling: 1000 })
  await page.waitForTimeout(400)
  const errs = await page.$$eval('.msg.error', (e) => e.map((x) => x.innerText))
  if (errs.length) { console.log('エラー:', errs); break }
  const last = (await page.$$eval('.msg.advisor', (e) => e.map((x) => x.innerText))).at(-1)
  console.log(`--- ${i + 1}回目の返事:\n${last.slice(0, 160)}${last.length > 160 ? '…' : ''}`)
}
const sid = new URL(page.url()).searchParams.get('sid')
const axes = await page.$$eval('.panel li', (e) => e.map((x) => x.innerText))
await page.screenshot({ path: 'chat_done.png' })
console.log(JSON.stringify({ sid, axes }))
await browser.close()
