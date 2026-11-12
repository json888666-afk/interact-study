import { expect, type Page } from '@playwright/test'
import type { Lesson } from '../../src/lessons'

export async function openFixtureLesson(page: Page, id: 'quadratic' | 'recursion') {
  const fixture = await page.request.get('/api/examples/' + id)
  expect(fixture.ok()).toBeTruthy()
  const { result }: { result: Lesson } = await fixture.json()
  await page.route('**/api/lessons/generate', (route) => route.fulfill({ json: { source: 'live', result } }))
  await page.goto('/')
  await page.getByLabel('你想弄懂什么？').fill(result.title)
  await page.getByRole('button', { name: '生成演示' }).click()
}
