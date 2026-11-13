import { expect, test } from '@playwright/test'
import type { Quiz } from '../../src/quiz-api'
import { openFixtureLesson } from './fixtures'

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
        ranking: { enabled: false, session_point: 0 },
        questions: Array.from({ length: 10 }, (_, index) => ({
          id: String(index), kind: 'single', topic: '开口方向', stem: '题目 ' + (index + 1),
          options: ['向上', '向下', '无法确定'],
        })),
      }
    } else {
      if (!quiz) throw Error('missing quiz')
      const index = Number(path.split('/').at(-2))
      if (path.endsWith('/explanation')) {
        Object.assign(quiz.questions[index].answer!, { correct: [0], explanation: '检查 a 的符号。' })
      } else {
        quiz.questions[index].answer = { selected: payload.selected, is_correct: index > 0 }
      }
      if (index === 9 && path.endsWith('/answer')) quiz.report = {
        total: 10, correct: 9, percent: 90, passed: true,
        topics: [{ topic: '开口方向', correct: 9, total: 10 }], wrong_ids: ['0'],
      }
    }
    await route.fulfill({ json: quiz })
  })

  await openFixtureLesson(page, 'quadratic')
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
    if (index === 1) {
      await expect(page.getByText('参考答案 A')).toHaveCount(0)
      await page.getByRole('button', { name: '查看解析' }).click()
      await expect(page.getByText('参考答案 A')).toBeVisible()
      await expect(page.getByRole('button', { name: '开始巩固' })).toBeVisible()
      await expect(page.getByRole('button', { name: '下一题', exact: true })).toBeEnabled()
    }
    if (index < 9) await page.getByRole('button', { name: '下一题' }).click()
  }
  const passDialog = page.getByRole('dialog', { name: '恭喜你，掌握了一个知识点！' })
  await expect(passDialog).toBeVisible()
  await expect(passDialog.getByText('正确率达到 90%以上，本次练习通过。')).toBeVisible()
  await expect(passDialog.locator('.quiz-badge')).toBeVisible()
  await expect(passDialog.locator('.quiz-stars')).toHaveCount(0)
  await expect(passDialog.locator('.quiz-confetti')).toHaveCount(0)
  await expect(passDialog.getByText('知识 +1')).toBeVisible()
  await passDialog.getByRole('button', { name: '查看练习报告' }).click()
  await expect(page.getByRole('heading', { name: '练习通过' })).toBeVisible()
  await expect(page.getByText('答对 9 / 10 题 · 正确率 90%')).toBeVisible()
  await page.getByRole('link', { name: '查看排行榜' }).click()
  await page.getByRole('button', { name: '继续浏览' }).click()
  await page.getByRole('button', { name: '返回上一页' }).click()
  await expect(page).toHaveURL(/\/study\?practice=/)
  await expect(page.getByRole('heading', { name: '练习通过' })).toBeVisible()
  await page.getByRole('button', { name: '返回学习' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(exampleTitle)
  await expect(page.frameLocator('iframe').getByRole('slider')).toBeVisible()
  await expect(message).toHaveValue(/开口方向/)
  expect(asks).toBe(2)
})

