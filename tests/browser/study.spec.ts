import { expect, test, type Page } from '@playwright/test'

const previewTitle = '交互教学预览'

async function submitQuestion(page: Page, question = '请解释递归') {
  await page.getByLabel('你想弄懂什么？').fill(question)
  await page.getByRole('button', { name: '生成演示' }).click()
  await expect(page).toHaveURL(/\/study$/)
}

async function mockLesson(page: Page, javascript: string) {
  await page.route('**/api/lessons/generate', (route) => route.fulfill({
    json: {
      source: 'live',
      result: {
        kind: 'lesson',
        title: '测试教学页面',
        summary: '预览验证',
        html: '<p id="check">正在检查</p>',
        css: '',
        javascript,
      },
    },
  }))
}

test('quadratic slider changes the preview and can reset', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /二次函数参数/ }).click()
  await expect(page.getByText('预置案例', { exact: true })).toBeVisible()
  const frame = page.frameLocator('iframe')
  await expect(frame.getByText('开口向上。', { exact: false })).toBeVisible()
  await frame.getByRole('slider', { name: '参数 a' }).fill('-1')
  await expect(frame.getByText('开口向下。', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '重新运行' }).click()
  await expect(frame.getByText('开口向上。', { exact: false })).toBeVisible()
})

test('recursion steps through stack and returns 24 on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await page.goto('/')
  await page.getByRole('button', { name: /递归调用栈/ }).click()
  const frame = page.frameLocator('iframe')
  const next = frame.getByRole('button', { name: '下一步' })
  await next.click()
  await expect(frame.getByRole('listitem')).toHaveText('factorial(4)')
  for (let index = 0; index < 7; index++) await next.click()
  await expect(frame.getByText('factorial(4) 返回 4 × 6 = 24。')).toBeVisible()
  await expect(next).toBeDisabled()
  await frame.getByRole('button', { name: '重置' }).click()
  await expect(next).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375)
})

test('generated preview cannot read host DOM or storage or fetch externally', async ({ page }) => {
  let externalRequests = 0
  await page.route('https://preview-probe.example/**', (route) => {
    externalRequests++
    return route.fulfill({ body: 'unexpected' })
  })
  await mockLesson(page, `
    const results = [];
    for (const [label, probe] of [
      ['DOM', () => parent.document.body],
      ['storage', () => parent.localStorage.getItem('lesson-probe')],
    ]) {
      try { probe(); results.push(label + ':open'); }
      catch { results.push(label + ':blocked'); }
    }
    fetch('https://preview-probe.example/').then(
      () => results.push('fetch:open'),
      () => results.push('fetch:blocked'),
    ).finally(() => { document.querySelector('#check').textContent = results.join(','); });
  `)
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('lesson-probe', 'test-value'))
  await submitQuestion(page)
  const iframe = page.getByTitle(previewTitle)
  await expect(iframe).toHaveAttribute('sandbox', 'allow-scripts')
  await expect(page.frameLocator('iframe').locator('#check')).toHaveText('DOM:blocked,storage:blocked,fetch:blocked')
  expect(externalRequests).toBe(0)
})

test('preview surfaces script errors and can regenerate', async ({ page }) => {
  await mockLesson(page, 'throw new Error("测试脚本失败")')
  await page.goto('/')
  await submitQuestion(page)
  await expect(page.getByRole('alert')).toContainText('测试脚本失败')
  await mockLesson(page, 'document.querySelector("#check").textContent = "已恢复"')
  await page.getByRole('button', { name: '重新加载内容' }).click()
  await expect(page.frameLocator('iframe').locator('#check')).toHaveText('已恢复')
})

