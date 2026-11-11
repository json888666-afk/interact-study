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
