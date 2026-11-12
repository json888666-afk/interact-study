import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import { openFixtureLesson } from './fixtures'

const password = 'Browser-password-42'

async function authenticate(page: Page, mode: '注册' | '登录', name: string) {
  await page.getByRole('navigation', { name: '账户导航' }).getByRole('link', { name: mode }).click()
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  if (mode === '注册') {
    await page.getByLabel('学习阶段').selectOption('高中')
    await page.getByLabel('近期学习目标').fill('用图像理解二次函数')
  }
  await page.getByRole('button', { name: mode, exact: true }).click()
  await expect(page.getByRole('navigation', { name: '账户导航' }).getByText(name, { exact: true })).toBeVisible()
}

test('registration, account switching, guest recovery and leaderboard', async ({ page }) => {
  expect((await page.request.get('/.local/browser-quiz.sqlite3')).status()).toBe(403)
  const alice = 'Alice_' + randomUUID().slice(0, 8)
  const bob = 'Bob_' + randomUUID().slice(0, 8)
  await openFixtureLesson(page, 'quadratic')
  await expect(page.getByRole('heading', { name: '二次函数参数', exact: true })).toBeVisible()
  await authenticate(page, '注册', alice)
  await expect(page.getByText('你还没有开始提问，快来探索知识吧！')).toBeVisible()
  await expect(page.getByRole('button', { name: /继续上次学习/ })).toHaveCount(0)
  await openFixtureLesson(page, 'recursion')
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '递归调用栈', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page.getByRole('button', { name: /继续上次学习.*二次函数参数/ })).toBeVisible()
  await authenticate(page, '注册', bob)
  await expect(page.getByRole('button', { name: /继续上次学习/ })).toHaveCount(0)
  await page.getByRole('button', { name: '退出' }).click()
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
  await expect(page.getByRole('heading', { name: '把问题动起来。' })).toBeVisible()
  await page.getByRole('link', { name: '排行榜' }).click()
  const name = 'Learner_' + randomUUID().slice(0, 8)
  await invite.getByRole('link', { name: '注册' }).click()
  await page.getByLabel('用户名').fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('学习阶段').selectOption('初中')
  await page.getByLabel('近期学习目标').fill('能用坐标理解函数')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: '把问题动起来。' })).toBeVisible()
  await expect(invite).toHaveCount(0)

  await page.getByRole('link', { name: '学习设置' }).click()
  await expect(page.getByLabel('学习阶段')).toHaveValue('初中')
  await page.getByLabel('学习阶段').selectOption('本科')
  await page.getByLabel('近期学习目标').fill('理解函数的变化率')
  await page.getByRole('button', { name: '保存学习资料' }).click()
  await expect(page).toHaveURL(/\/$/)
  await page.getByRole('link', { name: '学习设置' }).click()
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

test('legacy account completes settings and returns to the home page', async ({ page }) => {
  const user = { id: 'old-account', username: 'OldAccount', profile: null }
  let profile: unknown = null
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { user: { ...user, profile } } }))
  await page.route('**/api/auth/profile', (route) => {
    profile = route.request().postDataJSON()
    return route.fulfill({ json: { user: { ...user, profile } } })
  })
  await page.goto('/leaderboard')
  await expect(page.getByRole('heading', { name: '完善学习资料' })).toBeVisible()
  await page.getByLabel('学习阶段').selectOption('硕士')
  await page.getByLabel('近期学习目标').fill('理解梯度在优化中的作用')
  await page.getByRole('button', { name: '保存学习资料' }).click()
  await expect(page.getByRole('heading', { name: '把问题动起来。' })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('goal review waits at 99 percent and keeps the form on rejection', async ({ page }) => {
  let finish: () => void = () => {}
  const waiting = new Promise<void>((resolve) => { finish = resolve })
  await page.route('**/api/auth/register', async (route) => {
    await waiting
    await route.fulfill({ status: 422, json: { detail: '请补充你准备参加的考试。' } })
  })
  await page.goto('/register')
  await page.getByLabel('用户名').fill('ReviewUser')
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('学习阶段').selectOption('高中')
  await page.getByLabel('近期学习目标').fill('准备参加考试')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  const review = page.getByRole('dialog', { name: '正在审核目标' })
  await expect(review.getByText('99%')).toBeVisible()
  await expect(page).toHaveURL(/\/register$/)
  finish()
  await expect(review).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveText('请补充你准备参加的考试。')
  await expect(page.getByLabel('近期学习目标')).toHaveValue('准备参加考试')
})

test('imports a paper, resubmits a pending question and returns to learn a tagged topic', async ({ page }) => {
  const user = { id: 'library-user', username: 'LibraryUser', profile: { education_stage: '初中', goal: '学习数学' } }
  const first = { id: 1, number: '1', stem: '抛物线何时开口向上？', tags: ['二次函数'],
    options: ['系数为正', '系数为负', '系数为零'], status: 'ready', file: 'paper.docx', page: 1 }
  const pending = { ...first, id: 2, number: '2', stem: '', tags: [], options: [], status: 'pending', reason: '公式有分歧。' }
  const paper = { id: 'paper', exam: '成都中考', subject: '数学', year: null, paper: null, filenames: ['paper.docx'],
    question_count: 2, ready_count: 1, review_count: 0, pending_count: 1, questions: [first, pending] }
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { user } }))
  await page.route('**/api/exam-library', (route) => route.fulfill({ json: { papers: [] } }))
  await page.route('**/api/exam-library/paper/questions/2/retry', (route) => {
    expect(route.request().postDataJSON().files[0].filename).toBe('clear.png')
    return route.fulfill({ json: { paper: { ...paper, pending_count: 0, review_count: 1,
      questions: [first, { ...pending, stem: '写出对称轴。', status: 'review_only' }] } } })
  })
  await page.route('**/api/exam-library/imports', (route) => {
    const submitted = route.request().postDataJSON()
    expect(submitted.exam).toBe('成都中考')
    expect(submitted.consent).toBe(true)
    expect(submitted.files[0]).toEqual({ filename: 'paper.docx', data: Buffer.from('sample').toString('base64') })
    return route.fulfill({ status: 201, json: { duplicate: false, paper } })
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
  await expect(page.getByText('已导入 2 道题，其中 1 道可用于自动判分。')).toBeVisible()
  await expect(page.getByText('系数为正')).toBeVisible()
  await page.getByRole('button', { name: '重新提交这道题' }).click()
  await page.getByLabel('这道题的清晰照片').setInputFiles({ name: 'clear.png', mimeType: 'image/png', buffer: Buffer.from('clear') })
  await page.getByRole('group', { name: '重新提交这道题' }).getByRole('checkbox', { name: /同意/ }).check()
  await page.getByRole('button', { name: '提交核对' }).click()
  await expect(page.getByText('写出对称轴。')).toBeVisible()
  await expect(page.getByRole('button', { name: '重新提交这道题' })).toHaveCount(0)
  await page.getByRole('link', { name: '学习二次函数' }).click()
  await expect(page.getByLabel('你想弄懂什么？')).toHaveValue('请讲解二次函数')
})
