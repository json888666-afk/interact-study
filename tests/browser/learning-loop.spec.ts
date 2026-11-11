import { expect, test } from '@playwright/test'
import type { Quiz } from '../../src/quiz-api'

test('asks with screenshot, resumes practice after refresh and returns to the same lesson', async ({ page }) => {
  let quiz: Quiz | null = null
  let asks = 0
  const exampleTitle = '二次函数参数'
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aIRkAAAAASUVORK5CYII=', 'base64')

  await page.route('**/api/lessons/ask', async (route) => {
    const payload = route.request().postDataJSON()
    expect(payload.lesson.title).toBe(exampleTitle)
    asks++
    if (asks === 1) {
      expect(payload.image).toBeNull()
    } else {
      expect(payload.image).toBe('data:image/png;base64,' + image.toString('base64'))
      expect(payload.history).toHaveLength(1)
    }
    await route.fulfill({ json: { answer: asks === 1 ? '看 a 的符号。' : '截图中的图像开口向下。' } })
  })
  await page.route('**/api/quizzes**', async (route) => {
    const path = new URL(route.request().url()).pathname
    expect(route.request().headers()['x-study-session']).toBeTruthy()
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: quiz })
      return
    }
    const payload = route.request().postDataJSON()
    if (path === '/api/quizzes') {
      expect(payload.history).toHaveLength(2)
      quiz = {
        id: 'quiz', version_id: payload.version_id, status: 'ready', message: '', report: null,
        questions: Array.from({ length: 10 }, (_, index) => ({
          id: String(index), kind: 'single', topic: '开口方向', stem: '题目 ' + (index + 1),
          options: ['向上', '向下', '无法确定'],
        })),
      }
    } else {
      if (!quiz) throw Error('missing quiz')
      const index = Number(path.split('/').at(-2))
      quiz.questions[index].answer = { selected: payload.selected, correct: [0], is_correct: index > 0, explanation: '检查 a 的符号。' }
      if (index === 9) quiz.report = {
        total: 10, correct: 9, percent: 90, passed: false,
        topics: [{ topic: '开口方向', correct: 9, total: 10 }], wrong_ids: ['0'],
      }
    }
    await route.fulfill({ json: quiz })
  })

  await page.goto('/')
  await page.getByRole('button', { name: new RegExp(exampleTitle) }).click()
  await expect(page.getByRole('button', { name: '问原理' })).toHaveAttribute('aria-pressed', 'true')
  const message = page.getByLabel('你想理解什么？')
  await message.fill('为什么开口会改变？')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.getByText('看 a 的符号。')).toBeVisible()
  await message.fill('截图里朝向哪里？')
  await page.getByLabel('附一张截图（可选）').setInputFiles({ name: 'chart.png', mimeType: 'image/png', buffer: image })
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.getByText('截图中的图像开口向下。')).toBeVisible()
  await page.getByRole('button', { name: '开始练习' }).click()
  await page.getByRole('radio', { name: /B. 向下/ }).check()
  await page.getByRole('button', { name: '提交答案' }).click()
  await expect(page.getByText('回答错误')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '检查理解' })).toBeVisible()
  await expect(page.getByText('已作答 1 / 10 题')).toBeVisible()
  await expect(page.getByRole('group', { name: '题目 2', exact: true })).toBeVisible()
  for (let index = 1; index < 10; index++) {
    await page.getByRole('radio', { name: /A. 向上/ }).check()
    await page.getByRole('button', { name: '提交答案' }).click()
    await expect(page.getByText('回答正确')).toBeVisible()
    if (index < 9) await page.getByRole('button', { name: '下一题' }).click()
  }
  await expect(page.getByRole('heading', { name: '可以再练习' })).toBeVisible()
  await expect(page.getByText('答对 9 / 10 题 · 正确率 90%')).toBeVisible()
  await page.getByRole('button', { name: '返回学习' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(exampleTitle)
  await expect(page.frameLocator('iframe').getByRole('slider')).toBeVisible()
  await expect(message).toHaveValue(/开口方向/)
  expect(asks).toBe(2)
})
