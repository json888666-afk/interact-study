import { learningRequest, type LearningContext } from './learning-api'

export type Question = {
  id: string
  kind: 'single' | 'multiple'
  topic: string
  stem: string
  options: string[]
  origin?: 'past' | 'simulated'
  source?: {
    exam: string
    subject: string
    year: number | null
    number: string
    publisher: string
    attribution?: string
    paper?: string | null
    imported?: boolean
    filename?: string
    page?: number
    url?: string | null
    license_url?: string | null
  }
  answer?: { selected: number[]; is_correct?: boolean; unsure?: boolean; correct?: number[]; explanation?: string }
  review?: {
    status: 'pending' | 'valid' | 'uncertain' | 'failed' | 'replacement_failed' | 'replaced'
    message: string
    objection?: string
    can_replace_simulated?: boolean
  }
  drill?: Drill
}

export type Drill = {
  required: boolean
  status: 'awaiting_explanation' | 'generating' | 'ready' | 'failed' | 'passed'
  round: number
  message: string
  questions: Question[]
  feedback: { id: string; stem: string; options: string[]; correct: number[]; selected: number[]; explanation: string }[]
}

export type Quiz = {
  id: string
  version_id: string
  status: 'generating' | 'ready' | 'failed' | 'exam_choice'
  exam?: { exam: string; subject: string }
  public_papers?: { url: string; title: string; year: number; publisher: string }[]
  message: string
  questions: Question[]
  blocked_question_id?: string | null
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
