import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { openFixtureLesson } from './fixtures'

const password = 'Browser-password-42'

async function completeOnboarding(page: Page, stage = '高中', goal = '用图像理解二次函数') {
  await expect(page.getByRole('heading', { name: '先认识一下你' })).toBeVisible()
  await page.getByRole('button', { name: new RegExp(stage) }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByRole('heading', { name: '最近想弄懂什么？' })).toBeVisible()
  await page.getByLabel('近期学习目标').fill(goal)
  await page.getByRole('button', { name: /完成/ }).click()
  await page.getByRole('button', { name: '开始学习' }).click()
}

async function authenticate(page: Page, mode: '注册' | '登录', name: string) {
  await Promise.race([
    page.getByRole('navigation', { name: '账户导航' }).waitFor({ timeout: 5000 }).catch(() => undefined),
    page.getByRole('button', { name: '先逛逛' }).waitFor({ timeout: 5000 }).catch(() => undefined),
  ])
  const guest = page.getByRole('button', { name: '先逛逛' })
  if (await guest.count()) {
    await guest.click()
    await page.getByLabel('你想弄懂什么？').waitFor({ timeout: 10000 })
  }
  await page.getByRole('navigation', { name: '账户导航' }).getByRole('link', { name: mode }).click()
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: mode, exact: true }).click()
  if (mode === '注册') await completeOnboarding(page)
  await expect(page.getByRole('navigation', { name: '账户导航' }).getByText(name, { exact: true })).toBeVisible()
}

test('registration, account switching, guest recovery and leaderboard', async ({ page }) => {
  const databasePath = process.env.BROWSER_QUIZ_DB_PATH ?? '.local/browser-quiz.sqlite3'
  expect(existsSync(databasePath)).toBe(true)
  const publicPath = (isAbsolute(databasePath) ? '/@fs/' : '/') + databasePath.replaceAll('\\', '/')
  expect((await page.request.get(encodeURI(publicPath))).status()).toBe(403)
  const alice = 'Alice_' + randomUUID().slice(0, 8)
  const bob = 'Bob_' + randomUUID().slice(0, 8)
  await openFixtureLesson(page, 'quadratic')
  await expect(page.getByRole('heading', { name: '二次函数参数', exact: true })).toBeVisible()
  await expect(page.getByText('通用模式 · 登录后可按年级/目标定制')).toBeVisible()
  await authenticate(page, '注册', alice)
  await expect(page.getByText('你还没有开始提问，快来探索知识吧！')).toBeVisible()
  await expect(page.getByText('当前个人设置：高中 · 用图像理解二次函数')).toBeVisible()
  await expect(page.getByRole('button', { name: /继续上次学习/ })).toHaveCount(0)
  await openFixtureLesson(page, 'recursion')
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await expect(page.getByText('按 高中 · 用图像理解二次函数 生成')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByRole('button', { name: '先逛逛' }).click()
  await expect(page.getByRole('button', { name: /继续上次学习.*二次函数参数/ })).toBeVisible()
  await authenticate(page, '注册', bob)
  await expect(page.getByRole('button', { name: /继续上次学习/ })).toHaveCount(0)
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('button', { name: '先逛逛' })).toBeVisible()
  await authenticate(page, '登录', alice)
  await expect(page.getByRole('button', { name: /继续上次学习.*递归调用栈/ })).toBeVisible()
  await page.getByRole('link', { name: '排行榜', exact: true }).click()
  await expect(page.getByRole('heading', { name: '排行榜', exact: true })).toBeVisible()
  await expect(page.getByText(/当前排名.*第 3 名.*我的积分.*0/)).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: alice })).toHaveClass('rank-current-user')
  await expect(page.getByRole('row').filter({ hasText: '小王' })).toContainText('5')
  await expect(page.getByRole('row').filter({ hasText: '小明' })).toContainText('3')
})