test('hides the answer during a challenge and thanks the learner once after a replacement', async ({ page }) => {
  const original = { id: 'original', kind: 'single' as const, topic: '开口方向', stem: '原来的题目', options: ['向上', '向下'] }
  const answer = { selected: [0], correct: [0], is_correct: true, explanation: '检查 a 的符号。' }
  const thanks = '感谢你的纠正！这道题已更换，请继续作答。'
  const quiz: Quiz = {
    id: 'quiz', version_id: 'version', status: 'ready', message: '', report: null,
    ranking: { enabled: false, session_point: 0 },
    questions: [{ ...original, answer }, { ...original, id: 'other', stem: '另一道题目' }],
  }
  let reviews = 0

  await page.route('**/api/quizzes**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/challenge')) {
      reviews++
      const { objection } = route.request().postDataJSON()
      quiz.questions[0] = { ...original, review: { status: 'pending', message: '', objection } }
      await route.fulfill({ status: 202, json: quiz })
      return
    }
    if (path.endsWith('/quiz') && quiz.questions[0].review?.status === 'pending') {
      quiz.questions[0] = reviews === 1
        ? { ...original, answer, review: { status: 'valid', message: '复核未发现题目有误，可以继续作答。请按题干条件判断。' } }
        : { ...original, id: 'replacement', stem: '新生成的题目', review: { status: 'replaced', message: thanks } }
    }
    await route.fulfill({ json: quiz })
  })

  await openFixtureLesson(page, 'quadratic')
  await page.getByRole('button', { name: '开始练习' }).click()
  await page.getByRole('button', { name: /第 1 题/ }).click()
  await expect(page.getByText('参考答案 A')).toBeVisible()
  await page.getByRole('button', { name: '质疑此题' }).click()
  await expect(page.getByText('参考答案 A')).toHaveCount(0)
  await expect(page.getByText('检查 a 的符号。')).toHaveCount(0)
  const objection = page.getByLabel('你对这道题有什么疑问？')
  await objection.fill('条件够吗？')
  await page.getByRole('button', { name: '提交质疑' }).click()
  await expect(page.getByText(/正在核查此题/)).toBeVisible()
  await expect(page.getByText(/复核未发现题目有误/)).toBeVisible()
  await expect(page.getByText('参考答案 A')).toHaveCount(0)
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await objection.fill('题干中的参数没有定义。')
  await page.getByRole('button', { name: '提交质疑' }).click()
  await page.getByRole('button', { name: /第 2 题/ }).click()
  const notice = page.getByRole('dialog', { name: '题目已更新' })
  await expect(notice.getByText(thanks)).toBeVisible()
  await notice.getByRole('button', { name: '继续作答' }).click()
  await expect(page.getByRole('group', { name: '新生成的题目' })).toBeVisible()
  await expect(page.getByText('参考答案 A')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('group', { name: '新生成的题目' })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('unknown answer locks the next question until one whole round passes and celebrates only once', async ({ page }) => {
  const quiz: Quiz = {
    id: 'drill-quiz', version_id: 'version', status: 'ready', message: '', report: null, blocked_question_id: null,
    ranking: { enabled: false, session_point: 0 },
    questions: [
      { id: 'main', kind: 'multiple', topic: '开口方向', stem: '主练习第一题', options: ['向上', '向下', '无法确定'] },
      { id: 'next', kind: 'single', topic: '开口方向', stem: '主练习第二题', options: ['向上', '向下', '无法确定'] },
    ],
  }
  const main = quiz.questions[0]
  function addQuestions(round: number) {
    main.drill!.questions = Array.from({ length: 3 }, (_, i) => ({
      id: `${round}-${i}`, kind: 'single', topic: '开口方向', stem: `第 ${round} 轮变式 ${i + 1}`, options: ['向上', '向下'],
    }))
    main.drill!.status = 'ready'
  }
  await page.route('**/api/quizzes**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/main/answer')) {
      expect(route.request().postDataJSON()).toEqual({ unsure: true })
      main.answer = { selected: [], is_correct: false, unsure: true }
      main.drill = { required: true, round: 1, status: 'awaiting_explanation', message: '', questions: [], feedback: [] }
      quiz.blocked_question_id = main.id
    } else if (path.endsWith('/main/explanation')) {
      Object.assign(main.answer!, { correct: [0, 1], explanation: '从参数符号判断。' })
      addQuestions(1)
    } else if (path.includes('/drill/questions/') && path.endsWith('/answer')) {
      const drill = main.drill!
      const current = drill.questions.find((item) => item.id === path.split('/').at(-2))!
      current.answer = { selected: route.request().postDataJSON().selected }
      if (drill.questions.every((item) => item.answer)) {
        if (drill.round === 1) {
          const wrong = drill.questions.filter((item) => item.answer!.selected[0] === 1)
          expect(wrong).toHaveLength(1)
          drill.feedback = wrong.map((item) => ({
            id: item.id, stem: item.stem, options: item.options, selected: [1], correct: [0], explanation: '看二次项系数。',
          }))
          drill.round = 2
          addQuestions(2)
        } else {
          drill.status = 'passed'
          quiz.blocked_question_id = null
        }
      }
    }
    await route.fulfill({ json: quiz })
  })

  await openFixtureLesson(page, 'quadratic')
  await page.getByRole('button', { name: '开始练习' }).click()
  await expect(page.getByRole('button', { name: '查看解析' })).toHaveCount(0)
  const unsure = page.getByRole('checkbox', { name: '我不清楚' })
  const option = page.getByRole('checkbox', { name: 'A. 向上' })
  await option.check()
  await unsure.check()
  await expect(option).not.toBeChecked()
  await option.check()
  await expect(unsure).not.toBeChecked()
  await unsure.check()
  await page.getByRole('button', { name: '提交答案' }).click()
  await expect(page.getByRole('button', { name: '下一题', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '第 2 题', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '查看解析' }).click()
  await expect(page.getByText('从参数符号判断。')).toBeVisible()
  const drill = page.getByRole('region', { name: '三题巩固' })
  for (const round of [1, 2]) {
    await expect(drill.getByRole('heading')).toHaveText(`三题巩固 · 第 ${round} 轮`)
    for (let i = 0; i < 3; i++) {
      await drill.getByRole('radio', { name: round === 1 && i === 0 ? 'B. 向下' : 'A. 向上' }).check()
      await drill.getByRole('button', { name: '提交巩固答案' }).click()
      if (i < 2) {
        await expect(drill.getByText('本题已提交')).toBeVisible()
        await expect(drill.getByText('看二次项系数。')).toHaveCount(round === 1 ? 0 : 1)
        await drill.getByRole('button', { name: '下一道巩固题' }).click()
      }
    }
    if (round === 1) {
      await expect(drill.getByText('看二次项系数。')).toBeVisible()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByRole('button', { name: '下一题', exact: true })).toBeDisabled()
      await page.reload()
    }
  }
  const celebration = page.getByRole('dialog', { name: '知识点攻克！' })
  await expect(celebration.getByText(/恭喜你，成功攻克了一个新知识点/)).toBeVisible()
  await celebration.getByRole('button', { name: '挑战下一题' }).click()
  await expect(page.getByRole('group', { name: '主练习第二题' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('group', { name: '主练习第二题' })).toBeVisible()
  await expect(celebration).toHaveCount(0)

  quiz.questions[1].answer = { selected: [1], is_correct: false, correct: [0], explanation: '看二次项系数。' }
  quiz.questions[1].drill = { required: true, round: 1, status: 'passed', message: '', questions: [], feedback: [] }
  quiz.report = { total: 2, correct: 0, percent: 0, passed: false, topics: [], wrong_ids: ['main', 'next'] }
  await page.reload()
  await expect(celebration).toBeVisible()
  await celebration.getByRole('button', { name: '查看练习报告' }).click()
  await expect(page.getByRole('region', { name: '练习报告' })).toBeFocused()
})

