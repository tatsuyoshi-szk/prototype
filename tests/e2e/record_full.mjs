// 使い方: node record_full.mjs [port] [ja|en]   （会話→アンケート→結果までを、画面で通して、videos/ に録画する。本物のAPIを使う＝費用がかかる）
// 留学生役の返事は、あらかじめ決めた文（相手の質問に合わせた返事ではない）。en にすると、英語で通す。
import { chromium } from 'playwright-core'

const base = `http://127.0.0.1:${process.argv[2] || 8000}`
const LANG = process.argv[3] === 'en' ? 'en' : 'ja'
const answers_ja = [
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
const answers_en = [
  "Hello. I am a master's student in computer science from Korea. I want to build game and app services at a Japanese IT company.",
  'I want to be a programmer and make apps that users open every day. I like improving a product quickly while watching how users react.',
  'I would like a team with people from many countries, where English is also used. I am looking for a company that gives good visa support.',
  'I am interested in games and communication apps. I want to bring Japanese games to people overseas. In the future I would like work that connects Korean and Japanese companies.',
  'At first I want to deepen my development skills in a team that uses new technology, where even young members are listened to.',
  'I want to work on overseas versions of games, together with the localization team. I speak Korean and English, and I want to use that strength.',
  'Yes, that is correct. Nothing else. Thank you very much.',
  'That is all. Thank you.',
  'That is all.',
]
// 第4引数が it のとき：IT志望（少人数のチームで、裁量を持って開発したい）の学生の返事（日本語）
const answers_it = [
  'はじめまして。ベトナムから来た、情報系の学部4年生です。日本でITエンジニアとして働きたいと思っています。まだ会社は決まっていません。',
  '自分でコードを書いて、サービスを作る仕事がしたいです。大学では、Webアプリの開発とデータ分析を勉強しました。',
  '大きい会社より、少人数のチームで、若いうちから裁量を持って開発に関わりたいです。自分の意見も言いやすい会社がいいです。',
  '新しい技術を使うチームがいいです。AIやクラウドに興味があります。勉強会や、技術を学べる環境があると嬉しいです。',
  '日本語は少し不安なので、チームに英語でも話せる人がいると安心です。ビザのサポートがある会社を探しています。',
  '将来は、日本で経験を積んでから、ベトナムと日本をつなぐITの仕事もしたいです。',
  'はい、合っています。ほかは大丈夫です。ありがとうございます。',
  '以上です。ありがとうございます。',
  '以上です。',
]
const answers = LANG === 'en' ? answers_en : process.argv[4] === 'it' ? answers_it : answers_ja
// アンケートの重み：上から順（日本語・英語で共通）。就活軸のあとに、共通14項目が決まった順で並ぶ
const AXIS_W = [5, 4, 4, 4, 3, 3]
const COMMON_W = [3, 2, 4, 4, 3, 3, 4, 3, 3, 3, 3, 4, 2, 2]
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
    await page.waitForFunction(() => !/考え中|Thinking…/.test(document.body.innerText), null, { timeout: 180000, polling: 1000 })
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
  const rows = await page.$$('.sheet .row:not(.head)')
  const nAxes = rows.length - COMMON_W.length
  for (const [k, row] of rows.entries()) {
    await row.scrollIntoViewIfNeeded()
    if (k === 0) {
      await row.$('label.must input').then((i) => i.check())     // 最初の軸を「譲れない」にする
    } else {
      const w = k < nAxes ? (AXIS_W[k] ?? 3) : COMMON_W[k - nAxes]
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
