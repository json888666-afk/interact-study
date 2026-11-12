import { learningRequest, type LearningContext } from './learning-api'

export type Question = {
  id: string
  kind: 'single' | 'multiple'
  topic: string
  stem: string
  options: string[]
  answer?: { selected: number[]; correct: number[]; is_correct: boolean; explanation: string }
  review?: {
    status: 'pending' | 'valid' | 'uncertain' | 'failed' | 'replacement_failed' | 'replaced'
    message: string
    objection?: string
  }
}

export type Quiz = {
  id: string
  version_id: string
  status: 'generating' | 'ready' | 'failed'
  message: string
  questions: Question[]
  ranking: { enabled: boolean; session_point: 0 | 1 }
  report: {
    total: number
    correct: number
    percent: number
    passed: boolean
    topics: { topic: string; correct: number; total: number }[]
    wrong_ids: string[]
  } | null
}

export type QuizIdentity = { sessionId: string; accountId?: string }

export function quizRequest<T>(owner: QuizIdentity, path: string, signal: AbortSignal, body?: object) {
  return learningRequest<T>('/api/quizzes' + path, {
    method: body ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-Study-Session': owner.sessionId,
      'X-Study-Account': owner.accountId ?? 'guest',
    },
    signal,
    body: body ? JSON.stringify(body) : undefined,
  })
}

export function startQuiz(owner: QuizIdentity, version: string, context: LearningContext, signal: AbortSignal, previous?: string) {
  return quizRequest<Quiz>(owner, '', signal, { ...context, version_id: version, previous_id: previous })
}
