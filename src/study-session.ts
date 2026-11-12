import type { Lesson, LessonRequest, LessonResponse } from './lessons'

export type LessonVersion = {
  id: string
  lesson: Lesson
  description: string
  source: LessonResponse['source']
}

export type StudySession = {
  id: string
  request: LessonRequest
  versions: LessonVersion[]
  currentId: string
}

const STORAGE_KEY = 'interact-study.session.v1'

function storageKey(accountId?: string) {
  return accountId ? STORAGE_KEY + '.' + accountId : STORAGE_KEY
}

export function makeVersion(lesson: Lesson, description: string, source: LessonVersion['source']): LessonVersion {
  return { id: crypto.randomUUID(), lesson, description, source }
}

export function createStudySession(request: LessonRequest, lesson: Lesson): StudySession {
  const initial = makeVersion(lesson, '初始版本', request.source)
  return { id: crypto.randomUUID(), request, versions: [initial], currentId: initial.id }
}

export function currentVersion(session: StudySession): LessonVersion {
  return session.versions.find((version) => version.id === session.currentId)!
}

export function loadStudySession(accountId?: string): StudySession | null {
  try {
    const value = localStorage.getItem(storageKey(accountId))
    if (!value) return null
    const session: StudySession = JSON.parse(value)
    const request = session?.request
    if (typeof session?.id !== 'string' || typeof session.currentId !== 'string'
      || typeof request?.question !== 'string'
      || !(request.source === 'live' || (request.source === 'example' && typeof request.id === 'string'))
      || !Array.isArray(session.versions)
      || !session.versions.some((version) => version?.id === session.currentId)) return null
    for (const version of session.versions) {
      const lesson = version?.lesson
      if (typeof version?.id !== 'string' || typeof version.description !== 'string'
        || (version.source !== 'live' && version.source !== 'example')
        || lesson?.kind !== 'lesson'
        || ![lesson.title, lesson.summary, lesson.html, lesson.css, lesson.javascript]
          .every((field) => typeof field === 'string')) return null
    }
    return session
  } catch {
    return null
  }
}

export function saveStudySession(session: StudySession, accountId?: string) {
  localStorage.setItem(storageKey(accountId), JSON.stringify(session))
}
