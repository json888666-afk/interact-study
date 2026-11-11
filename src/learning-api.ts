import type { Lesson } from './lessons'

export type Turn = { question: string; answer: string }
export type LearningContext = { question: string; lesson: Lesson; history: Turn[] }

export async function learningRequest<T>(path: string, options: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail
      : typeof detail?.message === 'string' ? detail.message : '请求未完成，请检查输入后重试。'
    throw new Error(message)
  }
  return payload as T
}

export function askLesson(context: LearningContext, message: string, image: string | null, signal: AbortSignal) {
  return learningRequest<{ answer: string }>('/api/lessons/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...context, message, image }),
    signal,
  })
}
