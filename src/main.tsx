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
  const hour = new Date().getHours()
  const greeting = hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
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
          <nav className="main-nav" aria-label="主导航">
            <div className="main-links">
              <a href="/" aria-current={path === '/' || path === '/study' ? 'page' : undefined}>学习</a>
              <a href={'/exam-library?from=' + encodeURIComponent(path + window.location.search)}
                aria-current={path === '/exam-library' ? 'page' : undefined}>我的试卷</a>
              <a href={leaderboardLink()} aria-current={path === '/leaderboard' ? 'page' : undefined}>排行榜</a>
            </div>
            {session && !studying && <button type="button" className="nav-continue"
              aria-label={`继续上次学习：${currentVersion(session).lesson.title}`}
              title={`继续上次学习：${currentVersion(session).lesson.title}`}
              onClick={() => resume(session)}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="8" />
                <path d="M12 8v4l2.5 1.5" />
              </svg>
              <span>继续学习</span>
            </button>}
            {user ? <AccountMenu user={user} path={path} search={search} loggingOut={loggingOut}
              onLogout={() => void logout()} />
              : <div className="guest-actions">
                <a href={authLink('login', path === '/leaderboard')}>登录</a>
                <a href={authLink('register', path === '/leaderboard')}>注册</a>
              </div>}
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
          <section className="home-head" aria-labelledby="home-title">
            <p className="home-greeting">{user ? `${greeting}，${user.username}` : '你好，访客'}</p>
            <h1 id="home-title">今天想弄懂什么？</h1>
            <p className="home-sub">输入一个问题，生成可以亲手拖动的教学页；看懂之后再练两道题。</p>
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
          <div className="home-examples" aria-label="示例问题">
            <span>试试：</span>
            {['二次函数开口方向', '递归调用栈', '向量加法'].map((example) => <button key={example} type="button"
              className="example-chip" onClick={() => setQuestion(example)}>{example}</button>)}
          </div>
        </main>
      )}
    </>
  )
}

function AccountMenu({ user, path, search, loggingOut, onLogout }: {
  user: User
  path: string
  search: string
  loggingOut: boolean
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  const from = encodeURIComponent(path + search)
  return <div className="account-menu" ref={container}>
    <button type="button" className="avatar-button" aria-label={`账户菜单：${user.username}`}
      aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
      {user.username.slice(0, 1).toUpperCase()}
    </button>
    {open && <div className="account-dropdown" role="menu">
      <div className="account-summary">
        <strong>{user.username}</strong>
        <span>{user.profile ? `${user.profile.education_stage} · ${user.profile.goal}` : '未设置学习目标'}</span>
      </div>
      <a role="menuitem" href={'/profile?from=' + from}>个人设置</a>
      <button role="menuitem" type="button" disabled={loggingOut} onClick={() => { setOpen(false); onLogout() }}>
        {loggingOut ? '正在退出…' : '退出'}
      </button>
    </div>}
  </div>
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
