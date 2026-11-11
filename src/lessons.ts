export type Lesson = {
  kind: 'lesson'
  title: string
  summary: string
  html: string
  css: string
  javascript: string
}

export type LessonResponse = {
  source: 'live' | 'example'
  result: Lesson | { kind: 'clarification' | 'out_of_scope'; message: string }
}

export type LessonRequest =
  | { source: 'live'; question: string }
  | { source: 'example'; id: string; question: string }

export const examples = [
  { id: 'quadratic', subject: '数学', title: '二次函数参数', description: '拖动参数，观察抛物线的变化。', mark: 'ƒ(x)' },
  { id: 'recursion', subject: '计算机', title: '递归调用栈', description: '单步执行，跟踪栈帧与返回值。', mark: '↳' },
]

export async function fetchLesson(request: LessonRequest, signal: AbortSignal): Promise<LessonResponse> {
  const response = request.source === 'example'
    ? await fetch('/api/examples/' + encodeURIComponent(request.id), { signal })
    : await fetch('/api/lessons/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: request.question }),
        signal,
      })

  return readLessonResponse(response)
}

export async function reviseLesson(question: string, instruction: string, lesson: Lesson, signal: AbortSignal) {
  const response = await fetch('/api/lessons/revise', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, instruction, lesson }),
    signal,
  })
  return readLessonResponse(response)
}

async function readLessonResponse(response: Response): Promise<LessonResponse> {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(typeof body?.detail?.message === 'string'
      ? body.detail.message
      : '暂时无法载入教学页面，请重试。')
  }
  if (!body) throw new Error('无法读取教学内容，请重试。')
  return body
}