test('exam choice shows a verified citation and unlocks its link after submission', async ({ page }) => {
  const quiz: Quiz = {
    id: 'exam-quiz', version_id: 'version', status: 'exam_choice', message: '暂未找到可核验的真题。',
    exam: { exam: '数学测试', subject: '数学' },
    public_papers: [{ url: 'https://publisher.example/public', title: '公开数学试卷', year: 2024, publisher: '考试机构' }],
    ranking: { enabled: false, session_point: 0 }, questions: [], report: null,
  }
  await page.route('**/api/quizzes**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/exam-choice')) {
      expect(route.request().postDataJSON()).toEqual({ action: 'retry' })
      quiz.status = 'ready'
      quiz.message = ''
      quiz.questions = [{
        id: 'past', kind: 'single', topic: '开口', stem: '原卷选择题', origin: 'past', options: ['向上', '向下'],
        source: { exam: '数学测试', subject: '数学', year: 2024, paper: 'A卷', number: '1', publisher: '考试机构' },
      }, {
        id: 'simulated', kind: 'multiple', topic: '开口', stem: '模拟选择题', origin: 'simulated', options: ['向上', '向下'],
      }]
    } else if (path.endsWith('/past/answer')) {
      quiz.questions[0].answer = { selected: [0], is_correct: true }
      quiz.questions[0].source!.url = 'https://publisher.example/original'
    }
    await route.fulfill({ json: quiz })
  })
  await openFixtureLesson(page, 'quadratic')
  await page.getByRole('button', { name: '开始练习' }).click()
  await expect(page.getByRole('button', { name: '继续做模拟题' })).toBeVisible()
  await expect(page.getByRole('link', { name: '查看公开试卷' })).toHaveAttribute('href', 'https://publisher.example/public')
  await page.getByRole('button', { name: '重试搜索' }).click()
  await expect(page.getByText('真题', { exact: true })).toBeVisible()
  await expect(page.getByText(/2024 年.*A卷.*第 1 题.*考试机构/)).toBeVisible()
  await expect(page.getByRole('link', { name: '查看原始试卷' })).toHaveCount(0)
  await page.getByRole('radio', { name: 'A. 向上' }).check()
  await page.getByRole('button', { name: '提交答案' }).click()
  await expect(page.getByRole('link', { name: '查看原始试卷' })).toHaveAttribute('href', 'https://publisher.example/original')
  await page.getByRole('button', { name: '下一题' }).click()
  await expect(page.getByText('模拟题', { exact: true })).toBeVisible()
})