test('guest leaderboard invitation supports browsing, registration and ordinary login return', async ({ page }) => {
  await page.route('**/api/leaderboard?page=*', async (route) => {
    const pageNumber = new URL(route.request().url()).searchParams.get('page')
    await route.fulfill({ json: {
      entries: [{ username: pageNumber === '1' ? '小王' : '小张', rank: Number(pageNumber), points: 5 }],
      has_more: pageNumber === '1', me: null,
    } })
  })
  await page.goto('/leaderboard')
  const invite = page.getByRole('dialog', { name: '加入学习排行榜' })
  await expect(invite.getByText(/暂时无法参与排行/)).toBeVisible()
  await invite.getByRole('button', { name: '继续浏览' }).click()
  await expect(page.getByRole('heading', { name: '排行榜' })).toBeFocused()
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.getByRole('row', { name: /小张/ })).toBeVisible()
  await expect(invite).toHaveCount(0)

  await page.getByRole('button', { name: '返回上一页' }).click()
  await expect(page.getByRole('link', { name: '我是新用户，开始学习' })).toBeVisible()
  await page.getByRole('link', { name: '排行榜' }).click()
  const name = 'Learner_' + randomUUID().slice(0, 8)
  await invite.getByRole('link', { name: '注册' }).click()
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await completeOnboarding(page, '初中', '能用坐标理解函数')
  await expect(page).toHaveURL(/\/leaderboard$/)
  await expect(page.getByRole('heading', { name: '排行榜' })).toBeVisible()
  await expect(invite).toHaveCount(0)

  await page.getByRole('link', { name: '个人设置' }).click()
  await expect(page.getByLabel('学习阶段')).toHaveValue('初中')
  await page.getByLabel('学习阶段').selectOption('本科')
  await page.getByLabel('近期学习目标').fill('理解函数的变化率')
  await page.getByRole('button', { name: '保存个人设置' }).click()
  await expect(page).toHaveURL(/\/leaderboard$/)
  await page.getByRole('link', { name: '个人设置' }).click()
  await expect(page.getByLabel('学习阶段')).toHaveValue('本科')
  await expect(page.getByLabel('近期学习目标')).toHaveValue('理解函数的变化率')

  await page.getByRole('button', { name: '退出' }).click()
  await page.getByRole('link', { name: '排行榜' }).click()
  await invite.getByRole('link', { name: '登录' }).click()
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/leaderboard$/)
  await expect(page.getByRole('heading', { name: '排行榜' })).toBeVisible()
})

test('legacy account completes settings and returns to the previous page', async ({ page }) => {
  const user = { id: 'old-account', username: 'OldAccount', profile: null }
  let profile: unknown = null
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { user: { ...user, profile } } }))
  await page.route('**/api/auth/profile', (route) => {
    profile = route.request().postDataJSON()
    return route.fulfill({ json: { user: { ...user, profile } } })
  })
  await page.goto('/leaderboard')
  await completeOnboarding(page, '硕士', '理解梯度在优化中的作用')
  await expect(page.getByRole('heading', { name: '排行榜', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('saving settings from a lesson returns to the lesson', async ({ page }) => {
  const name = 'Study_' + randomUUID().slice(0, 8)
  await page.goto('/')
  await authenticate(page, '注册', name)
  await openFixtureLesson(page, 'recursion')
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '个人设置' }).click()
  await expect(page.getByRole('heading', { name: '个人设置' })).toBeVisible()
  await page.getByRole('button', { name: '保存个人设置' }).click()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
})

test('personal settings has back and home actions', async ({ page }) => {
  const name = 'Settings_' + randomUUID().slice(0, 8)
  await page.goto('/')
  await authenticate(page, '注册', name)
  await openFixtureLesson(page, 'recursion')
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '个人设置' }).click()
  await expect(page.getByRole('heading', { name: '个人设置' })).toBeVisible()
  await page.getByRole('button', { name: '← 返回上一页' }).click()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '个人设置' }).click()
  await page.getByRole('link', { name: '返回首页' }).click()
  await expect(page.getByRole('heading', { name: '把问题动起来。' })).toBeVisible()
})

test('leaderboard and library return to the source page', async ({ page }) => {
  const name = 'Back_' + randomUUID().slice(0, 8)
  await page.goto('/')
  await authenticate(page, '注册', name)
  await openFixtureLesson(page, 'recursion')
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '排行榜', exact: true }).click()
  await expect(page.getByRole('heading', { name: '排行榜', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '← 返回上一页' }).click()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '我的试卷' }).click()
  await expect(page.getByRole('heading', { name: '我的试卷' })).toBeVisible()
  await page.getByRole('button', { name: '← 返回上一页' }).click()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '我的试卷' }).click()
  await expect(page.getByRole('heading', { name: '我的试卷' })).toBeVisible()
  await page.getByRole('link', { name: '排行榜', exact: true }).click()
  await expect(page.getByRole('heading', { name: '排行榜', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '← 返回上一页' }).click()
  await expect(page.getByRole('heading', { name: '我的试卷' })).toBeVisible()
})

test('goal review waits at 99 percent and keeps the form on rejection', async ({ page }) => {
  let finish: () => void = () => {}
  const waiting = new Promise<void>((resolve) => { finish = resolve })
  await page.route('**/api/auth/profile', async (route) => {
    await waiting
    await route.fulfill({ status: 422, json: { detail: '请补充你准备参加的考试。' } })
  })
  const name = 'Review_' + randomUUID().slice(0, 8)
  await page.goto('/register')
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page.getByRole('heading', { name: '先认识一下你' })).toBeVisible()
  await page.getByRole('button', { name: /高中/ }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByLabel('近期学习目标').fill('准备参加考试')
  await page.getByRole('button', { name: /完成/ }).click()
  const review = page.getByRole('dialog', { name: '正在审核目标' })
  await expect(review.getByText('99%')).toBeVisible()
  finish()
  await expect(review).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveText('请补充你准备参加的考试。')
  await expect(page.getByLabel('近期学习目标')).toHaveValue('准备参加考试')
})

