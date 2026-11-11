import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { examples, fetchLesson, type LessonRequest, type LessonResponse } from './lessons'
import { LessonWorkspace } from './lesson-workspace'
import { createStudySession, currentVersion, loadStudySession, saveStudySession, type StudySession } from './study-session'
import './styles.css'

type StudyState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'response'; data: LessonResponse }

function App() {
  const [session, setSession] = useState(loadStudySession)
  const [question, setQuestion] = useState(() => session?.request.question ?? '')
  const [request, setRequest] = useState<LessonRequest | null>(() => session?.request ?? null)
  const [state, setState] = useState<StudyState>(() => session
    ? { kind: 'response', data: { source: currentVersion(session).source, result: currentVersion(session).lesson } }
    : { kind: 'loading' })
  const [studying, setStudying] = useState(() => Boolean(session && window.location.pathname === '/study'))
  const [storageError, setStorageError] = useState('')
  const active = useRef<AbortController | null>(null)
  const studyHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (window.location.pathname === '/study' && !studying) window.history.replaceState(null, '', '/')
    const onNavigate = () => setStudying(window.location.pathname === '/study')
    window.addEventListener('popstate', onNavigate)
    return () => {
      window.removeEventListener('popstate', onNavigate)
      active.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (studying) studyHeading.current?.focus()
  }, [studying])

  function home() {
    if (!studying) return
    if (window.history.state?.study) window.history.back()
    else {
      window.history.replaceState(null, '', '/')
      setStudying(false)
    }
  }

  function enterStudy() {
    if (window.location.pathname !== '/study') window.history.pushState({ study: true }, '', '/study')
    setStudying(true)
  }

  function save(session: StudySession) {
    setSession(session)
    try {
      saveStudySession(session)
      setStorageError('')
    } catch {
      setStorageError('浏览器无法保存此版本，关闭或刷新页面后可能无法恢复。')
    }
  }

  function resume(session: StudySession) {
    active.current?.abort()
    const version = currentVersion(session)
    setRequest(session.request)
    setState({ kind: 'response', data: { source: version.source, result: version.lesson } })
    enterStudy()
  }

  async function open(next: LessonRequest) {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setRequest(next)
    setState({ kind: 'loading' })
    enterStudy()
    try {
      const data = await fetchLesson(next, controller.signal)
      if (!controller.signal.aborted) {
        if (data.result.kind === 'lesson') save(createStudySession(next, data.result))
        setState({ kind: 'response', data })
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof TypeError ? '无法连接学习服务，请确认后端已启动。'
          : error instanceof Error ? error.message : '加载失败，请重试。'
        setState({ kind: 'error', message })
      }
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const value = question.trim()
    if (value) void open({ source: 'live', question: value })
  }

  const result = state.kind === 'response' ? state.data.result : null
  const workspace = result?.kind === 'lesson' ? session : null
  const version = workspace ? currentVersion(workspace) : null

  return (
    <>
      <header className="topbar">
        <div className="topbar-content">
          <a className="brand" href="/" onClick={(event) => { event.preventDefault(); home() }}>
            <span className="brand-mark" aria-hidden="true">∿</span>演算室
          </a>
          <span className="topbar-label">数学与计算机 · 交互学习</span>
        </div>
      </header>
      {studying && request ? (
        <main className="study page">
          <button type="button" className="back-button" onClick={home}>← 返回问题首页</button>
          <div className="study-header">
            <p className="source">{(version?.source ?? (state.kind === 'response' ? state.data.source : request.source)) === 'example'
              ? '预置案例' : '实时生成'}</p>
            <h1 ref={studyHeading} tabIndex={-1}>{version?.lesson.title ?? request.question}</h1>
            {version && <p>{version.lesson.summary}</p>}
          </div>
          {state.kind === 'loading' && <div className="state-panel" role="status"><span className="spinner" />正在准备教学页面…</div>}
          {state.kind === 'error' && <div className="state-panel error-panel" role="alert">
            <p>{state.message}</p>
            <button type="button" className="primary-button" onClick={() => void open(request)}>重试</button>
          </div>}
          {result && result.kind !== 'lesson' && <div className="state-panel" role="status">
            <p>{result.message}</p><button type="button" className="primary-button" onClick={home}>编辑问题</button>
          </div>}
          {workspace && <LessonWorkspace key={workspace.id} session={workspace} onSave={save} />}
          {workspace && storageError && <p role="alert">{storageError}</p>}
        </main>
      ) : (
        <main className="home page">
          <section className="hero" aria-labelledby="home-title">
            <h1 id="home-title">把问题<span>动起来。</span></h1>
            <p>输入一个数学或计算机问题，生成可以亲手操作的交互演示。</p>
          </section>
          <form className="question-card" onSubmit={submit}>
            <label htmlFor="question">你想弄懂什么？</label>
            <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)}
              maxLength={2000} required placeholder="例如，为什么改变二次函数的系数，会让抛物线变宽或变窄？" />
            <div className="form-footer">
              <span className="character-count">{question.length} / 2000</span>
              <button className="primary-button" type="submit" disabled={!question.trim()}>生成演示 <span aria-hidden="true">→</span></button>
            </div>
          </form>
          {session && <button type="button" className="quiet-button resume-button" onClick={() => resume(session)}>
            继续上次学习 · {currentVersion(session).lesson.title}
          </button>}
          <section className="examples" aria-labelledby="examples-heading">
            <h2 id="examples-heading">预置案例</h2>
            <div className="example-grid">
              {examples.map((example) => (
                <button key={example.id} type="button" className="example-card"
                  onClick={() => void open({ source: 'example', id: example.id, question: example.title })}>
                  <span className="example-mark" aria-hidden="true">{example.mark}</span>
                  <span className="example-copy">
                    <span className="subject">{example.subject}</span>
                    <strong>{example.title}</strong>
                    <span className="description">{example.description}</span>
                  </span>
                  <span className="example-arrow" aria-hidden="true">↗</span>
                </button>
              ))}
            </div>
          </section>
        </main>
      )}
    </>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