test('rejects old preview messages and messages with a stale preview identifier', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /二次函数参数/ }).click()
  const iframe = page.getByTitle(previewTitle)
  await expect(page.frameLocator('iframe').getByRole('slider')).toBeVisible()
  await iframe.evaluate((element: HTMLIFrameElement) => {
    Object.assign(window, { previousPreview: element.contentWindow })
  })
  await page.getByRole('button', { name: '重新运行' }).click()
  await expect(page.frameLocator('iframe').getByRole('slider')).toBeVisible()
  await iframe.evaluate((element: HTMLIFrameElement) => {
    const oldWindow = (window as Window & { previousPreview: Window }).previousPreview
    const id = element.srcdoc.match(/<script nonce="([a-f\d]+)">/)?.[1]
    for (const [source, previewId] of [[oldWindow, id], [element.contentWindow, 'stale'] ] as const) {
      window.dispatchEvent(new MessageEvent('message', {
        source, origin: 'null',
        data: { channel: 'interact-study-preview', previewId, type: 'error', message: '应被忽略' },
      }))
    }
  })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.frameLocator('iframe').getByRole('slider')).toBeVisible()
})

test('failed requests and clarification retain the question', async ({ page }) => {
  await page.route('**/api/lessons/generate', (route) => route.fulfill({
    status: 504, json: { detail: { code: 'model_timeout', message: '生成超时，请重试。' } },
  }), { times: 1 })
  await page.goto('/')
  const question = '解释这个函数'
  await submitQuestion(page, question)
  await expect(page.getByRole('alert')).toContainText('生成超时')
  await page.route('**/api/lessons/generate', (route) => {
    expect(route.request().postDataJSON()).toEqual({ question })
    return route.fulfill({ json: { source: 'live', result: { kind: 'clarification', message: '请给出函数表达式。' } } })
  })
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('请给出函数表达式。')).toBeVisible()
  await page.getByRole('button', { name: '编辑问题' }).click()
  await expect(page.getByLabel('你想弄懂什么？')).toHaveValue(question)
})

test('revision switches automatically and restores history after refresh', async ({ page }) => {
  await page.route('**/api/lessons/revise', async (route) => {
    const { question, instruction, lesson } = route.request().postDataJSON()
    expect(question).toBe('递归调用栈')
    expect(instruction).toBe('增加暂停按钮')
    expect(lesson.title).toBe('递归调用栈')
    await route.fulfill({ json: {
      source: 'live',
      result: { ...lesson, title: '可暂停的递归演示', html: '<button id="pause">暂停</button>', css: '',
        javascript: 'document.querySelector("#pause").onclick = (event) => { event.target.textContent = "继续"; };' },
    } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /递归调用栈/ }).click()
  await page.getByLabel('你想怎样调整这个演示？').fill('增加暂停按钮')
  await page.getByRole('button', { name: '发送修改' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('可暂停的递归演示')
  await expect(page.getByRole('button', { name: '确认此版本' })).toHaveCount(0)
  await page.frameLocator('iframe').getByRole('button', { name: '暂停' }).click()
  await expect(page.frameLocator('iframe').getByRole('button', { name: '继续' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('可暂停的递归演示')
  await page.getByRole('button', { name: '恢复版本 1' }).click()
  await expect(page.frameLocator('iframe').getByRole('button', { name: '下一步' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('递归调用栈')
  await expect(page.getByRole('button', { name: '恢复版本 2' })).toBeVisible()
})

test('a broken revision preserves the current iframe and its slider state', async ({ page }) => {
  await page.route('**/api/lessons/revise', async (route) => {
    const { lesson } = route.request().postDataJSON()
    await route.fulfill({ json: {
      source: 'live', result: { ...lesson, javascript: 'throw new Error("候选脚本失败")' },
    } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: /二次函数参数/ }).click()
  const slider = page.frameLocator('iframe').getByRole('slider')
  await slider.fill('-1')
  await page.getByLabel('你想怎样调整这个演示？').fill('调整线条颜色')
  await page.getByRole('button', { name: '发送修改' }).click()
  await expect(page.getByRole('alert')).toContainText('新版加载失败，已保留当前版本。')
  await expect(page.getByRole('alert')).toContainText('候选脚本失败')
  await expect(slider).toHaveValue('-1')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('二次函数参数')
  await expect(page.getByText('版本 2', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('你想怎样调整这个演示？')).toHaveValue('调整线条颜色')
})
