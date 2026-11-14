// 英語の相談を、画面（Edge）で最後まで進める。sid と軸を出力する。
import { chromium } from 'playwright-core'
const answers = [
  "Hi, I'm a fourth-year business student from Vietnam studying in Japan. I want to work in Japan after graduation, and someday start my own company. I haven't decided on a company yet.",
  "I'd like to build IT or e-commerce businesses that connect Vietnam and Japan. I know both countries well, so that's my strength.",
  "I want a job where I can build a new service and deliver it to customers from early on. I prefer environments where young people get real responsibility.",
  "I want to keep working with Vietnam, for example with Vietnamese teams or on business trips, but Japan can be my base.",
  "I don't care about the industry. IT or trading is fine, as long as I can take on new challenges and grow. Pay matters too: results should be recognized.",
  "Family is important to me, so being able to go home to Vietnam once a year for a longer time would be reassuring. My Japanese isn't perfect, so an English-friendly workplace helps.",
  "Yes, that's right. Also, I want my results to be reflected in my pay and evaluation. Nothing else.",
  "That's all, thank you.",
  "That's all.",
]
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1000, height: 900 } })
await page.goto('http://127.0.0.1:5173/')
await page.waitForSelector('textarea')
for (const [i, a] of answers.entries()) {
  if (await page.$('.panel')) break
  await page.fill('textarea', a)
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => !/考え中|Thinking/.test(document.body.innerText), null, { timeout: 180000, polling: 1000 })
  await page.waitForTimeout(500)
  const errs = await page.$$eval('.msg.error', (e) => e.map((x) => x.innerText))
  if (errs.length) { console.log('ERROR:', errs); break }
  const last = (await page.$$eval('.msg.advisor', (e) => e.map((x) => x.innerText))).at(-1)
  console.log(`--- reply ${i + 1} [ui placeholder: ${await page.$eval('textarea', (e) => e.placeholder).catch(() => '(locked)')}]\n${last.slice(0, 200)}${last.length > 200 ? '…' : ''}`)
}
const sid = new URL(page.url()).searchParams.get('sid')
console.log('panel title:', await page.$eval('.panel h2', (e) => e.innerText).catch(() => '-'))
const axes = await page.$$eval('.panel li', (e) => e.map((x) => x.innerText))
await page.screenshot({ path: 'en_chat_done.png' })
console.log(JSON.stringify({ sid, axes }))
await browser.close()
