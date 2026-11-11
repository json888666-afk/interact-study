import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { fetchLesson, reviseLesson } from './lessons'
import { Preview, type PreviewResult } from './preview'
import { currentVersion, makeVersion, type LessonVersion, type StudySession } from './study-session'

type FeedbackEntry = { id: string; instruction: string; reply: string }

export function LessonWorkspace({ session, onSave }: { session: StudySession; onSave: (session: StudySession) => void }) {
  const current = currentVersion(session)
  const [candidate, setCandidate] = useState<LessonVersion | null>(null)
  const [instruction, setInstruction] = useState('')
  const [requesting, setRequesting] = useState(false)
  const pending = requesting || candidate !== null
  const [feedback, setFeedback] = useState<FeedbackEntry[]>([])
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)

  useEffect(() => () => active.current?.abort(), [])

  function addFeedback(text: string, reply: string) {
    setFeedback((items) => [...items, { id: crypto.randomUUID(), instruction: text, reply }])
  }

  async function update(reload: boolean) {
    if (active.current || candidate) return
    const text = reload ? '重新加载内容' : instruction.trim()
    if (!text) return
    const controller = new AbortController()
    active.current = controller
    setRequesting(true)
    setError('')
    try {
      const { result, source } = reload
        ? await fetchLesson(session.request, controller.signal)
        : await reviseLesson(session.request.question, text, current.lesson, controller.signal)
      if (controller.signal.aborted) return
      if (result.kind === 'lesson') {
        setCandidate(makeVersion(result, text, source))
      } else {
        addFeedback(text, result.message)
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof TypeError ? '无法连接学习服务，请重试。'
          : error instanceof Error ? error.message : '修改失败，请重试。')
      }
    } finally {
      active.current = null
      if (!controller.signal.aborted) setRequesting(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void update(false)
  }

  const finishUpdate = useCallback((result: PreviewResult) => {
    if (!candidate) return
    if (result.kind === 'ready') {
      onSave({ ...session, versions: [...session.versions, candidate], currentId: candidate.id })
      setInstruction((value) => value.trim() === candidate.description ? '' : value)
      addFeedback(candidate.description, '演示已更新。旧版可从版本历史恢复。')
    } else {
      setError('新版加载失败，已保留当前版本。' + (result.message ? ' ' + result.message : ''))
    }
    setCandidate(null)
  }, [candidate, onSave, session])

  function restore(id: string) {
    setCandidate(null)
    setError('')
    onSave({ ...session, currentId: id })
  }

  return (
    <div className="lesson-workspace">
      <div className="workspace-canvas">
        {(candidate ? [current, candidate] : [current]).map((version) => {
          const staging = version.id !== current.id
          return (
            <div key={version.id} className={staging ? 'staged-lesson' : undefined} inert={staging}>
              <Preview lesson={version.lesson} onRegenerate={() => void update(true)} busy={pending}
                onResult={staging ? finishUpdate : undefined} />
            </div>
          )
        })}
      </div>
      <aside className="workspace-sidebar">
        <section className="workspace-panel" aria-labelledby="revise-title">
          <h2 id="revise-title">对话修改</h2>
          {feedback.length > 0 && <ol className="feedback-list" aria-live="polite">
            {feedback.map((entry) => <li key={entry.id}>
              <strong>{entry.instruction}</strong><p>{entry.reply}</p>
            </li>)}
          </ol>}
          <form onSubmit={submit}>
            <label htmlFor="instruction">你想怎样调整这个演示？</label>
            <textarea id="instruction" value={instruction} maxLength={2000}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="例如，增加一个暂停按钮。" />
            <button className="primary-button" type="submit" disabled={pending || !instruction.trim()}>发送修改</button>
          </form>
          {pending && <p className="workspace-status" role="status">{candidate ? '正在加载新版演示…' : '正在生成新版演示…'}</p>}
          {error && <p className="workspace-status" role="alert">{error}</p>}
        </section>
        <section className="workspace-panel" aria-labelledby="versions-title">
          <h2 id="versions-title">版本历史</h2>
          <ol className="version-list">
            {session.versions.map((version, index) => <li key={version.id}>
              <div><strong>版本 {index + 1}</strong><p title={version.description}>{version.description}</p></div>
              {version.id === current.id ? <span>当前</span>
                : <button className="quiet-button" type="button" disabled={pending}
                  aria-label={`恢复版本 ${index + 1}`} onClick={() => restore(version.id)}>恢复</button>}
            </li>)}
          </ol>
        </section>
      </aside>
    </div>
  )
}