test('imports a paper, confirms drafts and returns to learn a tagged topic', async ({ page }) => {
  const user = { id: 'library-user', username: 'LibraryUser', profile: { education_stage: '初中', goal: '学习数学' } }
  const draft = { status: 'draft', confirmed: false, file: 'paper.docx', page: 1,
    reason: '识别结果待确认，请核对题干、选项后点击确认。' }
  const first = { id: 1, number: '1',
    stem: '已知 $xOy$ 中，$P(3,-5)$ 关于 $y$ 轴对称。\n\n| x | 1 | 2 |\n|---|---|---|\n| y | 3 | 4 |',
    tags: ['二次函数'], options: ['系数为正', '系数为负', '系数为零'], correct: [0], ...draft }
  const second = { id: 2, number: '2', stem: '写出对称轴。', tags: [],
    options: ['x=1', 'x=-1', 'x=0'], correct: [0], ...draft }
  const paper = { id: 'paper', exam: '成都中考', subject: '数学', year: null, paper: null, filenames: ['paper.docx'],
    question_count: 2, draft_count: 2, confirmed_count: 0, ready_count: 0, review_count: 0, questions: [first, second] }
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { user } }))
  await page.route('**/api/exam-library', (route) => route.fulfill({ json: { papers: [] } }))
  await page.route('**/api/exam-library/imports', (route) => {
    const submitted = route.request().postDataJSON()
    expect(submitted.exam).toBe('成都中考')
    expect(submitted.consent).toBe(true)
    expect(submitted.files[0]).toEqual({ filename: 'paper.docx', data: Buffer.from('sample').toString('base64') })
    return route.fulfill({ status: 201, json: { duplicate: false, paper } })
  })
  await page.route('**/api/exam-library/paper/questions/1/confirm', (route) => route.fulfill({ json: { paper: {
    ...paper, draft_count: 1, confirmed_count: 1, ready_count: 1,
    questions: [{ ...first, confirmed: true, status: 'ready', reason: '' }, second] } } }))
  await page.route('**/api/exam-library/paper/questions/2/confirm', (route) => route.fulfill({ json: { paper: {
    ...paper, draft_count: 0, confirmed_count: 2, ready_count: 2,
    questions: [{ ...first, confirmed: true, status: 'ready', reason: '' },
      { ...second, confirmed: true, status: 'ready', reason: '' }] } } }))
  await page.route('**/api/exam-library/paper/questions/1/tags', (route) => {
    const submitted = route.request().postDataJSON()
    expect(submitted.tags).toEqual(['二次函数', '判别式'])
    return route.fulfill({ json: { paper: { ...paper, questions: [
      { ...first, confirmed: true, status: 'ready', reason: '', tags: submitted.tags },
      { ...second, confirmed: true, status: 'ready', reason: '' }] } } })
  })
  await page.goto('/')
  await page.getByRole('link', { name: '我的试卷' }).click()
  await page.getByLabel('考试名称').fill('成都中考')
  await page.getByLabel('试卷和参考答案').setInputFiles({
    name: 'paper.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: Buffer.from('sample'),
  })
  await page.getByRole('checkbox', { name: /同意/ }).check()
  await page.getByRole('button', { name: '导入试卷' }).click()
  await expect(page.getByText('已识别 2 道题，请逐题核对后点击「确认入库」。')).toBeVisible()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.locator('.katex').first()).toBeVisible()
  await expect(page.getByText('|---|')).toHaveCount(0)
  await expect(page.getByText('系数为正')).toBeVisible()
  await expect(page.getByText('未确认').first()).toBeVisible()
  await page.getByRole('button', { name: '确认入库' }).first().click()
  await expect(page.getByText('已确认入库。')).toBeVisible()
  await page.getByRole('button', { name: '确认入库' }).click()
  await expect(page.getByText('已确认入库。')).toHaveCount(1)
  await expect(page.getByRole('button', { name: '确认入库' })).toHaveCount(0)
  await page.getByRole('button', { name: '编辑知识点' }).first().click()
  await page.getByLabel('添加知识点').fill('判别式')
  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByText('知识点已更新。')).toBeVisible()
  await expect(page.getByRole('link', { name: '学习判别式' })).toBeVisible()
  await page.getByRole('link', { name: '学习二次函数' }).click()
  await expect(page.getByLabel('你想弄懂什么？')).toHaveValue('请讲解二次函数')
})
