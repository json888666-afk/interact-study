import { useEffect, useRef, useState, type FormEvent } from 'react'
import { askLesson, type LearningContext, type Turn } from './learning-api'

export function AskPanel({ context, draft, setDraft, onAnswer }: {
  context: LearningContext
  draft: string
  setDraft: (value: string) => void
  onAnswer: (turn: Turn) => void
}) {
  const [image, setImage] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => () => active.current?.abort(), [])

  function chooseImage(file: File | undefined) {
    setError('')
    if (!file) {
      setImage(null)
    } else if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setImage(null)
      if (fileInput.current) fileInput.current.value = ''
      setError('请选择不超过 5 MiB 的 PNG、JPEG 或 WebP 截图。')
    } else {
      setImage(file)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || active.current) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    try {
      const encoded = image ? await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(new Error('无法读取截图，请重新选择。'))
        reader.readAsDataURL(image)
      }) : null
      if (controller.signal.aborted) return
      const { answer } = await askLesson({ ...context, history: context.history.slice(-6) }, message, encoded, controller.signal)
      if (controller.signal.aborted) return
      onAnswer({ question: message, answer })
      setDraft('')
      setImage(null)
      if (fileInput.current) fileInput.current.value = ''
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : '问答失败，请重试。')
    } finally {
      active.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return (
    <section className="workspace-panel" aria-label="问原理">
      {context.history.length > 0 && <ol className="feedback-list" aria-live="polite">
        {context.history.map((turn, index) => <li key={index}>
          <strong>{turn.question}</strong><p className="explanation">{turn.answer}</p>
        </li>)}
      </ol>}
      <form onSubmit={submit}>
        <label htmlFor="ask-message">你想理解什么？</label>
        <textarea id="ask-message" value={draft} maxLength={2000} disabled={busy}
          onChange={(event) => setDraft(event.target.value)} placeholder="例如，这一步为什么成立？" />
        <label htmlFor="ask-image">附一张截图（可选）</label>
        <input id="ask-image" className="screenshot-input" type="file" ref={fileInput} disabled={busy}
          accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseImage(event.target.files?.[0])} />
        <button className="primary-button" type="submit" disabled={busy || !draft.trim()}>发送问题</button>
      </form>
      {busy && <p role="status">正在整理解释…</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
