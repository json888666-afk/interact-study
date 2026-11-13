import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { AUTH_CHANGE_KEY, AuthForm, Leaderboard, LearningSettings, authLink, authRequest, finishAuth, leaderboardLink, safeReturnLocation, type User } from './account-pages'
import { GUEST_KEY, Onboarding, WelcomeCelebration, WelcomeGate } from './welcome'
import { ExamLibrary } from './exam-library'
import { fetchLesson, type LessonRequest, type LessonResponse } from './lessons'
import { LessonWorkspace } from './lesson-workspace'
import { LoadingProgress } from './loading-progress'
import { createStudySession, currentVersion, loadStudySession, saveStudySession, type StudySession } from './study-session'
import './styles.css'

type StudyState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'response'; data: LessonResponse }

function App({ user }: { user: User | null }) {
  const [session, setSession] = useState(() => loadStudySession(user?.id))
  const [question, setQuestion] = useState(() => new URLSearchParams(window.location.search).get('question')?.slice(0, 2000)
    ?? session?.request.question ?? '')
  const [request, setRequest] = useState<LessonRequest | null>(() => session?.request ?? null)
  const [state, setState] = useState<StudyState>(() => session
    ? { kind: 'response', data: { source: currentVersion(session).source, result: currentVersion(session).lesson } }
    : { kind: 'loading' })
  const [studying, setStudying] = useState(() => Boolean(session && window.location.pathname === '/study'))
  const [storageError, setStorageError] = useState('')
  const [logoutError, setLogoutError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
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
      saveStudySession(session, user?.id)
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

  async function logout() {
    setLoggingOut(true)
    setLogoutError('')
    try {
      await authRequest('logout')
      try { sessionStorage.removeItem(GUEST_KEY) } catch { /* storage may be unavailable */ }
      finishAuth()
    } catch {
      setLogoutError('退出失败，请重试。')
      setLoggingOut(false)
    }
  }

  const result = state.kind === 'response' ? state.data.result : null
  const workspace = result?.kind === 'lesson' ? session : null
  const version = workspace ? currentVersion(workspace) : null
  const path = window.location.pathname
  const search = window.location.search
  const params = new URLSearchParams(search)
  const guestEntry = (() => {
    try { return sessionStorage.getItem(GUEST_KEY) === '1' } catch { return false }
  })()

  if (user?.profile && params.get('welcome') === '1') {
    return <WelcomeCelebration next={safeReturnLocation(params.get('next')) ?? '/'} />
  }
  if (user === null && path === '/' && !guestEntry) {
    return <WelcomeGate onGuest={() => {
      try { sessionStorage.setItem(GUEST_KEY, '1') } catch { /* storage may be unavailable */ }
      window.location.replace('/')
    }} />
  }
  if (user && (!user.profile || user.needs_goal_review)) {
    return <Onboarding returnTo={path === '/profile' ? '/' : path + search} />
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-content">
          <a className="brand" href="/" onClick={(event) => {
            if (studying) { event.preventDefault(); home() }
          }}>
            <span className="brand-mark" aria-hidden="true">∿</span>可视化理论中心
          </a>
          <nav className="account-nav" aria-label="账户导航">
            <a href={leaderboardLink()}>排行榜</a>
            {user ? <>
              <span className="account-name">{user.username}</span>
              <a href={'/exam-library?from=' + encodeURIComponent(path + window.location.search)}>我的试卷</a>
              <a href={'/profile?from=' + encodeURIComponent(path + window.location.search)}>个人设置</a>
              <button type="button" className="quiet-button" disabled={loggingOut} onClick={() => void logout()}>退出</button>
            </> : <>
              <a href={authLink('login', path === '/leaderboard')}>登录</a>
              <a href={authLink('register', path === '/leaderboard')}>注册</a>
            </>}
          </nav>
        </div>
      </header>
      {logoutError && <p className="page" role="alert">{logoutError}</p>}
      {user && path === '/profile' ? <LearningSettings user={user} />
      : path === '/leaderboard' ? <Leaderboard guest={!user} />
      : path === '/exam-library' ? <ExamLibrary signedIn={!!user} />
      : path === '/profile' ? <AuthForm mode="login" />
      : path === '/login' || path === '/register' ? <AuthForm mode={path === '/login' ? 'login' : 'register'} />
      : studying && request ? (
        <main className="study page">
          <button type="button" className="back-button" onClick={home}>← 返回问题首页</button>
          <div className="study-header">
            <p className="source">{(version?.source ?? (state.kind === 'response' ? state.data.source : request.source)) === 'example'
              ? '预置案例' : '实时生成'}</p>
            <p className="profile-badge">{user?.profile
              ? `按 ${user.profile.education_stage} · ${user.profile.goal} 生成`
              : '通用模式 · 登录后可按年级/目标定制'}</p>
            <h1 ref={studyHeading} tabIndex={-1}>{version?.lesson.title ?? request.question}</h1>
            {version && <p>{version.lesson.summary}</p>}
          </div>
          {state.kind === 'loading' && <div className="state-panel"><LoadingProgress label="正在生成教学页面…" /></div>}
          {state.kind === 'error' && <div className="state-panel error-panel" role="alert">
            <p>{state.message}</p>
            <button type="button" className="primary-button" onClick={() => void open(request)}>重试</button>
          </div>}
          {result && result.kind !== 'lesson' && <div className="state-panel" role="status">
            <p>{result.message}</p><button type="button" className="primary-button" onClick={home}>编辑问题</button>
          </div>}
          {workspace && <LessonWorkspace key={workspace.id} session={workspace} accountId={user?.id} onSave={save} />}
          {workspace && storageError && <p role="alert">{storageError}</p>}
        </main>
      ) : (
        <main className="home page">
          <section className="hero" aria-labelledby="home-title">
            <h1 id="home-title">把问题<span>动起来。</span></h1>
            <p>{user && !session ? '你还没有开始提问，快来探索知识吧！'
              : '输入一个数学或计算机问题，生成可以亲手操作的交互演示。'}</p>
          </section>
          {user?.profile
            ? <p className="profile-hint">当前个人设置：{user.profile.education_stage} · {user.profile.goal}
                <a href={'/profile?from=' + encodeURIComponent(path)}>修改</a></p>
            : <p className="profile-hint">登录并设置学习阶段与目标后，可获得更贴合的内容。</p>}
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
        </main>
      )}
    </>
  )
}

function AccountRoot() {
  const [user, setUser] = useState<User | null | undefined>()
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    authRequest('me', undefined, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setUser(result.user) })
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    const onStorage = (event: StorageEvent) => { if (event.key === AUTH_CHANGE_KEY) window.location.reload() }
    const onShow = (event: PageTransitionEvent) => { if (event.persisted) window.location.reload() }
    window.addEventListener('storage', onStorage)
    window.addEventListener('pageshow', onShow)
    return () => {
      controller.abort()
      window.removeEventListener('storage', onStorage)
      window.removeEventListener('pageshow', onShow)
    }
  }, [])

  if (error) return <main className="page account-page" role="alert">
    无法读取登录状态。 <button type="button" className="quiet-button" onClick={() => window.location.reload()}>重试</button>
  </main>
  return user === undefined ? <p className="page account-page" role="status">正在加载…</p>
    : <App user={user} />
}

createRoot(document.getElementById('root')!).render(<AccountRoot />)
